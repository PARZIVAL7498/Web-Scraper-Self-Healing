#!/usr/bin/env python3
"""Health-check tests: empty extract fails; same-domain prose passes."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from health_check import check_health


class HealthCheckTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, pages: list) -> Path:
        path = directory / name
        path.write_text(json.dumps(pages), encoding="utf-8")
        return path

    def test_empty_content_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest = self._write(
                Path(tmp),
                "latest.json",
                [{"url": "https://duckdb.org/docs/", "title": "Docs", "content": ""}],
            )
            baseline = self._write(Path(tmp), "base.json", [])
            ok, reason, _ = check_health(latest, baseline)
            self.assertFalse(ok)
            self.assertIn("empty", reason.lower())

    def test_prose_pages_pass(self):
        page = {
            "url": "https://expressjs.com/en/5x/guide/behind-proxies/",
            "title": "Express behind proxies",
            "content": "When running an Express app behind a reverse proxy, set trust proxy. " * 4,
        }
        with tempfile.TemporaryDirectory() as tmp:
            latest = self._write(Path(tmp), "latest.json", [page])
            baseline = self._write(Path(tmp), "base.json", [page])
            ok, reason, data = check_health(latest, baseline)
            self.assertTrue(ok, reason)
            self.assertEqual(len(data), 1)


if __name__ == "__main__":
    unittest.main()
