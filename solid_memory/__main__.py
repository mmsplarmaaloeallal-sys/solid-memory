"""CLI entry point: python -m solid_memory."""
import argparse
import json
from .core import EpistemicType, SolidMemory


def main() -> None:
    parser = argparse.ArgumentParser(prog="solid-memory", description="Local provenance-aware knowledge store")
    parser.add_argument("--db", default="solid_memory.sqlite3", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="preserve a knowledge item")
    add.add_argument("content")
    add.add_argument("--type", choices=[e.value for e in EpistemicType])
    add.add_argument("--confidence", type=float, default=0.5)
    add.add_argument("--source", default="cli")
    search = sub.add_parser("search", help="search knowledge")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    listing = sub.add_parser("list", help="list recent knowledge")
    listing.add_argument("--limit", type=int, default=50)
    sub.add_parser("verify", help="verify stored integrity")
    args = parser.parse_args()
    store = SolidMemory(args.db)
    if args.command == "add":
        result = store.add(args.content, args.type, args.confidence, {"source_type": args.source})
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "search":
        print(json.dumps([e.to_dict() for e in store.search(args.query, args.limit)], ensure_ascii=False, indent=2))
    elif args.command == "list":
        print(json.dumps([e.to_dict() for e in store.list_entries(args.limit)], ensure_ascii=False, indent=2))
    elif args.command == "verify":
        result = store.verify()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
