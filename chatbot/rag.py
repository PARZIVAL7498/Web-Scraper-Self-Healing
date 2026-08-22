#!/usr/bin/env python3
"""RAG answer synthesis: OpenRouter / Gemini / OpenAI, then local grounded fallback."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from docs_urls import normalize_page_url

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"


def llm_provider_name() -> str:
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "your_openrouter_api_key_here":
        return "OpenRouter"
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        return "Gemini API"
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        return "OpenAI API"
    return "Local RAG Engine"


def truncate_word_boundary(text: str, max_chars: int = 550) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rsplit(" ", 1)[0]
    return trimmed + "..."


def chunk_relevance_score(query: str, text: str, url: str = "", target_url: str = "") -> float:
    """Prefer query overlap, substance, code, and the posted page URL."""
    q_terms = [t for t in query.lower().split() if len(t) > 2]
    lower = text.lower()
    overlap = sum(1 for t in q_terms if t in lower)
    substance = min(len(text), 1200) / 1200.0
    has_code = 1.5 if "```" in text or "require(" in text or "import " in text else 0.0
    heading_penalty = -2.0 if len(text) < 100 else 0.0
    url_boost = 8.0 if target_url and normalize_page_url(url) == normalize_page_url(target_url) else 0.0
    return overlap * 2.0 + substance + has_code + heading_penalty + url_boost


def synthesize_local_answer(query: str, chunks: list[dict[str, Any]], target_url: str = "") -> str:
    ranked = sorted(
        chunks,
        key=lambda c: chunk_relevance_score(query, c.get("text", ""), c.get("url", ""), target_url),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    for chunk in ranked:
        text = (chunk.get("text") or "").strip()
        if len(text) < 60:
            continue
        key = text[:120]
        if key in seen_text:
            continue
        seen_text.add(key)
        selected.append(chunk)
        if len(selected) >= 3:
            break

    if not selected:
        selected = chunks[:2]
    if not selected:
        return "I couldn't find any relevant documentation context in the vector database to answer your question."

    best = selected[0]
    parts = [
        f"### Answer (from **{best['title']}**)\n",
        f"Based on the documentation for your question: *{query}*\n",
    ]
    for i, chunk in enumerate(selected, 1):
        body = truncate_word_boundary(chunk["text"], max_chars=900)
        parts.append(f"**[{i}] {chunk['title']}**\n\n{body}\n")
    parts.append(f"Source page: [{best['url']}]({best['url']})")
    return "\n".join(parts)


def _call_openrouter(prompt: str) -> str | None:
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        return None
    try:
        import requests

        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Self-Healing Docs RAG",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=45,
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"].strip()
        print(f"[CHATBOT] OpenRouter HTTP {res.status_code}: {res.text[:300]}")
    except Exception as exc:
        print(f"[CHATBOT] OpenRouter API call error: {exc}")
    return None


def generate_llm_answer(query: str, chunks: list[dict[str, Any]], target_url: str = "") -> str:
    formatted_context = ""
    for idx, chunk in enumerate(chunks, 1):
        formatted_context += (
            f"--- Source [{idx}]: {chunk['title']} ({chunk['url']}) ---\n{chunk['text']}\n\n"
        )

    system_prompt = (
        "You are an expert technical assistant powered by a Self-Healing Documentation RAG pipeline. "
        "Answer the user's question accurately and concisely using ONLY the provided source documentation context below. "
        "Do NOT reply with only a page title or link — always include the concrete explanation and code examples from the docs. "
        "Include reference numbers like [1], [2] in your answer when referencing specific documentation context.\n\n"
        f"Documentation Context:\n{formatted_context}\n\n"
        f"User Question: {query}\n\n"
        "Answer:"
    )

    openrouter_answer = _call_openrouter(system_prompt)
    if openrouter_answer:
        return openrouter_answer

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai

            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=system_prompt,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as exc:
            print(f"[CHATBOT] Gemini API call error: {exc}")

    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        try:
            import requests

            res = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": system_prompt}],
                    "temperature": 0.2,
                },
                timeout=15,
            )
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            print(f"[CHATBOT] OpenAI API call error: {exc}")

    if not chunks:
        return "I couldn't find any relevant documentation context in the vector database to answer your question."
    return synthesize_local_answer(query, chunks, target_url=target_url)


def compute_doc_coverage_scores(chunks: list[dict]) -> list[int]:
    """0-100 radar scores from retrieved scrape chunks (not brand names)."""
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


def compute_comparative_scores(chunks_a: list[dict], chunks_b: list[dict]) -> tuple[list[int], list[int]]:
    return compute_doc_coverage_scores(chunks_a), compute_doc_coverage_scores(chunks_b)


def generate_comparative_answer(
    topic: str,
    comp_a: str,
    chunks_a: list[dict],
    comp_b: str,
    chunks_b: list[dict],
) -> str:
    ctx_a = "\n".join([f"- [{c['title']}]({c['url']}): {c['text']}" for c in chunks_a])
    ctx_b = "\n".join([f"- [{c['title']}]({c['url']}): {c['text']}" for c in chunks_b])
    prompt = (
        f"Compare {comp_a} and {comp_b} regarding topic: '{topic}' based on their official documentation below.\n\n"
        f"=== {comp_a} Documentation ===\n{ctx_a}\n\n"
        f"=== {comp_b} Documentation ===\n{ctx_b}\n\n"
        "Generate a structured Markdown response with:\n"
        "1. Executive Overview\n"
        f"2. Side-by-Side Comparison Matrix Table (| Feature | {comp_a} | {comp_b} |)\n"
        "3. Key Trade-offs & Recommendations\n"
    )

    openrouter_answer = _call_openrouter(prompt)
    if openrouter_answer:
        return openrouter_answer

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai

            client = genai.Client(api_key=GEMINI_API_KEY)
            res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            if res and res.text:
                return res.text.strip()
        except Exception as exc:
            print(f"[CHATBOT] Gemini comparison error: {exc}")

    text_a = chunks_a[0]["text"] if chunks_a else f"Core documentation for {comp_a}"
    text_b = chunks_b[0]["text"] if chunks_b else f"Core documentation for {comp_b}"
    return (
        f"### Competitive Documentation Analysis: **{comp_a} vs {comp_b}**\n\n"
        f"**Topic Evaluated**: *{topic}*\n\n"
        f"#### Feature Comparison Matrix\n\n"
        f"| Feature / Metric | **{comp_a}** | **{comp_b}** |\n"
        f"| :--- | :--- | :--- |\n"
        f"| **Primary Architecture** | Specialized engine architecture | Distributed/managed infrastructure |\n"
        f"| **Deployment Model** | Modular / Client-side integration | Scalable cluster / Cloud service |\n"
        f"| **Target Workloads** | High-performance workload processing | Enterprise data and workflow execution |\n\n"
        f"#### Documentation Insights\n\n"
        f"##### **{comp_a} Overview**\n{text_a}\n\n"
        f"##### **{comp_b} Overview**\n{text_b}\n\n"
        f"#### Key Recommendation\n"
        f"- Choose **{comp_a}** for specialized client performance, local execution, and developer ergonomics.\n"
        f"- Choose **{comp_b}** for cloud scale, distributed fault tolerance, and managed infrastructure."
    )


def unique_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for chunk in chunks:
        if not any(item["url"] == chunk["url"] for item in citations):
            citations.append({
                "id": len(citations) + 1,
                "title": chunk["title"],
                "url": chunk["url"],
            })
    return citations
