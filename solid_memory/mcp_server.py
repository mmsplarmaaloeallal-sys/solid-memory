"""Minimal stdio MCP server for Solid Memory; standard library only.

Run: python -m solid_memory.mcp_server
This implements the core JSON-RPC methods used by MCP clients: initialize,
notifications/initialized, tools/list, and tools/call.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any

from .core import EpistemicType, SolidMemory

STORE = SolidMemory(os.environ.get("SOLID_MEMORY_DB", "solid_memory.sqlite3"))


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {"name":"memory_add","description":"Preserve a knowledge item with epistemic type, confidence and provenance.","inputSchema":{"type":"object","properties":{"content":{"type":"string"},"epistemic_type":{"type":"string","enum":[e.value for e in EpistemicType]},"confidence":{"type":"number","minimum":0,"maximum":1},"provenance":{"type":"object"},"metadata":{"type":"object"}},"required":["content"]}},
        {"name":"memory_search","description":"Search preserved knowledge by words. Results include provenance and integrity hashes.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":200}},"required":["query"]}},
        {"name":"memory_list","description":"List recent knowledge records, optionally filtered by epistemic type.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":500},"epistemic_type":{"type":"string","enum":[e.value for e in EpistemicType]}}}},
        {"name":"memory_get","description":"Retrieve a knowledge record by ID.","inputSchema":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"]}},
        {"name":"memory_revise","description":"Create a new version linked to an existing record; original remains preserved.","inputSchema":{"type":"object","properties":{"id":{"type":"string"},"content":{"type":"string"},"epistemic_type":{"type":"string","enum":[e.value for e in EpistemicType]},"confidence":{"type":"number","minimum":0,"maximum":1}},"required":["id","content"]}},
        {"name":"memory_contradiction_candidates","description":"Find lexical-overlap candidates for human contradiction review; does not assert a contradiction.","inputSchema":{"type":"object","properties":{"id":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":100}},"required":["id"]}},
        {"name":"memory_verify","description":"Verify stored content hashes and the append-only event hash chain.","inputSchema":{"type":"object","properties":{}}},
    ]


def call_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "memory_add":
        entry = STORE.add(args["content"], args.get("epistemic_type"), args.get("confidence", 0.5), args.get("provenance"), args.get("metadata"))
        return entry.to_dict()
    if name == "memory_search":
        return [e.to_dict() for e in STORE.search(args["query"], args.get("limit", 20))]
    if name == "memory_list":
        return [e.to_dict() for e in STORE.list_entries(args.get("limit", 50), args.get("epistemic_type"))]
    if name == "memory_get":
        entry = STORE.get(args["id"])
        return entry.to_dict() if entry else {"found": False, "id": args["id"]}
    if name == "memory_revise":
        changes = {k: args[k] for k in ("epistemic_type", "confidence") if k in args}
        return STORE.revise(args["id"], args["content"], **changes).to_dict()
    if name == "memory_contradiction_candidates":
        return STORE.detect_potential_contradictions(args["id"], args.get("limit", 20))
    if name == "memory_verify":
        return STORE.verify()
    raise ValueError(f"Unknown tool: {name}")


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle(message: dict[str, Any]) -> None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return
    if method == "initialize":
        send({"jsonrpc":"2.0","id":request_id,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"solid-memory","version":"0.1.0"}}})
        return
    if method == "ping":
        send({"jsonrpc":"2.0","id":request_id,"result":{}})
        return
    if method == "tools/list":
        send({"jsonrpc":"2.0","id":request_id,"result":{"tools":tool_definitions()}})
        return
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            result = call_tool(params.get("name", ""), params.get("arguments") or {})
            send({"jsonrpc":"2.0","id":request_id,"result":{"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False,indent=2)}],"structuredContent":result,"isError":False}})
        except Exception as exc:
            send({"jsonrpc":"2.0","id":request_id,"result":{"content":[{"type":"text","text":f"{type(exc).__name__}: {exc}"}],"isError":True}})
        return
    if request_id is not None:
        send({"jsonrpc":"2.0","id":request_id,"error":{"code":-32601,"message":f"Method not found: {method}"}})


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if isinstance(message, dict):
                handle(message)
        except Exception as exc:
            # Keep protocol stdout clean; diagnostics go to stderr.
            print(f"Solid Memory protocol error: {exc}", file=sys.stderr)
            if os.environ.get("SOLID_MEMORY_DEBUG"):
                traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
