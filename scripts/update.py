#!/usr/bin/env python3
"""Refresh official research-link catalog and dataset manifests; no raw file mirroring."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE = 8 * 1024 * 1024
HEADERS = {"User-Agent": "aieco-indexer/0.1 (+https://github.com/XXXDDD/aieco)", "Accept": "text/html, application/json"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_if_changed(path: Path, value: dict) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
    return True


def fetch_text(url: str) -> str:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=35) as response:
        final_host = urlsplit(response.geturl()).hostname or ""
        if final_host not in {"openai.com", "www.openai.com", "www.anthropic.com", "anthropic.com", "huggingface.co"}:
            raise ValueError("Unexpected redirect destination: " + final_host)
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("Source exceeds safety size limit: " + url)
        return data.decode("utf-8", errors="replace")


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.active: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "a" and self.active is None:
            href = dict(attrs).get("href")
            if href:
                self.active = {"href": href, "parts": []}

    def handle_data(self, data):
        if self.active is not None:
            self.active["parts"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            value = self.active
            self.links.append((value["href"], " ".join(" ".join(value["parts"]).split())))
            self.active = None


def parse_links(markup: str) -> list[tuple[str, str]]:
    parser = AnchorParser()
    parser.feed(markup)
    return parser.links


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def permitted_research_url(provider: str, url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path.lower()
    if parts.scheme != "https":
        return False
    if provider == "anthropic":
        return host in {"anthropic.com", "www.anthropic.com"} and path.startswith("/research/") and not path.startswith("/research/team/")
    if provider == "openai":
        return host in {"openai.com", "www.openai.com"} and path.startswith("/index/")
    return False


def discover(provider: str, source_url: str, markup: str) -> list[dict]:
    found = {}
    for href, text in parse_links(markup):
        url = canonical_url(urljoin(source_url, html.unescape(href)))
        if not permitted_research_url(provider, url):
            continue
        title = " ".join(text.split()).strip()
        if len(title) < 12 or title.lower() in {"read more", "learn more", "view more"}:
            continue
        title = re.split(r"\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b", title, maxsplit=1)[0]
        title = title[:180].strip()
        if not title:
            continue
        found[url] = {"url": url, "title": title}
    return list(found.values())



def discover_openai_rss(markup: str) -> list[dict]:
    """Read OpenAI's official RSS without scraping blocked HTML pages.

    Research articles are kept; AI Adoption posts need explicit
    empirical/economic keywords. RSS publication timestamps come from OpenAI.
    """
    root = ET.fromstring(markup)
    if root.tag != "rss":
        raise ValueError("Unexpected OpenAI RSS document root")
    result = {}
    adoption_terms = re.compile(
        r"\b(research|report|study|survey|dataset|data|econom(?:y|ic|ics)|"
        r"employment|labor|labour|productiv\w*|adoption|usage|workforce|jobs?)\b",
        re.IGNORECASE,
    )
    for item in root.findall("./channel/item"):
        title = " ".join((item.findtext("title") or "").split())
        url = canonical_url((item.findtext("link") or "").strip())
        category = (item.findtext("category") or "").strip()
        if not permitted_research_url("openai", url) or not title:
            continue
        if category.casefold() != "research" and not (
            category.casefold() == "ai adoption" and adoption_terms.search(title)
        ):
            continue
        date_value = None
        raw_date = item.findtext("pubDate")
        if raw_date:
            try:
                date_value = parsedate_to_datetime(raw_date).date().isoformat()
            except (TypeError, ValueError, IndexError):
                pass
        result[url] = {
            "url": url,
            "title": title[:180],
            "published_at": date_value,
            "topics": ["research"] if category.casefold() == "research" else ["adoption"],
        }
    if not result:
        raise ValueError("No relevant entries in official OpenAI RSS feed")
    return list(result.values())


def cdn_head_manifest(source: dict) -> dict:
    """Track immutable-ish asset identifiers without mirroring binary files."""
    assets = source.get("assets") or []
    if not assets:
        raise ValueError("Missing registered OpenAI CDN assets")
    records = []
    for asset in assets:
        url = asset["url"]
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != "cdn.openai.com":
            raise ValueError("Untrusted OpenAI asset hostname: " + url)
        request = Request(url, headers=HEADERS, method="HEAD")
        with urlopen(request, timeout=35) as response:
            if urlsplit(response.geturl()).hostname != "cdn.openai.com":
                raise ValueError("Unexpected OpenAI CDN redirect: " + response.geturl())
            size = response.headers.get("Content-Length")
            records.append({
                "label": asset["label"],
                "url": url,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "content_length": int(size) if size and size.isdigit() else None,
            })
    return {
        "schema_version": 1,
        "id": source["id"],
        "provider": "openai",
        "homepage": source["homepage"],
        "license": source["license"],
        "monitoring": "Official CDN HEAD ETag, Last-Modified and Content-Length (not a content hash)",
        "files": sorted(records, key=lambda r: r["url"]),
    }


def update_catalog(registry: dict) -> tuple[int, list[str]]:
    path = ROOT / "research/catalog.json"
    catalog = read_json(path)
    existing = {canonical_url(row["url"]) for row in catalog["records"]}
    new_records = []
    errors = []
    for source in registry["research_pages"]:
        try:
            markup = fetch_text(source["url"])
            candidates = (discover_openai_rss(markup) if source.get("kind") == "rss"
                          else discover(source["provider"], source["url"], markup))
            if not candidates:
                raise ValueError("No usable research links; layout may have changed")
            for item in candidates:
                if item["url"] in existing:
                    continue
                existing.add(item["url"])
                digest = hashlib.sha256(item["url"].encode()).hexdigest()[:12]
                new_records.append({
                    "id": source["provider"] + "-" + digest,
                    "provider": source["provider"],
                    "title": item["title"],
                    "url": item["url"],
                    "published_at": item.get("published_at"),
                    "topics": item.get("topics", []),
                    "description": "",
                    "source": "discovered:" + source["id"],
                    "dataset_ids": [],
                })
            print(f"[research] {source['id']}: {len(candidates)} links, {len(new_records)} new in aggregate")
        except Exception as exc:
            errors.append(f"{source['id']}: {exc}")
    if new_records:
        catalog["records"].extend(sorted(new_records, key=lambda row: (row["provider"], row["url"])))
        write_if_changed(path, catalog)
    return len(new_records), errors


def openai_manifest(source: dict, markup: str) -> dict:
    terms = ("download csv files", "data dictionary", "download data for the ai jobs")
    assets = {}
    for href, label in parse_links(markup):
        url = canonical_url(urljoin(source["url"], html.unescape(href)))
        host = urlsplit(url).hostname or ""
        if host != "cdn.openai.com" or not any(term in label.casefold() for term in terms):
            continue
        assets[url] = {"label": label, "url": url}
    if not assets:
        raise ValueError("No official dataset links found on OpenAI download page")
    return {
        "schema_version": 1,
        "id": source["id"], "provider": "openai",
        "homepage": source["homepage"], "license": source["license"],
        "monitoring": "URL changes only (upstream content at a stable URL is not checksummed)",
        "files": sorted(assets.values(), key=lambda row: row["url"]),
    }


def huggingface_manifest(source: dict, payload: dict) -> dict:
    revision = payload.get("sha")
    siblings = payload.get("siblings")
    if not isinstance(revision, str) or len(revision) < 12 or not isinstance(siblings, list):
        raise ValueError("Missing Hugging Face revision or file listing")
    paths = sorted(x["rfilename"] for x in siblings if isinstance(x, dict) and isinstance(x.get("rfilename"), str))
    return {
        "schema_version": 1,
        "id": source["id"], "provider": "anthropic", "homepage": source["homepage"],
        "license": source["license"], "revision": revision, "file_count": len(paths),
        "files": paths[:500], "files_truncated": len(paths) > 500,
        "monitoring": "Hugging Face repository SHA and file listing; content not mirrored",
    }


def update_datasets(registry: dict) -> tuple[int, list[str]]:
    updated = 0
    errors = []
    for source in registry["datasets"]:
        try:
            if source["kind"] == "cdn-head":
                manifest = cdn_head_manifest(source)
            elif source["kind"] == "openai-links":
                body = fetch_text(source["url"])
                manifest = openai_manifest(source, body)
            elif source["kind"] == "huggingface":
                manifest = huggingface_manifest(source, json.loads(fetch_text(source["url"])))
            else:
                raise ValueError("Unsupported source kind")
            path = ROOT / "data/manifests" / (source["id"] + ".json")
            if write_if_changed(path, manifest):
                updated += 1
            print(f"[dataset] {source['id']}: checked")
        except Exception as exc:
            errors.append(f"{source['id']}: {exc}")
    return updated, errors


def classify_source_errors(errors: list[str], registry: dict) -> tuple[list[str], list[str]]:
    """OpenAI returning HTTP 403 on CI is degraded coverage, not a GitHub auth failure.

    Keep all unexpected exceptions and other provider failures fatal rather than
    treating an incomplete catalog as completely healthy.
    """
    openai_ids = {
        source["id"]
        for source in registry["research_pages"] + registry["datasets"]
        if source["provider"] == "openai"
    }
    warnings, failures = [], []
    for error in errors:
        source_id = error.partition(": ")[0]
        if source_id in openai_ids and "HTTP Error 403" in error:
            warnings.append(error)
        else:
            failures.append(error)
    return warnings, failures


def write_github_summary(new: int, changed: int, warnings: list[str], failures: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        "## aieco upstream update",
        f"- New research records: **{new}**",
        f"- Changed dataset manifests: **{changed}**",
        f"- Source coverage: **{'degraded' if warnings or failures else 'complete'}**",
    ]
    if warnings:
        lines += ["", "### Inaccessible sources (retaining existing records)"]
        lines += [f"- {error}" for error in warnings]
        lines += ["", "OpenAI returned HTTP 403 to this runner. Existing entries are preserved; "
                  "this run **did not verify freshness** of the blocked sources."]
    if failures:
        lines += ["", "### Fatal upstream errors"]
        lines += [f"- {error}" for error in failures]
    with open(path, "a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


def main() -> int:
    registry = read_json(ROOT / "sources/registry.json")
    new, research_errors = update_catalog(registry)
    changed, dataset_errors = update_datasets(registry)
    print(f"New research: {new}; changed manifests: {changed}")
    warnings, failures = classify_source_errors(research_errors + dataset_errors, registry)
    for warning in warnings:
        print("WARNING: source unavailable; preserved existing catalog: " + warning, file=sys.stderr)
    for error in failures:
        print("ERROR: " + error, file=sys.stderr)
    write_github_summary(new, changed, warnings, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
