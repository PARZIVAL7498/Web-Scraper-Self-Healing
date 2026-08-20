#!/usr/bin/env python3
"""
scripts/chunk_and_embed.py
Reads scraped JSON from `data/latest_scrape.json`, splits page content into clean chunks,
and embeds them into a local ChromaDB collection (`docs_rag`) using sentence-transformers/all-MiniLM-L6-v2.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse

import chromadb
from chromadb.utils import embedding_functions

DEFAULT_INPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "latest_scrape.json"
CHROMA_DB_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma_db"
COLLECTION_NAME = "docs_rag"


def normalize_url(url: str) -> str:
    """Normalizes input URL by prepending https:// if protocol scheme is missing."""
    if not url:
        return "https://duckdb.org/docs/"
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def extract_competitor_tag(url: str) -> str:
    """Extracts clean competitor brand tag from URL (e.g., 'Temporal', 'Duckdb', 'Render', 'Deno', 'Drizzle')."""
    url = normalize_url(url)
    parsed = urlparse(url)
    domain = (parsed.netloc or "unknown").replace("www.", "").lower()
    parts = domain.split(".")

    generic_subdomains = {
        "docs", "doc", "documentation", "api", "developer", "developers",
        "v1", "v2", "v3", "help", "guide", "learn", "blog", "app", "dev", "portal", "orm"
    }
    common_tlds = {"com", "org", "io", "co", "dev", "net", "ai", "app", "rs", "sh", "uk", "ca", "team", "tech", "xyz"}

    filtered = [p for p in parts if p not in generic_subdomains and p not in common_tlds]

    if filtered:
        name = filtered[0]
    else:
        non_tld = [p for p in parts if p not in common_tlds]
        name = non_tld[0] if non_tld else parts[0]

    return name.capitalize()


def split_text_into_chunks(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """Splits a document text string into overlapping paragraph chunks."""
    if not text:
        return []

    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para_str = para.strip()
        if not para_str:
            continue

        if len(current_chunk) + len(para_str) + 2 <= chunk_size:
            current_chunk += ("\n\n" + para_str) if current_chunk else para_str
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = para_str

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def chunk_and_embed(input_path: Path = DEFAULT_INPUT_PATH, competitor_tag: str = None) -> int:
    """Reads JSON pages, splits content into vector chunks, and upserts to local ChromaDB."""
    if not input_path.exists():
        print(f"[CHUNK_EMBED] ❌ Input file not found: {input_path}")
        return 0

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            pages = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[CHUNK_EMBED] ❌ Invalid JSON in {input_path}: {e}")
            return 0

    if not isinstance(pages, list) or len(pages) == 0:
        print("[CHUNK_EMBED] ⚠️ Scraped payload is empty. Nothing to embed.")
        return 0

    print(f"[CHUNK_EMBED] 📦 Processing {len(pages)} document pages from '{input_path}'...")

    documents = []
    metadatas = []
    ids = []

    total_chunks = 0
    for page_idx, page in enumerate(pages):
        url = page.get("url", "")
        title = page.get("title", f"Document Page {page_idx+1}")
        content = page.get("content", "")

        tag = competitor_tag if competitor_tag else extract_competitor_tag(url)

        chunks = split_text_into_chunks(content, chunk_size=600, chunk_overlap=80)

        for chunk_idx, chunk_text in enumerate(chunks):
            doc_id = f"{tag.lower()}_p{page_idx}_c{chunk_idx}_{hash(url + chunk_text[:20]) & 0xffffffff:x}"
            documents.append(chunk_text)
            metadatas.append({
                "url": url,
                "title": title,
                "competitor": tag,
                "chunk_index": chunk_idx,
                "page_index": page_idx
            })
            ids.append(doc_id)
            total_chunks += 1

    if total_chunks == 0:
        print("[CHUNK_EMBED] ⚠️ Zero valid text chunks created.")
        return 0

    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    
    try:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    except Exception as e:
        print(f"[CHUNK_EMBED] ⚠️ SentenceTransformer load fallback: {e}")
        ef = embedding_functions.DefaultEmbeddingFunction()

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef
    )

    print(f"[CHUNK_EMBED] ⚙️ Upserting {total_chunks} chunks into ChromaDB collection '{COLLECTION_NAME}'...")
    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"[CHUNK_EMBED] ✅ Successfully indexed {total_chunks} chunks into vector store at '{CHROMA_DB_DIR}'!")
    return total_chunks


def main():
    parser = argparse.ArgumentParser(description="Chunk and Embed scraped docs into ChromaDB")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH), help="Path to input scraped JSON")
    parser.add_argument("--competitor", default=None, help="Competitor tag override")
    args = parser.parse_args()

    chunk_and_embed(Path(args.input), args.competitor)


if __name__ == "__main__":
    main()
