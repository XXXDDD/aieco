#!/usr/bin/env python3
"""Offline schema and provenance checks for aieco catalog and manifests."""
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def https_url(value):
    return isinstance(value, str) and urlsplit(value).scheme == "https" and bool(urlsplit(value).hostname)


def validate(root=ROOT):
    registry = json.loads((root / "sources/registry.json").read_text(encoding="utf-8"))
    catalog = json.loads((root / "research/catalog.json").read_text(encoding="utf-8"))
    check(registry.get("schema_version") == 1 and catalog.get("schema_version") == 1, "Unsupported schema")
    ids = set()
    for source in registry["research_pages"] + registry["datasets"]:
        check(source["id"] not in ids, "Duplicate source ID: " + source["id"])
        ids.add(source["id"])
        check(source["provider"] in ("openai", "anthropic") and https_url(source["url"]), "Bad registered source")
    dataset_ids = {x["id"] for x in registry["datasets"]}
    record_ids, urls = set(), set()
    for row in catalog["records"]:
        check(isinstance(row["id"], str) and row["id"] not in record_ids, "Bad or duplicate record ID")
        record_ids.add(row["id"])
        url = row["url"].rstrip("/")
        check(https_url(url) and url not in urls, "Bad or duplicate research URL")
        urls.add(url)
        check(row["provider"] in ("openai", "anthropic"), "Bad research provider")
        check(isinstance(row["title"], str) and len(row["title"]) >= 8, "Missing title")
        check(isinstance(row.get("description"), str), "Missing description")
        check(isinstance(row["topics"], list) and all(isinstance(x, str) for x in row["topics"]), "Invalid topics")
        check(all(x in dataset_ids for x in row["dataset_ids"]), "Unknown associated dataset")
        if row["published_at"] is not None:
            date.fromisoformat(row["published_at"])
    for path in (root / "data/manifests").glob("*.json") if (root / "data/manifests").exists() else []:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        check(manifest["id"] in dataset_ids and manifest["schema_version"] == 1, "Unregistered dataset manifest")
    skill = (root / "skills/research-explorer/SKILL.md").read_text(encoding="utf-8")
    check(skill.startswith("---\n") and "\nname: research-explorer\n" in skill and "\ndescription:" in skill, "Invalid skill metadata")
    return len(record_ids)


if __name__ == "__main__":
    print(f"Validated {validate()} research records")
