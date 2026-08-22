#!/usr/bin/env python3
"""Verify OpenRouter RAG answers against indexed Chroma chunks."""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

import requests

from chunk_and_embed import open_docs_collection, query_collection

OUT = ROOT / "docs" / "proof_rag_answers.json"


def ask(col, q: str, competitor: str) -> dict:
    res = query_collection(col, q, where={"competitor": competitor}, n_results=4)
    chunks = []
    if res.get("documents") and res["documents"][0]:
        for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
            chunks.append({"text": doc, "title": meta.get("title"), "url": meta.get("url")})

    ctx = "\n\n".join(
        f"[{i}] {c['title']} ({c['url']})\n{c['text'][:900]}" for i, c in enumerate(chunks, 1)
    )
    prompt = (
        "Answer using ONLY this docs context. Include [n] citations and concrete steps/code.\n\n"
        f"Context:\n{ctx}\n\nQuestion: {q}\nAnswer:"
    )
    key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "RAG-Verify",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=60,
    )
    answer = ""
    if r.status_code == 200:
        answer = r.json()["choices"][0]["message"]["content"]
    else:
        answer = f"ERROR {r.status_code}: {r.text[:300]}"

    return {
        "question": q,
        "competitor": competitor,
        "http": r.status_code,
        "chunks": len(chunks),
        "citations": [c["url"] for c in chunks],
        "answer": answer,
    }


def main():
    col = open_docs_collection(ROOT / "data" / "chroma_db")
    results = [
        ask(col, "how can we use debug in our own code?", "Expressjs"),
        ask(col, "How do I install the DuckDB Python client and what is the minimum Python version?", "Duckdb"),
        ask(col, "How do I set DEBUG for Express on Windows?", "Expressjs"),
    ]
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for row in results:
        print("===", row["competitor"], row["question"])
        print("HTTP", row["http"], "chunks", row["chunks"])
        print(row["answer"][:700])
        print("CITES", row["citations"])
        print()
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
