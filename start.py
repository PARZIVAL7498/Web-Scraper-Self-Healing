#!/usr/bin/env python3
"""
start.py - Master Orchestrator Script for Self-Healing Docs-to-RAG Chatbot

Automates all initiation tasks:
1. Environment Setup (copies .env.example -> .env if needed)
2. Runs the Self-Healing Scraper & Vector Indexing Pipeline (`scripts/heal_loop.py`)
3. Launches the FastAPI Chatbot App via Uvicorn (`python -m uvicorn chatbot.app:app`)
4. Auto-opens the web browser to http://localhost:8000
"""

import os
import sys
import time
import shutil
import subprocess
import webbrowser
import threading
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
ENV_FILE = ROOT_DIR / ".env"
ENV_EXAMPLE_FILE = ROOT_DIR / ".env.example"


def setup_environment():
    """Ensure .env exists before running applications."""
    if not ENV_FILE.exists():
        if ENV_EXAMPLE_FILE.exists():
            shutil.copyfile(ENV_EXAMPLE_FILE, ENV_FILE)
            print("[START] 📄 Created '.env' file from '.env.example'")
        else:
            print("[START] ⚠️ '.env.example' not found; proceeding without default environment file.")


def run_pipeline(mock_unhealthy: bool = False, mock: bool = False):
    """Run self-healing scraper and vector store indexing pipeline."""
    print("\n" + "=" * 70)
    print("STEP 1: RUNNING SELF-HEALING SCRAPER & VECTOR INDEXING PIPELINE")
    print("=" * 70)

    cmd = [sys.executable, str(SCRIPTS_DIR / "heal_loop.py")]
    if mock_unhealthy:
        cmd.append("--mock-unhealthy")
    elif mock:
        cmd.append("--mock")

    try:
        res = subprocess.run(cmd, check=False)
        if res.returncode != 0:
            print(f"[START] ⚠️ Pipeline returned exit code {res.returncode}. Proceeding to launch web server...")
        else:
            print("[START] ✅ Self-healing scraper & ChromaDB indexing completed successfully.")
    except Exception as e:
        print(f"[START] ❌ Failed to execute pipeline script: {e}")


def open_browser(url: str, delay: float = 2.0):
    """Open browser after server starts."""
    def _open():
        time.sleep(delay)
        print(f"\n[START] 🌐 Launching browser: {url}")
        webbrowser.open(url)

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def start_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = True, auto_browser: bool = True):
    """Start Uvicorn FastAPI web server."""
    url = f"http://{host}:{port}"
    print("\n" + "=" * 70)
    print(f"STEP 2: STARTING FASTAPI CHATBOT WEB SERVER AT {url}")
    print("=" * 70)

    if auto_browser:
        open_browser(url, delay=2.0)

    cmd = [
        sys.executable, "-m", "uvicorn", "chatbot.app:app",
        "--host", host,
        "--port", str(port)
    ]
    if reload:
        cmd.append("--reload")

    print(f"[START] 🚀 Executing: {' '.join(cmd)}\n")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n[START] 🛑 Server stopped by user.")


def main():
    parser = argparse.ArgumentParser(description="Master Launcher for Self-Healing Docs-to-RAG Chatbot")
    parser.add_argument("--skip-heal", action="store_true", help="Skip running the scraper/heal loop and start server immediately")
    parser.add_argument("--mock-unhealthy", action="store_true", help="Run heal loop in mock-unhealthy demo mode")
    parser.add_argument("--mock", action="store_true", help="Run heal loop in mock mode")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP to bind web server (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind web server (default: 8000)")
    parser.add_argument("--no-reload", action="store_true", help="Disable Uvicorn auto-reload")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open default web browser")

    args = parser.parse_args()

    print("\n✨ SELF-HEALING DOCS-TO-RAG CHATBOT LAUNCHER ✨\n")

    # Step 1: Environment Setup
    setup_environment()

    # Step 2: Scraper Pipeline Execution (unless skipped)
    if not args.skip_heal:
        run_pipeline(mock_unhealthy=args.mock_unhealthy, mock=args.mock)
    else:
        print("[START] ⏭️ Skipping self-healing scraper pipeline (--skip-heal specified).")

    # Step 3: Web Server Launch
    start_server(
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        auto_browser=not args.no_browser
    )


if __name__ == "__main__":
    main()
