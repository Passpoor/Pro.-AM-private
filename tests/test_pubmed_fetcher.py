import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pubmed_fetcher as monitor


class StateTests(unittest.TestCase):
    def test_migrates_legacy_sent_pmids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"sent_pmids": ["1", "2"]}), encoding="utf-8")
            state = monitor.load_state(path)
        self.assertEqual(state["version"], 2)
        self.assertEqual(state["papers"]["1"]["status"], "delivered")

    def test_save_state_is_atomic_and_round_trips(self):
        state = {"version": 2, "papers": {"1": {"status": "pending"}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            monitor.save_state(path, state)
            self.assertEqual(
                monitor.load_state(path)["papers"]["1"]["status"], "pending"
            )
            self.assertFalse(path.with_suffix(".json.tmp").exists())


class PipelineTests(unittest.TestCase):
    def test_delivery_failure_persists_pending_without_marking_delivered(self):
        article = {
            "pmid": "123",
            "title": "Example",
            "abstract": "Abstract",
            "journal": "Journal",
        }
        enriched = {
            **article,
            "title_zh": "示例",
            "abstract_zh": "摘要",
            "authors": "A",
            "date": "2026",
            "rank": {},
            "insight": {},
        }
        config = types.SimpleNamespace(
            TOPICS=[{"name_zh": "CAR-M", "max_results": 30}],
            RECENT_DAYS=7,
            MAX_BACKFILL_DAYS=90,
            SENDER_EMAIL="sender@example.com",
        )
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            with (
                patch.dict(os.environ, {"STATE_FILE": str(state_path)}, clear=False),
                patch("pubmed_fetcher.GoogleTranslator"),
                patch("pubmed_fetcher.discover_topic", return_value=["123"]),
                patch("pubmed_fetcher.fetch_details", return_value=([article], set())),
                patch("pubmed_fetcher.enrich_article", return_value=enriched),
                patch(
                    "pubmed_fetcher.send_email", side_effect=RuntimeError("SMTP failed")
                ),
                patch("pubmed_fetcher.importlib.import_module", return_value=config),
                self.assertRaisesRegex(RuntimeError, "SMTP failed"),
            ):
                monitor.run("fake_config", False, None, Path("unused.html"))
            state = monitor.load_state(state_path)
        self.assertEqual(state["papers"]["123"]["status"], "pending")

    @patch("pubmed_fetcher.Entrez.efetch")
    def test_medline_parser_preserves_repeated_authors(self, efetch):
        efetch.return_value = io.StringIO(
            "PMID- 123\nTI  - Example paper.\nAB  - Example abstract.\n"
            "TA  - Test J\nDP  - 2026 Aug\nAU  - Alpha A\nAU  - Beta B\n\n"
        )
        articles, unavailable = monitor.fetch_details(["123"])
        self.assertEqual(unavailable, set())
        self.assertEqual(articles[0]["authors"], "Alpha A, Beta B")

    @patch("pubmed_fetcher.search_pubmed")
    def test_fallback_runs_when_primary_has_no_new_papers(self, search):
        search.side_effect = [["known"], ["fresh"]]
        topic = {"query": "primary", "fallback_query": "broad", "max_results": 30}
        self.assertEqual(monitor.discover_topic(topic, 7, {"known"}), ["fresh"])
        self.assertEqual(search.call_count, 2)

    @patch("pubmed_fetcher.search_pubmed", return_value=["fresh"])
    def test_fallback_does_not_run_when_primary_has_new_paper(self, search):
        topic = {"query": "primary", "fallback_query": "broad", "max_results": 30}
        self.assertEqual(monitor.discover_topic(topic, 7, set()), ["fresh"])
        search.assert_called_once()

    def test_email_html_escapes_untrusted_content(self):
        article = {
            "pmid": "1",
            "title": "<script>x</script>",
            "title_zh": "标题",
            "abstract_zh": "摘要",
            "journal": "Journal",
            "date": "2026",
            "authors": "A",
            "rank": {},
            "insight": {},
        }
        rendered = monitor.build_email_html([article], 7)
        self.assertNotIn("<script>x</script>", rendered)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", rendered)

    def test_journal_rank_is_disabled_without_key(self):
        self.assertEqual(monitor.get_journal_rank("Nature", ""), {})

    def test_evidence_sentences_are_rendered_and_escaped(self):
        rendered = monitor.insight_html(
            {
                "relevance_score": 8,
                "evidence_sentences": ["CAR-M <improved> survival."],
            }
        )
        self.assertIn("摘要证据", rendered)
        self.assertIn("CAR-M &lt;improved&gt; survival.", rendered)


if __name__ == "__main__":
    unittest.main()
