import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import query, update, validate


class CatalogTests(unittest.TestCase):
    def test_openai_discovery_and_navigation_exclusion(self):
        markup = '<a href="/index/chatgpt-expanding-world-of-work/">ChatGPT’s expanding world of work</a>' \
                 '<a href="/research">Research index</a>' \
                 '<a href="/index/another-research/">Another economics research report</a>'
        items = update.discover("openai", "https://openai.com/signals/", markup)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["url"].startswith("https://openai.com/index/") for item in items))

    def test_anthropic_discovery(self):
        markup = '<a href="/research/team/economics">Economics team</a>' \
                 '<a href="/research/labor-market-impacts"><span>Labor market impacts of AI</span></a>'
        items = update.discover("anthropic", "https://www.anthropic.com/research/team/economics", markup)
        self.assertEqual([i["title"] for i in items], ["Labor market impacts of AI"])

    def test_official_rss_only_admits_research_and_evidence_based_adoption(self):
        rss = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>AI and job productivity study</title><link>https://openai.com/index/jobs-productivity-study/</link><pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate><category>Research</category></item>
<item><title>Introducing a new model</title><link>https://openai.com/index/introducing-new-model</link><category>Product</category></item>
<item><title>Examining AI adoption data</title><link>https://openai.com/index/ai-adoption-data</link><category>AI Adoption</category></item>
<item><title>A company customer story</title><link>https://openai.com/index/customer-story</link><category>AI Adoption</category></item>
</channel></rss>"""
        records = update.discover_openai_rss(rss)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["published_at"], "2026-10-26")
        self.assertEqual(records[0]["topics"], ["research"])
        self.assertEqual(records[1]["topics"], ["adoption"])

    def test_cdn_head_uses_official_host_and_records_revision_headers(self):
        source = {"id": "test", "provider": "openai", "homepage": "https://openai.com/signals/data-download/",
                  "license": "CC-BY-4.0", "assets": [{"label": "Data", "url": "https://cdn.openai.com/signals/data-dictionary.pdf"}]}
        class FakeResponse:
            headers = {"Content-Length": "123", "ETag": "abc", "Last-Modified": "Tue, 27 Oct 2026 00:00:00 GMT"}
            def geturl(self):
                return "https://cdn.openai.com/signals/data-dictionary.pdf"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        with patch.object(update, "urlopen", return_value=FakeResponse()):
            manifest = update.cdn_head_manifest(source)
        self.assertEqual(manifest["files"][0]["etag"], "abc")
        self.assertEqual(manifest["files"][0]["content_length"], 123)
        source["assets"][0]["url"] = "https://example.com/fake.pdf"
        with self.assertRaises(ValueError):
            update.cdn_head_manifest(source)

    def test_manifests(self):
        markup = '<a href="https://cdn.openai.com/something.zip">Download CSV files of the data</a>'
        src = {"id": "test", "url": "https://openai.com/signals/data-download/", "homepage": "https://openai.com/signals/data-download/", "license": "CC-BY-4.0"}
        self.assertEqual(len(update.openai_manifest(src, markup)["files"]), 1)
        src2 = {"id": "hf", "homepage": "https://huggingface.co/datasets/Anthropic/EconomicIndex", "license": "MIT"}
        hf = update.huggingface_manifest(src2, {"sha": "a" * 40, "siblings": [{"rfilename": "b.csv"}, {"rfilename": "a.csv"}]})
        self.assertEqual(hf["files"], ["a.csv", "b.csv"])

    def test_query_ranking(self):
        rows = [{"id": "a", "title": "AI labor", "topics": [], "description": "", "provider": "openai"},
                {"id": "b", "title": "Research", "topics": ["labor"], "description": "", "provider": "anthropic"}]
        self.assertEqual(query.search(rows, ["labor"])[0]["id"], "a")

    def test_atomic_noop_diff(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "index.json"
            self.assertTrue(update.write_if_changed(path, {"a": 1}))
            self.assertFalse(update.write_if_changed(path, {"a": 1}))

    def test_openai_403_degrades_but_other_source_failures_remain_fatal(self):
        registry = {
            "research_pages": [
                {"id": "openai-signals", "provider": "openai"},
                {"id": "anthropic-economics", "provider": "anthropic"},
            ],
            "datasets": [{"id": "openai-signals-v3", "provider": "openai"}],
        }
        warnings, failures = update.classify_source_errors(
            [
                "openai-signals: HTTP Error 403: Forbidden",
                "openai-signals-v3: HTTP Error 403: Forbidden",
                "anthropic-economics: HTTP Error 500: Internal Server Error",
                "openai-signals: No usable research links",
            ],
            registry,
        )
        self.assertEqual(len(warnings), 2)
        self.assertEqual(len(failures), 2)

    def test_degraded_run_summary_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "summary.md"
            with patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(path)}):
                update.write_github_summary(
                    17, 1, ["openai-signals: HTTP Error 403: Forbidden"], []
                )
            summary = path.read_text(encoding="utf-8")
            self.assertIn("degraded", summary)
            self.assertIn("did not verify freshness", summary)

    def test_project_catalog_is_valid(self):
        self.assertGreaterEqual(validate.validate(), 5)


if __name__ == "__main__":
    unittest.main()
