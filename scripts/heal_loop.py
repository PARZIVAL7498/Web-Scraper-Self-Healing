#!/usr/bin/env python3
"""
scripts/heal_loop.py
Self-healing orchestrator loop:
1. Runs scraper (`scripts/run_scraper.py`)
2. Performs health check (`scripts/health_check.py`)
3. If unhealthy:
   - Invokes `bdata scraper heal <COLLECTOR_ID> "<reason>"`
   - Invokes `bdata scraper approve <COLLECTOR_ID>`
   - Re-runs & re-checks (up to 2 retries)
4. If still unhealthy -> log failure & exit non-zero (CI failure trigger)
5. If healthy -> update `data/last_known_good.json` & execute `scripts/chunk_and_embed.py`
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LATEST_SCRAPE_PATH = DATA_DIR / "latest_scrape.json"
BASELINE_PATH = DATA_DIR / "last_known_good.json"
HEAL_STATUS_PATH = DATA_DIR / "heal_job_status.json"
SCRIPTS_DIR = Path(__file__).resolve().parent

DEFAULT_COLLECTOR_ID = os.getenv("BRIGHTDATA_COLLECTOR_ID", "c_sample_collector_12345")
DEFAULT_TARGET_URL = os.getenv("TARGET_URL", "https://duckdb.org/docs/")


def write_heal_status(
    phase: str,
    collector_id: str,
    *,
    attempt: int | None = None,
    health_reason: str = "",
    engine: str = "",
    message: str = "",
):
    """Persist heal pipeline phase for UI polling via /api/heal-status."""
    from datetime import datetime, timezone

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": phase,
        "collector_id": collector_id,
        "attempt": attempt,
        "health_reason": (health_reason or "")[:500],
        "engine": engine,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        HEAL_STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[HEAL_LOOP] ⚠️ Failed to write heal status: {e}")


def run_command(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """Helper to run shell command and log execution safely."""
    cmd_str = " ".join(cmd)
    print(f"[HEAL_LOOP] 🔧 Executing: {cmd_str}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if check and result.returncode != 0:
            print(f"[HEAL_LOOP] ❌ Command failed with code {result.returncode}:\n{result.stderr}")
        return result
    except FileNotFoundError:
        print(f"[HEAL_LOOP] ⚠️ CLI executable '{cmd[0]}' not found on system PATH.")
        return subprocess.CompletedProcess(args=cmd, returncode=127, stdout="", stderr=f"Executable '{cmd[0]}' not found.")


def _bdata_bin() -> str | None:
    return shutil.which("bdata") or shutil.which("brightdata")


def heal_loop(collector_id: str, target_url: str, max_retries: int = 2, mock: bool = False, mock_unhealthy: bool = False):
    """
    Main self-healing pipeline iteration loop.
    """
    from run_scraper import is_placeholder_api_key, is_placeholder_collector, is_studio_ready

    bdata = _bdata_bin()
    sample_collector = is_placeholder_collector(collector_id)
    studio_ready = is_studio_ready(collector_id, os.getenv("BRIGHTDATA_API_KEY"))
    # Use real bdata heal/approve only when CLI, collector, and API key are real.
    # --mock-unhealthy only fakes the first broken scrape payload.
    use_mock_heal_cli = mock or (bdata is None) or not studio_ready

    if bdata is None:
        print("[HEAL_LOOP] ℹ️ 'bdata' CLI not found on PATH. Using Web Unlocker/HTTP; mocking heal/approve CLI only.")
    elif sample_collector or is_placeholder_api_key(os.getenv("BRIGHTDATA_API_KEY")):
        print("[HEAL_LOOP] ℹ️ Bright Data not configured (placeholder key/collector). Using HTTP scrape + mock heal CLI.")
    else:
        print(f"[HEAL_LOOP] ✅ Using Bright Data CLI at: {bdata}")

    print("=" * 70)
    print("🤖 STARTING SCRAPER SELF-HEALING PIPELINE")
    print(f"• Collector ID: {collector_id}")
    print(f"• Target URL:    {target_url}")
    print(f"• Max Retries:   {max_retries}")
    print(f"• Mock Heal CLI: {use_mock_heal_cli}")
    print("=" * 70)

    write_heal_status(
        "scrape",
        collector_id,
        attempt=1,
        message="Pipeline started",
    )

    attempt = 0
    is_healthy = False
    health_reason = ""
    current_mock_unhealthy = mock_unhealthy

    while attempt <= max_retries:
        attempt_num = attempt + 1
        print(f"\n--- 🔄 ATTEMPT {attempt_num} / {max_retries + 1} ---")

        write_heal_status(
            "retry" if attempt > 0 else "scrape",
            collector_id,
            attempt=attempt_num,
            message=f"Running scraper (attempt {attempt_num})",
        )

        # Step 1: Run scraper wrapper (live HTTP unless --mock-unhealthy)
        run_scraper_cmd = [
            sys.executable, "-u", str(SCRIPTS_DIR / "run_scraper.py"),
            "--collector-id", collector_id,
            "--url", target_url,
            "--output", str(LATEST_SCRAPE_PATH)
        ]
        if current_mock_unhealthy:
            run_scraper_cmd.append("--mock-unhealthy")

        run_res = run_command(run_scraper_cmd, check=False)
        if run_res.returncode != 0:
            print("[HEAL_LOOP] ⚠️ Scraper script reported execution failure.")

        engine = ""
        try:
            import run_scraper as rs
            engine = getattr(rs, "LAST_SCRAPE_ENGINE", "") or ""
        except Exception:
            proof = DATA_DIR / "proof_bdata_run.json"
            if proof.exists():
                try:
                    engine = json.loads(proof.read_text(encoding="utf-8")).get("engine", "")
                except Exception:
                    pass

        # Step 2: Perform health check
        health_cmd = [
            sys.executable, "-u", str(SCRIPTS_DIR / "health_check.py"),
            "--latest", str(LATEST_SCRAPE_PATH),
            "--baseline", str(BASELINE_PATH)
        ]
        health_res = run_command(health_cmd, check=False)

        if health_res.returncode == 0:
            is_healthy = True
            health_reason = health_res.stdout.strip()
            print(f"\n✨ HEALTH CHECK PASSED: {health_reason}")
            write_heal_status(
                "healthy",
                collector_id,
                attempt=attempt_num,
                health_reason=health_reason,
                engine=engine,
                message="Health check PASSED",
            )
            break
        else:
            is_healthy = False
            health_reason = health_res.stdout.strip() or health_res.stderr.strip() or "Unknown health check failure"
            print(f"\n🚨 HEALTH CHECK FAILED: {health_reason}")
            write_heal_status(
                "health_fail",
                collector_id,
                attempt=attempt_num,
                health_reason=health_reason,
                engine=engine,
                message="Health check FAILED",
            )

        # If unhealthy and retries remain -> trigger Bright Data Scraper Studio healing
        if attempt < max_retries:
            print(f"\n🩹 TRIGGERING SELF-HEALING (Attempt {attempt_num})...")
            write_heal_status(
                "healing",
                collector_id,
                attempt=attempt_num,
                health_reason=health_reason,
                engine=engine,
                message="Invoking bdata scraper heal" if not use_mock_heal_cli else "Mock heal CLI (no real bdata)",
            )

            if use_mock_heal_cli:
                print(f"[HEAL_LOOP] 🎭 Mocking Bright Data heal CLI calls:")
                print(f"  -> bdata scraper heal {collector_id} \"{health_reason}\"")
                print(f"  -> bdata scraper approve {collector_id}")
                print("[HEAL_LOOP] 💡 Bright Data AI is re-learning DOM selectors & updating extraction schema...")
                current_mock_unhealthy = False
                try:
                    from datetime import datetime, timezone
                    (DATA_DIR / "last_heal_at.txt").write_text(
                        datetime.now(timezone.utc).isoformat(), encoding="utf-8"
                    )
                except Exception:
                    pass
            else:
                # Real Bright Data Scraper Studio self-heal
                env = os.environ.copy()
                api_key = os.getenv("BRIGHTDATA_API_KEY")
                if api_key:
                    env["BRIGHTDATA_API_KEY"] = api_key

                heal_reason = health_reason[:480]
                heal_cmd = [bdata, "scraper", "heal", collector_id, heal_reason, "--url", target_url, "--auto-approve"]
                print(f"[HEAL_LOOP] 🔧 Executing: {' '.join(heal_cmd)}")
                heal_res = subprocess.run(heal_cmd, capture_output=True, text=True, env=env)
                if heal_res.returncode != 0:
                    print(f"[HEAL_LOOP] ⚠️ heal failed ({heal_res.returncode}): {heal_res.stderr or heal_res.stdout}")
                    # Fallback explicit approve if heal stopped at approval gate without --auto-approve support
                    approve_cmd = [bdata, "scraper", "approve", collector_id, "--url", target_url]
                    print(f"[HEAL_LOOP] 🔧 Executing: {' '.join(approve_cmd)}")
                    subprocess.run(approve_cmd, capture_output=True, text=True, env=env)
                else:
                    print((heal_res.stdout or "").strip()[:1000] or "[HEAL_LOOP] heal completed.")

                # Record heal timestamp for status/UI
                try:
                    from datetime import datetime, timezone
                    (DATA_DIR / "last_heal_at.txt").write_text(
                        datetime.now(timezone.utc).isoformat(), encoding="utf-8"
                    )
                except Exception:
                    pass

                current_mock_unhealthy = False

            print("[HEAL_LOOP] ⏳ Healing applied. Retrying scraper execution...")

        attempt += 1

    # Final Pipeline Verdict
    if not is_healthy:
        print("\n" + "!" * 70)
        print("❌ CRITICAL: Scraper pipeline failed health check after max retries!")
        print(f"Reason: {health_reason}")
        print("!" * 70)
        write_heal_status(
            "error",
            collector_id,
            attempt=attempt,
            health_reason=health_reason,
            message="Pipeline failed after max retries",
        )
        sys.exit(1)

    print("\n" + "=" * 70)
    print("✅ PIPELINE HEALTHY: Updating baseline dataset & triggering vector store indexing...")
    print("=" * 70)

    write_heal_status(
        "indexing",
        collector_id,
        health_reason=health_reason,
        message="Updating baseline and indexing Chroma",
    )

    # Step 5: Update baseline last_known_good.json
    try:
        shutil.copyfile(LATEST_SCRAPE_PATH, BASELINE_PATH)
        print(f"[HEAL_LOOP] 📄 Updated baseline dataset at '{BASELINE_PATH}'")
    except Exception as e:
        print(f"[HEAL_LOOP] ⚠️ Failed to update baseline file: {e}")

    # Step 6: Invoke vector store indexing (chunk_and_embed.py)
    chunk_embed_cmd = [
        sys.executable, "-u", str(SCRIPTS_DIR / "chunk_and_embed.py"),
        "--input", str(LATEST_SCRAPE_PATH)
    ]
    chunk_res = run_command(chunk_embed_cmd, check=False)
    
    if chunk_res.returncode == 0:
        print("\n🎉 SELF-HEALING PIPELINE COMPLETED SUCCESSFULLY!")
        write_heal_status(
            "done",
            collector_id,
            health_reason=health_reason,
            message="Pipeline completed successfully",
        )
    else:
        print("\n⚠️ Scraper healed & verified, but chunking/embedding reported warnings.")
        write_heal_status(
            "error",
            collector_id,
            health_reason=health_reason,
            message="Indexing failed after healthy scrape",
        )
        sys.exit(chunk_res.returncode)


def main():
    parser = argparse.ArgumentParser(description="Self-Healing Scraper Pipeline Orchestrator")
    parser.add_argument("--collector-id", default=DEFAULT_COLLECTOR_ID, help="Bright Data Collector ID")
    parser.add_argument("--url", default=DEFAULT_TARGET_URL, help="Target doc URL")
    parser.add_argument("--retries", type=int, default=2, help="Max healing retries")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode without invoking real bdata CLI")
    parser.add_argument("--mock-unhealthy", action="store_true", help="Start with an unhealthy scrape to demo self-healing loop")

    args = parser.parse_args()

    heal_loop(
        collector_id=args.collector_id,
        target_url=args.url,
        max_retries=args.retries,
        mock=args.mock,
        mock_unhealthy=args.mock_unhealthy
    )


if __name__ == "__main__":
    main()
