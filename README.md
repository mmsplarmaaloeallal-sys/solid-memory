# Solid Memory

Local-first, provenance-aware knowledge memory. This repository turns the supplied Python skeleton into a runnable foundation with SQLite persistence, immutable versioned records, a SHA-256 event chain, a CLI, and an MCP stdio server.

## Current implementation

- Epistemic labels: `FACT`, `CLAIM`, `HYPOTHESIS`, `ASSUMPTION`, `UNKNOWN`, `CONTRADICTION`.
- Records carry provenance, confidence, metadata, timestamps, content hashes, and parent-linked revisions.
- SQLite persistence; original records are retained when revised.
- Hash-chain and content-hash integrity verification.
- Keyword search, typed relation storage, JSONL export method.
- CLI plus seven MCP tools: add, search, list, get, revise, contradiction candidates, verify.
- Python 3.10+; standard library only, no API key or runtime dependency.

## Run

```bash
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
python -m pip install -e .
solid-memory add "Experiment E-14 produced result X" --type CLAIM --confidence 0.7 --source experiment:E-14
solid-memory search "experiment result"
solid-memory list
solid-memory verify
```

Without installing, use `python -m solid_memory` in place of `solid-memory`. The default database is `./solid_memory.sqlite3`.

## MCP integration

Run from the repository root:

```bash
SOLID_MEMORY_DB=./solid_memory.sqlite3 python -m solid_memory.mcp_server
```

`mcp.json` contains a generic stdio client configuration. Set the command's working directory to this repository. Local stdio MCP is not automatically callable from ChatGPT mobile or a hosted ChatGPT plugin. Remote use requires deploying a secured network service and connecting a compatible host.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Mapping to the architecture diagram

| Diagram layer | Status in this release |
|---|---|
| Master Corpus | Implemented with SQLite `entries` |
| Epistemic Registry | Implemented labels and filtering; classification heuristic is deliberately conservative |
| Evidence and Provenance | Stored with every record |
| Lineage / Versioned Core | Parent-linked revisions; originals preserved |
| Integrity and Provenance | Content hashes and event hash chain |
| Knowledge Graph | Relation table/API foundation; advanced graph reasoning pending |
| RAG Power Grid | Keyword retrieval only; embeddings, vector store, hot/warm/cold tiers pending |
| Input Firewall | Basic validation and safe parameterized SQL; source trust scoring and injection detection pending |
| Governance / Release Firewall | Human review workflow and policy enforcement pending |
| Evolution / Meta-evolution | Not implemented yet |
| Trio Intelligence Mesh, chaos and adversarial testing | Not implemented yet |

The architecture diagram is the target design, not a claim that every box already exists in code.

## Integrity and epistemic limits

The hash chain detects edits against the recorded chain; it is not a digital signature and cannot prevent someone with full database control from rewriting the whole chain. Back up the database.

Classification labels do not prove truth. The default classifier assigns `CLAIM`; potential contradiction search returns review candidates based on lexical overlap, not verified semantic contradictions. Human or independent verification remains necessary.

## License

MIT
