#!/usr/bin/env python3
"""Unit tests for shared URL / credential helpers."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "chatbot"))

from docs_urls import (
    extract_brand,
    is_placeholder_api_key,
    is_placeholder_collector,
    is_specific_docs_page,
    is_studio_ready,
    normalize_page_url,
    normalize_url,
    url_path_query_terms,
)
from rag import chunk_relevance_score, synthesize_local_answer


class DocsUrlTests(unittest.TestCase):
    def test_normalize_adds_https(self):
        self.assertEqual(normalize_url("expressjs.com/en/guide/"), "https://expressjs.com/en/guide/")

    def test_normalize_page_url_strips_slash_and_fragment(self):
        self.assertEqual(
            normalize_page_url("https://ExpressJS.com/en/5x/guide/behind-proxies/#note"),
            "https://expressjs.com/en/5x/guide/behind-proxies",
        )

    def test_brand_from_docs_host(self):
        self.assertEqual(extract_brand("https://expressjs.com/en/5x/guide/behind-proxies/"), "Expressjs")
        self.assertEqual(extract_brand("https://duckdb.org/docs/"), "Duckdb")

    def test_specific_page_vs_docs_root(self):
        self.assertTrue(is_specific_docs_page("https://expressjs.com/en/5x/guide/behind-proxies/"))
        self.assertFalse(is_specific_docs_page("https://duckdb.org/docs/"))
        self.assertFalse(is_specific_docs_page("https://duckdb.org/docs/current/"))

    def test_path_terms_include_slug(self):
        terms = url_path_query_terms("https://expressjs.com/en/5x/guide/behind-proxies/")
        self.assertIn("behind", terms)
        self.assertIn("proxies", terms)

    def test_placeholder_credentials_are_not_studio_ready(self):
        self.assertTrue(is_placeholder_api_key("your_brightdata_api_key_here"))
        self.assertTrue(is_placeholder_collector("c_your_collector_id_here"))
        self.assertFalse(is_studio_ready("c_your_collector_id_here", "your_brightdata_api_key_here"))
        self.assertTrue(is_studio_ready("c_mt2z0drp1irsde3ydk", "real-looking-key-not-placeholder"))


class RagRankTests(unittest.TestCase):
    def test_posted_page_outranks_sibling_docs(self):
        target = "https://expressjs.com/en/5x/guide/behind-proxies/"
        proxy_score = chunk_relevance_score(
            "tell me about the function in it",
            "Custom trust implementation. app.set('trust proxy', (ip) => true)",
            url=target,
            target_url=target,
        )
        debug_score = chunk_relevance_score(
            "tell me about the function in it",
            "Using debug in your own code. const debug = require('debug')('myapp')",
            url="https://expressjs.com/en/5x/guide/debugging/",
            target_url=target,
        )
        self.assertGreater(proxy_score, debug_score)

    def test_local_answer_cites_target_page(self):
        target = "https://expressjs.com/en/5x/guide/behind-proxies/"
        answer = synthesize_local_answer(
            "tell me about the function in it",
            [
                {
                    "title": "Debugging Express",
                    "url": "https://expressjs.com/en/5x/guide/debugging/",
                    "text": "Using debug in your own code. Install the debug module and call it instead of console.log.",
                },
                {
                    "title": "Express behind proxies",
                    "url": target,
                    "text": "The trust proxy Function type is a custom trust implementation. "
                    "app.set('trust proxy', (ip) => { return ip === '127.0.0.1'; }); "
                    "This callback decides whether a hop is trusted.",
                },
            ],
            target_url=target,
        )
        self.assertIn("behind proxies", answer.lower())
        self.assertIn(target, answer)
        self.assertNotIn("Debugging Express ·", answer)


if __name__ == "__main__":
    unittest.main()
