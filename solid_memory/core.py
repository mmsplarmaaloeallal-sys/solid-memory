"""Persistent knowledge store with epistemic labels and a verifiable event hash chain.

The initial release intentionally uses Python's standard library only.
It is a reliable foundation, not a claim to implement every subsystem in the
larger Solid Memory architecture diagram.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EpistemicType(str, Enum):
    FACT = "FACT"
    CLAIM = "CLAIM"
    HYPOTHESIS = "HYPOTHESIS"
    ASSUMPTION = "ASSUMPTION"
    UNKNOWN = "UNKNOWN"
    CONTRADICTION = "CONTRADICTION"


@dataclass(frozen=True)
class KnowledgeEntry:
    id: str
    content: str
    epistemic_type: EpistemicType
    confidence: float
    provenance: dict[str, Any]
    version: int
    content_hash: str
    created_at: str
    metadata: dict[str, Any]
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["epistemic_type"] = self.epistemic_type.value
        return value


class SolidMemory:
    """SQLite-backed append-only knowledge records and integrity events."""

    def __init__(self, database: str | Path = "solid_memory.sqlite3") -> None:
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                epistemic_type TEXT NOT NULL,
                confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                provenance_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                parent_id TEXT REFERENCES entries(id)
            );
            CREATE INDEX IF NOT EXISTS idx_entries_type ON entries(epistemic_type);
            CREATE INDEX IF NOT EXISTS idx_entries_parent ON entries(parent_id);
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS relations (
                source_id TEXT NOT NULL REFERENCES entries(id),
                target_id TEXT NOT NULL REFERENCES entries(id),
                relation_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(source_id, target_id, relation_type)
            );
            """)
            if db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
                self._append_event(db, "STORE_INITIALIZED", "store", {"schema_version": 1})

    def _append_event(self, db: sqlite3.Connection, event_type: str, entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        previous = db.execute("SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = previous["event_hash"] if previous else "0" * 64
        created_at = utc_now()
        event_id = str(uuid.uuid4())
        payload_json = canonical_json(payload)
        signed = canonical_json({
            "event_id": event_id, "event_type": event_type, "entity_id": entity_id,
            "payload_json": payload_json, "previous_hash": previous_hash, "created_at": created_at,
        })
        event_hash = sha256_text(signed)
        db.execute(
            "INSERT INTO events(event_id,event_type,entity_id,payload_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?,?)",
            (event_id, event_type, entity_id, payload_json, previous_hash, event_hash, created_at),
        )
        return {"event_id": event_id, "event_hash": event_hash, "previous_hash": previous_hash}

    @staticmethod
    def classify(content: str) -> EpistemicType:
        """Conservative heuristic only; it does not verify truth."""
        text = content.strip().lower()
        if not text:
            return EpistemicType.UNKNOWN
        if re.search(r"\b(i assume|assumption:|assuming that)\b", text):
            return EpistemicType.ASSUMPTION
        if re.search(r"\b(hypothesis:|hypothesize|might be|may be|could be|possibly)\b", text):
            return EpistemicType.HYPOTHESIS
        if re.search(r"\b(unknown|not known|unverified|not yet verified)\b", text):
            return EpistemicType.UNKNOWN
        if re.search(r"\b(claim:|alleges?|reportedly|according to)\b", text):
            return EpistemicType.CLAIM
        return EpistemicType.CLAIM

    def add(
        self,
        content: str,
        epistemic_type: EpistemicType | str | None = None,
        confidence: float = 0.5,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> KnowledgeEntry:
        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        kind = EpistemicType(epistemic_type) if epistemic_type else self.classify(content)
        provenance = provenance or {"source_type": "user_supplied"}
        metadata = metadata or {}
        if not isinstance(provenance, dict) or not isinstance(metadata, dict):
            raise ValueError("provenance and metadata must be JSON objects")
        with self._connect() as db:
            if parent_id and not db.execute("SELECT 1 FROM entries WHERE id=?", (parent_id,)).fetchone():
                raise ValueError(f"parent_id does not exist: {parent_id}")
            version = 1
            if parent_id:
                row = db.execute("SELECT MAX(version) AS v FROM entries WHERE id=? OR parent_id=?", (parent_id, parent_id)).fetchone()
                version = int(row["v"] or 1) + 1
            entry_id = str(uuid.uuid4())
            created_at = utc_now()
            content_hash = sha256_text(canonical_json({
                "content": content, "epistemic_type": kind.value, "confidence": float(confidence),
                "provenance": provenance, "metadata": metadata, "parent_id": parent_id,
            }))
            db.execute(
                """INSERT INTO entries(id,content,epistemic_type,confidence,provenance_json,version,content_hash,created_at,metadata_json,parent_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (entry_id, content, kind.value, float(confidence), canonical_json(provenance), version, content_hash, created_at, canonical_json(metadata), parent_id),
            )
            self._append_event(db, "KNOWLEDGE_ADDED", entry_id, {
                "content_hash": content_hash, "epistemic_type": kind.value, "confidence": float(confidence),
                "provenance": provenance, "version": version, "parent_id": parent_id,
            })
            row = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        return self._row_to_entry(row)

    def revise(self, entry_id: str, content: str, **changes: Any) -> KnowledgeEntry:
        old = self.get(entry_id)
        if not old:
            raise KeyError(f"entry not found: {entry_id}")
        return self.add(
            content,
            epistemic_type=changes.get("epistemic_type", old.epistemic_type),
            confidence=changes.get("confidence", old.confidence),
            provenance=changes.get("provenance", old.provenance),
            metadata=changes.get("metadata", old.metadata),
            parent_id=entry_id,
        )

    def get(self, entry_id: str) -> KnowledgeEntry | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def list_entries(self, limit: int = 50, epistemic_type: str | None = None) -> list[KnowledgeEntry]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as db:
            if epistemic_type:
                rows = db.execute("SELECT * FROM entries WHERE epistemic_type=? ORDER BY rowid DESC LIMIT ?", (EpistemicType(epistemic_type).value, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM entries ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def search(self, query: str, limit: int = 20) -> list[KnowledgeEntry]:
        terms = [term for term in re.findall(r"[\w-]+", query.lower()) if term]
        if not terms:
            return []
        limit = max(1, min(int(limit), 200))
        # Portable baseline retrieval; vector embeddings can be added behind this API later.
        where = " AND ".join("LOWER(content) LIKE ?" for _ in terms)
        args = [f"%{term}%" for term in terms] + [limit]
        with self._connect() as db:
            rows = db.execute(f"SELECT * FROM entries WHERE {where} ORDER BY rowid DESC LIMIT ?", args).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def relate(self, source_id: str, target_id: str, relation_type: str) -> None:
        relation_type = relation_type.strip().upper()
        if not relation_type or len(relation_type) > 80:
            raise ValueError("relation_type must contain 1-80 characters")
        with self._connect() as db:
            for item in (source_id, target_id):
                if not db.execute("SELECT 1 FROM entries WHERE id=?", (item,)).fetchone():
                    raise KeyError(f"entry not found: {item}")
            db.execute("INSERT OR IGNORE INTO relations VALUES(?,?,?,?)", (source_id, target_id, relation_type, utc_now()))
            self._append_event(db, "RELATION_ADDED", source_id, {"target_id": target_id, "relation_type": relation_type})

    def detect_potential_contradictions(self, entry_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return review candidates, never a claim of semantic contradiction."""
        entry = self.get(entry_id)
        if not entry:
            raise KeyError(f"entry not found: {entry_id}")
        terms = set(re.findall(r"[a-zA-Z0-9_]+", entry.content.lower()))
        terms = {t for t in terms if len(t) > 3}
        candidates = []
        for other in self.list_entries(limit=500):
            if other.id == entry_id:
                continue
            other_terms = set(re.findall(r"[a-zA-Z0-9_]+", other.content.lower()))
            other_terms = {t for t in other_terms if len(t) > 3}
            overlap = len(terms & other_terms) / max(1, len(terms | other_terms))
            if overlap >= 0.25:
                candidates.append({"entry": other.to_dict(), "lexical_overlap": round(overlap, 3), "status": "REVIEW_REQUIRED"})
        return sorted(candidates, key=lambda item: item["lexical_overlap"], reverse=True)[:max(1, min(limit, 100))]

    def verify(self) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        with self._connect() as db:
            events = db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
            previous_hash = "0" * 64
            for event in events:
                expected_signed = canonical_json({
                    "event_id": event["event_id"], "event_type": event["event_type"],
                    "entity_id": event["entity_id"], "payload_json": event["payload_json"],
                    "previous_hash": previous_hash, "created_at": event["created_at"],
                })
                expected_hash = sha256_text(expected_signed)
                if event["previous_hash"] != previous_hash or event["event_hash"] != expected_hash:
                    issues.append({"sequence": event["sequence"], "event_id": event["event_id"], "error": "hash_chain_mismatch"})
                previous_hash = event["event_hash"]
            entries = db.execute("SELECT * FROM entries").fetchall()
            for row in entries:
                expected = sha256_text(canonical_json({
                    "content": row["content"], "epistemic_type": row["epistemic_type"],
                    "confidence": row["confidence"], "provenance": json.loads(row["provenance_json"]),
                    "metadata": json.loads(row["metadata_json"]), "parent_id": row["parent_id"],
                }))
                if expected != row["content_hash"]:
                    issues.append({"entry_id": row["id"], "error": "content_hash_mismatch"})
        return {"ok": not issues, "events_checked": len(events), "entries_checked": len(entries), "issues": issues}

    def export_jsonl(self, path: str | Path) -> int:
        entries = self.list_entries(limit=500)
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            for entry in reversed(entries):
                handle.write(canonical_json(entry.to_dict()) + "\n")
        return len(entries)

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=row["id"], content=row["content"], epistemic_type=EpistemicType(row["epistemic_type"]),
            confidence=row["confidence"], provenance=json.loads(row["provenance_json"]),
            version=row["version"], content_hash=row["content_hash"], created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"]), parent_id=row["parent_id"],
        )
