#!/usr/bin/env python3
"""
chatbot/app.py
FastAPI backend for RAG Chatbot with Citation Support, ChromaDB retrieval,
Dual-URL Live Scrape & Compare engine, True Live HTML Web Scraper with Word Boundary Truncation,
and Chart.js metrics evaluation.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CHROMA_DB_DIR = DATA_DIR / "chroma_db"
STATIC_DIR = Path(__file__).resolve().parent / "static"
COLLECTION_NAME = "docs_rag"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"


def _collector_id() -> str:
    return os.getenv("BRIGHTDATA_COLLECTOR_ID", "c_sample_collector_12345")


LAST_HEAL_AT_PATH = DATA_DIR / "last_heal_at.txt"

sys.path.append(str(BASE_DIR / "scripts"))
from run_scraper import run_bdata_scraper, normalize_url, LAST_SCRAPE_ENGINE
from chunk_and_embed import chunk_and_embed, extract_competitor_tag
from health_check import check_health


def _llm_provider_name() -> str:
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "your_openrouter_api_key_here":
        return "OpenRouter"
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        return "Gemini API"
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        return "OpenAI API"
    return "Local RAG Engine"


def _call_openrouter(prompt: str) -> Optional[str]:
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        return None
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Self-Healing Docs RAG",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=45,
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"].strip()
        print(f"[CHATBOT] OpenRouter HTTP {res.status_code}: {res.text[:300]}")
    except Exception as e:
        print(f"[CHATBOT] OpenRouter API call error: {e}")
    return None


app = FastAPI(title="Docs-to-RAG Self-Healing Chatbot & Competitor Engine", version="2.4.0")


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
    """Returns local ChromaDB collection."""
    if not CHROMA_DB_DIR.exists():
        return None
    try:
        chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        try:
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        except Exception:
            ef = embedding_functions.DefaultEmbeddingFunction()
        return chroma_client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)
    except Exception as e:
        print(f"[CHATBOT] ChromaDB connection error: {e}")
        return None


def truncate_word_boundary(text: str, max_chars: int = 550) -> str:
    """Truncates text at word boundaries so words are never cut in half."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rsplit(' ', 1)[0]
    return trimmed + "..."


def _norm_page_url(url: str) -> str:
    return (url or "").strip().lower().split("#")[0].rstrip("/")


def _is_specific_docs_page(url: str) -> bool:
    """True when the user pointed at a concrete docs page, not a site/docs root."""
    parts = [p for p in urlparse(_norm_page_url(url)).path.split("/") if p]
    generic = {"docs", "doc", "documentation", "en", "current", "latest", "api", "guide", "reference", "www"}
    return any(p.lower() not in generic for p in parts)


def _url_path_query_terms(url: str) -> str:
    raw = urlparse(_norm_page_url(url)).path.replace("-", " ").replace("_", " ").replace("/", " ")
    stop = {"docs", "doc", "html", "htm", "api", "current", "latest", "www", "guide", "en"}
    return " ".join(t for t in raw.split() if len(t) > 2 and t.lower() not in stop)


def _chunk_relevance_score(query: str, text: str, url: str = "", target_url: str = "") -> float:
    """Prefer chunks that match the query AND contain real explanatory content/code."""
    q_terms = [t for t in query.lower().split() if len(t) > 2]
    lower = text.lower()
    overlap = sum(1 for t in q_terms if t in lower)
    substance = min(len(text), 1200) / 1200.0
    has_code = 1.5 if "```" in text or "require(" in text or "import " in text else 0.0
    heading_penalty = -2.0 if len(text) < 100 else 0.0
    url_boost = 8.0 if target_url and _norm_page_url(url) == _norm_page_url(target_url) else 0.0
    return overlap * 2.0 + substance + has_code + heading_penalty + url_boost


def synthesize_local_answer(query: str, chunks: List[Dict[str, Any]], target_url: str = "") -> str:
    """
    Local (no-LLM) answer builder: ranks retrieved chunks by query relevance + substance,
    then writes a direct answer with the best prose/code — not just titles and links.
    """
    ranked = sorted(
        chunks,
        key=lambda c: _chunk_relevance_score(query, c.get("text", ""), c.get("url", ""), target_url),
        reverse=True,
    )

    # Keep the most useful passages (allow multiple from the same page)
    selected = []
    seen_text = set()
    for c in ranked:
        text = (c.get("text") or "").strip()
        if len(text) < 60:
            continue
        key = text[:120]
        if key in seen_text:
            continue
        seen_text.add(key)
        selected.append(c)
        if len(selected) >= 3:
            break

    if not selected:
        # Fall back to whatever we retrieved, even if short
        selected = chunks[:2]

    best = selected[0]
    answer_parts = [
        f"### Answer (from **{best['title']}**)\n",
        f"Based on the documentation for your question: *{query}*\n",
    ]

    for i, c in enumerate(selected, 1):
        body = truncate_word_boundary(c["text"], max_chars=900)
        answer_parts.append(f"**[{i}] {c['title']}**\n\n{body}\n")

    answer_parts.append(
        f"Source page: [{best['url']}]({best['url']})"
    )
    return "\n".join(answer_parts)


def generate_llm_answer(query: str, chunks: List[Dict[str, Any]], target_url: str = "") -> str:
    """
    Clean RAG Answer Synthesizer with Word Boundary Truncation.
    Generates structured Markdown grounded strictly in retrieved live web text.
    """
    formatted_context = ""
    for idx, chunk in enumerate(chunks, 1):
        formatted_context += f"--- Source [{idx}]: {chunk['title']} ({chunk['url']}) ---\n{chunk['text']}\n\n"

    system_prompt = (
        "You are an expert technical assistant powered by a Self-Healing Documentation RAG pipeline. "
        "Answer the user's question accurately and concisely using ONLY the provided source documentation context below. "
        "Do NOT reply with only a page title or link — always include the concrete explanation and code examples from the docs. "
        "Include reference numbers like [1], [2] in your answer when referencing specific documentation context.\n\n"
        f"Documentation Context:\n{formatted_context}\n\n"
        f"User Question: {query}\n\n"
        "Answer:"
    )

    # Primary: OpenRouter
    openrouter_answer = _call_openrouter(system_prompt)
    if openrouter_answer:
        return openrouter_answer

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=system_prompt,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[CHATBOT] Gemini API call error: {e}")

    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        try:
            import requests
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": system_prompt}], "temperature": 0.2}
            res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[CHATBOT] OpenAI API call error: {e}")

    if not chunks:
        return "I couldn't find any relevant documentation context in the vector database to answer your question."

    return synthesize_local_answer(query, chunks, target_url=target_url)


def compute_doc_coverage_scores(chunks: List[Dict]) -> List[int]:
    """
    Derive 0-100 radar scores from retrieved scrape chunks (not brand names).
    Axes: code examples, structure depth, content volume, API/reference signal, source diversity.
    """
    texts = [str(c.get("text") or "") for c in (chunks or [])]
    urls = [str(c.get("url") or "") for c in (chunks or [])]
    joined = "\n".join(texts)
    total_chars = max(len(joined), 1)

    code_fences = joined.count("```") + joined.count("    ")
    code_score = min(100, int(15 + code_fences * 4 + (joined.count(";") + joined.count("()")) * 0.15))

    heading_hits = sum(
        1
        for line in joined.splitlines()
        if line.strip().startswith("#")
        or line.strip().endswith(":")
        or (len(line) < 80 and line.isupper() and len(line) > 3)
    )
    structure_score = min(100, int(20 + heading_hits * 6 + len(texts) * 4))

    volume_score = min(100, int(10 + (total_chars / 80)))

    api_tokens = (
        "api", "endpoint", "function", "class", "method", "parameter",
        "install", "import", "export", "schema", "query", "request", "response",
    )
    lower = joined.lower()
    api_hits = sum(lower.count(t) for t in api_tokens)
    api_score = min(100, int(18 + api_hits * 1.5))

    unique_urls = len({u for u in urls if u})
    diversity_score = min(100, int(25 + unique_urls * 18 + len(texts) * 3))

    return [
        max(5, min(100, code_score)),
        max(5, min(100, structure_score)),
        max(5, min(100, volume_score)),
        max(5, min(100, api_score)),
        max(5, min(100, diversity_score)),
    ]


def compute_comparative_scores(
    chunks_a: List[Dict],
    chunks_b: List[Dict],
) -> tuple:
    """Compute relative doc-coverage scores from live scrape chunks."""
    return compute_doc_coverage_scores(chunks_a), compute_doc_coverage_scores(chunks_b)


def generate_comparative_answer(topic: str, comp_a: str, chunks_a: List[Dict], comp_b: str, chunks_b: List[Dict]) -> str:
    """Generates structured side-by-side comparative markdown report."""
    ctx_a = "\n".join([f"- [{c['title']}]({c['url']}): {c['text']}" for c in chunks_a])
    ctx_b = "\n".join([f"- [{c['title']}]({c['url']}): {c['text']}" for c in chunks_b])

    prompt = (
        f"Compare {comp_a} and {comp_b} regarding topic: '{topic}' based on their official documentation below.\n\n"
        f"=== {comp_a} Documentation ===\n{ctx_a}\n\n"
        f"=== {comp_b} Documentation ===\n{ctx_b}\n\n"
        "Generate a structured Markdown response with:\n"
        "1. Executive Overview\n"
        "2. Side-by-Side Comparison Matrix Table (| Feature | " + comp_a + " | " + comp_b + " |)\n"
        "3. Key Trade-offs & Recommendations\n"
    )

    openrouter_answer = _call_openrouter(prompt)
    if openrouter_answer:
        return openrouter_answer

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            if res and res.text:
                return res.text.strip()
        except Exception as e:
            print(f"[CHATBOT] Gemini comparison error: {e}")

    text_a = chunks_a[0]['text'] if chunks_a else f"Core documentation for {comp_a}"
    text_b = chunks_b[0]['text'] if chunks_b else f"Core documentation for {comp_b}"

    return (
        f"### 📊 Competitive Documentation Analysis: **{comp_a} vs {comp_b}**\n\n"
        f"**Topic Evaluated**: *{topic}*\n\n"
        f"#### ⚔️ Feature Comparison Matrix\n\n"
        f"| Feature / Metric | **{comp_a}** | **{comp_b}** |\n"
        f"| :--- | :--- | :--- |\n"
        f"| **Primary Architecture** | Specialized engine architecture | Distributed/managed infrastructure |\n"
        f"| **Deployment Model** | Modular / Client-side integration | Scalable cluster / Cloud service |\n"
        f"| **Target Workloads** | High-performance workload processing | Enterprise data and workflow execution |\n\n"
        f"#### 🔍 Documentation Insights\n\n"
        f"##### 🟩 **{comp_a} Overview**\n{text_a}\n\n"
        f"##### 🟦 **{comp_b} Overview**\n{text_b}\n\n"
        f"#### 💡 Key Recommendation\n"
        f"- Choose **{comp_a}** for specialized client performance, local execution, and developer ergonomics.\n"
        f"- Choose **{comp_b}** for cloud scale, distributed fault tolerance, and managed infrastructure."
    )


@app.get("/api/status")
def get_status():
    """Returns database status, scrape engine, collector id, and LLM provider."""
    import run_scraper as run_scraper_mod

    collection = get_chroma_collection()
    count = collection.count() if collection else 0

    baseline_path = DATA_DIR / "last_known_good.json"
    baseline_count = 0
    if baseline_path.exists():
        try:
            with open(baseline_path, "r", encoding="utf-8") as f:
                data = json.load(f)
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

    return {
        "status": "online",
        "indexed_chunks": count,
        "baseline_pages": baseline_count,
        "llm_provider": _llm_provider_name(),
        "collector_id": _collector_id(),
        "scrape_engine": engine,
        "last_heal_at": last_heal_at,
        "openrouter_model": OPENROUTER_MODEL if _llm_provider_name() == "OpenRouter" else None,
    }


@app.post("/api/chat")
def chat(request: ChatRequest):
    """
    RAG Q&A: answer from indexed Chroma first (fast).
    Only scrape+embed when that competitor has no chunks yet.
    """
    target_url = normalize_url(request.url or "https://duckdb.org/docs/")
    comp_tag = extract_competitor_tag(target_url)

    collector_id = _collector_id()
    file_path = DATA_DIR / f"scrape_{comp_tag.lower()}.json"
    collection = get_chroma_collection()

    def _has_competitor_chunks() -> bool:
        if not collection or collection.count() == 0:
            return False
        try:
            sample = collection.get(where={"competitor": comp_tag}, limit=1)
            return bool(sample and sample.get("ids"))
        except Exception:
            return False

    def _has_page_chunks(page_url: str) -> bool:
        if not collection or collection.count() == 0:
            return False
        try:
            sample = collection.get(where={"competitor": comp_tag}, include=["metadatas"])
            want = _norm_page_url(page_url)
            return any(_norm_page_url((m or {}).get("url", "")) == want for m in (sample.get("metadatas") or []))
        except Exception:
            return False

    specific_page = _is_specific_docs_page(target_url)
    need_scrape = (not _has_competitor_chunks()) or (specific_page and not _has_page_chunks(target_url))

    # Avoid multi-minute Studio scrape on every chat turn (causes browser "Failed to fetch")
    if need_scrape:
        try:
            run_bdata_scraper(
                collector_id=collector_id,
                target_url=target_url,
                output_path=file_path,
                mock=False,
                max_pages=1 if specific_page else 4,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Scrape failed (Studio-first): {e}")
        chunk_and_embed(input_path=file_path, competitor_tag=comp_tag, page_scoped=specific_page)
        collection = get_chroma_collection()

    retrieval_query = request.query
    path_terms = _url_path_query_terms(target_url)
    if path_terms:
        retrieval_query = f"{request.query} {path_terms}"

    try:
        pool = min(12, max(collection.count(), 1)) if collection else 4
        n = pool if specific_page else min(request.top_k or 4, pool)
        results = collection.query(
            query_texts=[retrieval_query],
            where={"competitor": comp_tag},
            n_results=n,
        ) if collection else {}

        if not results or not results.get("documents") or not results["documents"][0]:
            results = collection.query(
                query_texts=[retrieval_query],
                n_results=n,
            ) if collection else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ChromaDB query failed: {str(e)}")

    retrieved_chunks = []
    citations = []

    if results and results.get("documents") and results["documents"][0]:
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)

        for i, (doc, meta) in enumerate(zip(docs, metas)):
            url = meta.get("url", target_url)
            title = meta.get("title", f"{comp_tag} Page {i+1}")
            
            retrieved_chunks.append({
                "text": doc,
                "url": url,
                "title": title,
                "chunk_index": meta.get("chunk_index", 0)
            })

    if specific_page:
        page_chunks = [c for c in retrieved_chunks if _norm_page_url(c["url"]) == _norm_page_url(target_url)]
        if page_chunks:
            retrieved_chunks = page_chunks
        elif collection:
            # Semantic search drifted; pull the indexed target page directly.
            try:
                dumped = collection.get(where={"competitor": comp_tag}, include=["documents", "metadatas"])
                want = _norm_page_url(target_url)
                retrieved_chunks = []
                for doc, meta in zip(dumped.get("documents") or [], dumped.get("metadatas") or []):
                    if _norm_page_url((meta or {}).get("url", "")) == want:
                        retrieved_chunks.append({
                            "text": doc,
                            "url": (meta or {}).get("url", target_url),
                            "title": (meta or {}).get("title", f"{comp_tag} Page"),
                            "chunk_index": (meta or {}).get("chunk_index", 0),
                        })
            except Exception:
                pass

    for c in retrieved_chunks:
        if not any(x["url"] == c["url"] for x in citations):
            citations.append({
                "id": len(citations) + 1,
                "title": c["title"],
                "url": c["url"],
            })

    answer = generate_llm_answer(request.query, retrieved_chunks, target_url=target_url)

    return {
        "query": request.query,
        "target_url": target_url,
        "brand": comp_tag,
        "answer": answer,
        "citations": citations,
        "retrieved_chunks_count": len(retrieved_chunks)
    }


@app.post("/api/scrape-and-compare")
def scrape_and_compare(req: CompareRequest):
    """Live Dual-URL Scrape & Compare Endpoint."""
    url_a = normalize_url(req.url_a)
    url_b = normalize_url(req.url_b)

    comp_a = extract_competitor_tag(url_a)
    comp_b = extract_competitor_tag(url_b)

    collector_id = _collector_id()

    file_a = DATA_DIR / f"scrape_{comp_a.lower()}.json"
    file_b = DATA_DIR / f"scrape_{comp_b.lower()}.json"

    try:
        run_bdata_scraper(collector_id=collector_id, target_url=url_a, output_path=file_a, mock=False)
        chunk_and_embed(input_path=file_a, competitor_tag=comp_a)
        run_bdata_scraper(collector_id=collector_id, target_url=url_b, output_path=file_b, mock=False)
        chunk_and_embed(input_path=file_b, competitor_tag=comp_b)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Compare scrape failed (Studio-first): {e}")

    # Step 3: Perform Dual Filtered Chroma Queries
    collection = get_chroma_collection()
    
    res_a = collection.query(query_texts=[req.topic], where={"competitor": comp_a}, n_results=3) if collection else {}
    res_b = collection.query(query_texts=[req.topic], where={"competitor": comp_b}, n_results=3) if collection else {}

    chunks_a = []
    if res_a.get("documents") and res_a["documents"][0]:
        for doc, meta in zip(res_a["documents"][0], res_a["metadatas"][0]):
            chunks_a.append({"text": doc, "title": meta.get("title", comp_a), "url": meta.get("url", url_a)})

    chunks_b = []
    if res_b.get("documents") and res_b["documents"][0]:
        for doc, meta in zip(res_b["documents"][0], res_b["metadatas"][0]):
            chunks_b.append({"text": doc, "title": meta.get("title", comp_b), "url": meta.get("url", url_b)})

    comparison_md = generate_comparative_answer(req.topic, comp_a, chunks_a, comp_b, chunks_b)

    scores_a, scores_b = compute_comparative_scores(chunks_a, chunks_b)

    citations = []
    for c in chunks_a + chunks_b:
        if not any(cit["url"] == c["url"] for cit in citations):
            citations.append({"id": len(citations) + 1, "title": c["title"], "url": c["url"]})

    return {
        "topic": req.topic,
        "competitor_a": comp_a,
        "competitor_b": comp_b,
        "scores_a": scores_a,
        "scores_b": scores_b,
        "comparison_markdown": comparison_md,
        "citations": citations
    }


@app.get("/api/heal-status")
def heal_status():
    """Return live heal pipeline phase written by heal_loop.py."""
    status_path = DATA_DIR / "heal_job_status.json"
    payload = {
        "phase": "idle",
        "collector_id": _collector_id(),
        "attempt": None,
        "health_reason": "",
        "engine": "",
        "message": "No heal job has run yet",
        "updated_at": None,
        "last_heal_at": None,
    }
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
    """Triggers self-healing scraper pipeline background worker."""
    script_path = BASE_DIR / "scripts" / "heal_loop.py"
    cmd = [sys.executable, "-u", str(script_path)]
    if req.mock_unhealthy:
        cmd.append("--mock-unhealthy")

    # Seed status so UI polling starts immediately
    try:
        from datetime import datetime, timezone
        seed = {
            "phase": "scrape",
            "collector_id": _collector_id(),
            "attempt": 1,
            "health_reason": "",
            "engine": "",
            "message": "Pipeline triggered from UI",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (DATA_DIR / "heal_job_status.json").write_text(json.dumps(seed, indent=2), encoding="utf-8")
    except Exception:
        pass

    def run_pipeline():
        subprocess.run(cmd)

    background_tasks.add_task(run_pipeline)

    return {
        "message": "Self-healing pipeline trigger initiated!",
        "mock_unhealthy": req.mock_unhealthy,
        "collector_id": _collector_id(),
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
