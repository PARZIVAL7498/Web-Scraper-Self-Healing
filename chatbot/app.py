#!/usr/bin/env python3
"""
FastAPI surface for the self-healing docs RAG product.

Pipeline: scrape (scripts/run_scraper.py) → health (heal_loop) → embed → chat/compare.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CHROMA_DB_DIR = DATA_DIR / "chroma_db"
STATIC_DIR = Path(__file__).resolve().parent / "static"
LAST_HEAL_AT_PATH = DATA_DIR / "last_heal_at.txt"

sys.path.insert(0, str(BASE_DIR / "scripts"))
sys.path.insert(0, str(BASE_DIR / "chatbot"))

from chunk_and_embed import chunk_and_embed, open_docs_collection, query_collection
from docs_urls import (
    collector_id,
    extract_competitor_tag,
    is_specific_docs_page,
    normalize_page_url,
    normalize_url,
    url_path_query_terms,
)
from rag import (
    OPENROUTER_MODEL,
    compute_comparative_scores,
    generate_comparative_answer,
    generate_llm_answer,
    llm_provider_name,
    unique_citations,
)
from run_scraper import run_bdata_scraper

app = FastAPI(title="Docs-to-RAG Self-Healing Chatbot", version="2.5.0")


class ChatRequest(BaseModel):
    query: str
    url: Optional[str] = "https://duckdb.org/docs/"
    top_k: Optional[int] = 4


class CompareRequest(BaseModel):
    url_a: str
    url_b: str
    topic: Optional[str] = "Architecture, features, and query performance"


class TriggerScrapeRequest(BaseModel):
    mock: Optional[bool] = False
    mock_unhealthy: Optional[bool] = False


def get_chroma_collection():
    if not CHROMA_DB_DIR.exists():
        return None
    try:
        return open_docs_collection(CHROMA_DB_DIR)
    except Exception as exc:
        print(f"[CHATBOT] ChromaDB connection error: {exc}")
        return None


def _has_filter_chunks(collection, where: dict) -> bool:
    if not collection or collection.count() == 0:
        return False
    try:
        sample = collection.get(where=where, limit=1)
        return bool(sample and sample.get("ids"))
    except Exception:
        return False


def _has_page_chunks(collection, competitor: str, page_url: str) -> bool:
    if not collection or collection.count() == 0:
        return False
    try:
        sample = collection.get(where={"competitor": competitor}, include=["metadatas"])
        want = normalize_page_url(page_url)
        return any(normalize_page_url((meta or {}).get("url", "")) == want for meta in (sample.get("metadatas") or []))
    except Exception:
        return False


def _chunks_from_query(results: dict, fallback_url: str, brand: str) -> list[dict]:
    chunks: list[dict] = []
    if not results or not results.get("documents") or not results["documents"][0]:
        return chunks
    docs = results["documents"][0]
    metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        chunks.append({
            "text": doc,
            "url": (meta or {}).get("url", fallback_url),
            "title": (meta or {}).get("title", f"{brand} Page {i + 1}"),
            "chunk_index": (meta or {}).get("chunk_index", 0),
        })
    return chunks


def _pin_chunks_to_page(collection, chunks: list[dict], competitor: str, target_url: str) -> list[dict]:
    want = normalize_page_url(target_url)
    page_chunks = [c for c in chunks if normalize_page_url(c["url"]) == want]
    if page_chunks:
        return page_chunks
    if not collection:
        return chunks
    try:
        dumped = collection.get(where={"competitor": competitor}, include=["documents", "metadatas"])
        pinned = []
        for doc, meta in zip(dumped.get("documents") or [], dumped.get("metadatas") or []):
            if normalize_page_url((meta or {}).get("url", "")) == want:
                pinned.append({
                    "text": doc,
                    "url": (meta or {}).get("url", target_url),
                    "title": (meta or {}).get("title", f"{competitor} Page"),
                    "chunk_index": (meta or {}).get("chunk_index", 0),
                })
        return pinned or chunks
    except Exception:
        return chunks


@app.get("/api/status")
def get_status():
    import run_scraper as run_scraper_mod

    collection = get_chroma_collection()
    count = collection.count() if collection else 0

    baseline_count = 0
    baseline_path = DATA_DIR / "last_known_good.json"
    if baseline_path.exists():
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline_count = len(data) if isinstance(data, list) else 0
        except Exception:
            pass

    last_heal_at = None
    if LAST_HEAL_AT_PATH.exists():
        try:
            last_heal_at = LAST_HEAL_AT_PATH.read_text(encoding="utf-8").strip() or None
        except Exception:
            last_heal_at = None

    engine = getattr(run_scraper_mod, "LAST_SCRAPE_ENGINE", "none")
    proof_path = DATA_DIR / "proof_bdata_run.json"
    if engine in (None, "none") and proof_path.exists():
        try:
            engine = json.loads(proof_path.read_text(encoding="utf-8")).get("engine", engine)
        except Exception:
            pass

    provider = llm_provider_name()
    return {
        "status": "online",
        "indexed_chunks": count,
        "baseline_pages": baseline_count,
        "llm_provider": provider,
        "collector_id": collector_id(),
        "scrape_engine": engine,
        "last_heal_at": last_heal_at,
        "openrouter_model": OPENROUTER_MODEL if provider == "OpenRouter" else None,
    }


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Index-first Q&A. Scrape only when this site/page is missing from Chroma."""
    target_url = normalize_url(request.url or "https://duckdb.org/docs/")
    comp_tag = extract_competitor_tag(target_url)
    collector = collector_id()
    file_path = DATA_DIR / f"scrape_{comp_tag.lower()}.json"
    collection = get_chroma_collection()

    specific_page = is_specific_docs_page(target_url)
    need_scrape = (not _has_filter_chunks(collection, {"competitor": comp_tag})) or (
        specific_page and not _has_page_chunks(collection, comp_tag, target_url)
    )

    if need_scrape:
        try:
            run_bdata_scraper(
                collector_id=collector,
                target_url=target_url,
                output_path=file_path,
                mock=False,
                max_pages=1 if specific_page else 4,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Scrape failed (Studio-first): {exc}") from exc
        chunk_and_embed(input_path=file_path, competitor_tag=comp_tag, page_scoped=specific_page)
        collection = get_chroma_collection()

    retrieval_query = request.query
    path_terms = url_path_query_terms(target_url)
    if path_terms:
        retrieval_query = f"{request.query} {path_terms}"

    try:
        pool = min(12, max(collection.count(), 1)) if collection else 4
        n = pool if specific_page else min(request.top_k or 4, pool)
        results = query_collection(
            collection,
            retrieval_query,
            where={"competitor": comp_tag},
            n_results=n,
        ) if collection else {}
        if not results or not results.get("documents") or not results["documents"][0]:
            results = query_collection(collection, retrieval_query, n_results=n) if collection else {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ChromaDB query failed: {exc}") from exc

    retrieved = _chunks_from_query(results, target_url, comp_tag)
    if specific_page:
        retrieved = _pin_chunks_to_page(collection, retrieved, comp_tag, target_url)

    return {
        "query": request.query,
        "target_url": target_url,
        "brand": comp_tag,
        "answer": generate_llm_answer(request.query, retrieved, target_url=target_url),
        "citations": unique_citations(retrieved),
        "retrieved_chunks_count": len(retrieved),
    }


@app.post("/api/scrape-and-compare")
def scrape_and_compare(req: CompareRequest):
    url_a = normalize_url(req.url_a)
    url_b = normalize_url(req.url_b)
    comp_a = extract_competitor_tag(url_a)
    comp_b = extract_competitor_tag(url_b)
    collector = collector_id()

    try:
        run_bdata_scraper(collector_id=collector, target_url=url_a, output_path=DATA_DIR / f"scrape_{comp_a.lower()}.json", mock=False)
        chunk_and_embed(input_path=DATA_DIR / f"scrape_{comp_a.lower()}.json", competitor_tag=comp_a)
        run_bdata_scraper(collector_id=collector, target_url=url_b, output_path=DATA_DIR / f"scrape_{comp_b.lower()}.json", mock=False)
        chunk_and_embed(input_path=DATA_DIR / f"scrape_{comp_b.lower()}.json", competitor_tag=comp_b)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Compare scrape failed (Studio-first): {exc}") from exc

    collection = get_chroma_collection()
    res_a = query_collection(collection, req.topic, where={"competitor": comp_a}, n_results=3) if collection else {}
    res_b = query_collection(collection, req.topic, where={"competitor": comp_b}, n_results=3) if collection else {}
    chunks_a = _chunks_from_query(res_a, url_a, comp_a)
    chunks_b = _chunks_from_query(res_b, url_b, comp_b)
    scores_a, scores_b = compute_comparative_scores(chunks_a, chunks_b)

    return {
        "topic": req.topic,
        "competitor_a": comp_a,
        "competitor_b": comp_b,
        "scores_a": scores_a,
        "scores_b": scores_b,
        "comparison_markdown": generate_comparative_answer(req.topic, comp_a, chunks_a, comp_b, chunks_b),
        "citations": unique_citations(chunks_a + chunks_b),
    }


@app.get("/api/heal-status")
def heal_status():
    payload = {
        "phase": "idle",
        "collector_id": collector_id(),
        "attempt": None,
        "health_reason": "",
        "engine": "",
        "message": "No heal job has run yet",
        "updated_at": None,
        "last_heal_at": None,
    }
    status_path = DATA_DIR / "heal_job_status.json"
    if status_path.exists():
        try:
            payload.update(json.loads(status_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    if LAST_HEAL_AT_PATH.exists():
        try:
            payload["last_heal_at"] = LAST_HEAL_AT_PATH.read_text(encoding="utf-8").strip() or None
        except Exception:
            pass
    return payload


@app.post("/api/trigger-scrape")
def trigger_scrape(req: TriggerScrapeRequest, background_tasks: BackgroundTasks):
    cmd = [sys.executable, "-u", str(BASE_DIR / "scripts" / "heal_loop.py")]
    if req.mock_unhealthy:
        cmd.append("--mock-unhealthy")

    try:
        seed = {
            "phase": "scrape",
            "collector_id": collector_id(),
            "attempt": 1,
            "health_reason": "",
            "engine": "",
            "message": "Pipeline triggered from UI",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (DATA_DIR / "heal_job_status.json").write_text(json.dumps(seed, indent=2), encoding="utf-8")
    except Exception:
        pass

    background_tasks.add_task(subprocess.run, cmd)
    return {
        "message": "Self-healing pipeline trigger initiated!",
        "mock_unhealthy": req.mock_unhealthy,
        "collector_id": collector_id(),
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
