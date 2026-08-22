#!/usr/bin/env python3
"""Chroma query helper must pass embeddings, never query_texts."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from chunk_and_embed import query_collection


class FakeCollection:
    def __init__(self):
        self.kwargs = None

    def query(self, **kwargs):
        self.kwargs = kwargs
        return {"documents": [["ok"]], "metadatas": [[{"url": "https://example.com"}]]}


class QueryCollectionTests(unittest.TestCase):
    def test_uses_query_embeddings_not_texts(self):
        collection = FakeCollection()
        with patch("chunk_and_embed.embed_texts", return_value=[[0.1, 0.2, 0.3]]):
            result = query_collection(
                collection,
                "how do I install duckdb?",
                where={"competitor": "Duckdb"},
                n_results=3,
            )
        self.assertIn("ok", result["documents"][0])
        self.assertIn("query_embeddings", collection.kwargs)
        self.assertNotIn("query_texts", collection.kwargs)
        self.assertEqual(collection.kwargs["where"], {"competitor": "Duckdb"})
        self.assertEqual(collection.kwargs["n_results"], 3)


if __name__ == "__main__":
    unittest.main()
