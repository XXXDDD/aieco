#!/usr/bin/env python3
"""Search local curated research catalog; not full-text document search."""
import argparse
import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "research/catalog.json"


def search(records, words):
    ranked = []
    for row in records:
        title = row["title"].casefold()
        topics = " ".join(row["topics"]).casefold()
        details = (row["description"] + " " + row["provider"]).casefold()
        score = sum((4 if word in title else 0) + (3 if word in topics else 0) + (1 if word in details else 0) for word in words)
        if score > 0 or not words:
            ranked.append((score, row))
    return [row for _, row in sorted(ranked, key=lambda x: (-x[0], x[1]["id"]))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("keywords", nargs="*", help="One or more search terms")
    parser.add_argument("--json", action="store_true", help="Machine-readable results")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    records = json.loads(CATALOG.read_text(encoding="utf-8"))["records"]
    result = search(records, [s.casefold() for arg in args.keywords for s in arg.split()])[:args.limit]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for row in result:
            print(f"{row['provider']} | {row['published_at'] or 'date unknown'} | {row['title']}\n  {row['url']}")
        if not result:
            print("No matches. Try broader terms or search the original source sites.")


if __name__ == "__main__":
    main()
