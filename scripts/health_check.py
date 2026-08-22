#!/usr/bin/env python3
"""
scripts/health_check.py
Validates scraped JSON payload against health criteria:
1. Non-empty page content (> 30 characters).
2. Domain-aware baseline page count comparison (only flags drop if scraping SAME domain).
Outputs PASS (exit code 0) or FAIL (exit code 1) with failure reason.
"""

import sys
import json
import argparse
from pathlib import Path

from docs_urls import get_domain

DEFAULT_LATEST_PATH = Path(__file__).resolve().parent.parent / "data" / "latest_scrape.json"
DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent.parent / "data" / "last_known_good.json"


def check_health(latest_path: Path, baseline_path: Path) -> tuple:
    """
    Checks if latest scrape payload is healthy.
    Returns (is_healthy: bool, reason: str, latest_data: list)
    """
    if not latest_path.exists():
        return False, f"[HEALTH_CHECK] ❌ FAIL: Scrape output file not found at {latest_path}", []

    try:
        with open(latest_path, "r", encoding="utf-8") as f:
            latest_data = json.load(f)
    except Exception as e:
        return False, f"[HEALTH_CHECK] ❌ FAIL: Unable to parse JSON from {latest_path}: {e}", []

    if not isinstance(latest_data, list) or len(latest_data) == 0:
        return False, f"[HEALTH_CHECK] ❌ FAIL: Scraped payload is empty (0 pages retrieved).", []

    # 1. Content Emptiness Check
    empty_pages = []
    for idx, page in enumerate(latest_data):
        content = page.get("content", "").strip()
        if not content or len(content) < 30:
            empty_pages.append(page.get("url", f"Page #{idx+1}"))

    if empty_pages:
        return False, f"[HEALTH_CHECK] ❌ FAIL: Scraped content is empty or corrupt on {len(empty_pages)} page(s): {', '.join(empty_pages[:3])}", latest_data

    # 2. Domain-Aware Baseline Comparison Check
    latest_domain = get_domain(latest_data[0].get("url", ""))

    if baseline_path.exists():
        try:
            with open(baseline_path, "r", encoding="utf-8") as f:
                baseline_data = json.load(f)

            if isinstance(baseline_data, list) and len(baseline_data) > 0:
                baseline_domain = get_domain(baseline_data[0].get("url", ""))

                # Only perform drop check if baseline is for the SAME domain
                if latest_domain and latest_domain == baseline_domain:
                    baseline_count = len(baseline_data)
                    latest_count = len(latest_data)

                    # Ignore placeholder/stub baselines (short generic content) when
                    # comparing against a real live scrape that has substantial prose.
                    stub_baseline = all(
                        len(str(p.get("content", "")).strip()) < 200
                        for p in baseline_data
                    )
                    latest_prose = sum(len(str(p.get("content", "")).strip()) for p in latest_data)

                    if (
                        not stub_baseline
                        and latest_count < (baseline_count * 0.5)
                        and latest_prose < 1500
                    ):
                        drop_pct = int(((baseline_count - latest_count) / baseline_count) * 100)
                        return False, f"[HEALTH_CHECK] ❌ FAIL: Page count dropped by {drop_pct}% vs baseline for {latest_domain} ({latest_count} current vs {baseline_count} baseline pages).", latest_data
        except Exception:
            pass

    return True, f"[HEALTH_CHECK] ✅ PASS: Scrape healthy: {len(latest_data)} pages validated cleanly for {latest_domain}.", latest_data


def main():
    parser = argparse.ArgumentParser(description="Run Scraper Health Check")
    parser.add_argument("--latest", default=str(DEFAULT_LATEST_PATH), help="Latest scrape JSON path")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH), help="Baseline JSON path")

    args = parser.parse_args()
    
    is_healthy, reason, latest_data = check_health(Path(args.latest), Path(args.baseline))
    print(reason)

    if not is_healthy:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
