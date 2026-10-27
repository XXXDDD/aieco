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
