#!/usr/bin/env python3
"""
scripts/chunk_and_embed.py
Reads scraped JSON from `data/latest_scrape.json`, splits page content into clean chunks,
and embeds them into a local ChromaDB collection (`docs_rag`) using sentence-transformers/all-MiniLM-L6-v2.
"""

import json
import argparse
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

from docs_urls import extract_competitor_tag, normalize_page_url

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

DEFAULT_INPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "latest_scrape.json"
CHROMA_DB_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma_db"
COLLECTION_NAME = "docs_rag"
_TEXT_EMBEDDER = None


def get_text_embedder():
    """Load MiniLM once. Prefer SentenceTransformer; fall back to ONNX on Windows/torch errors."""
    global _TEXT_EMBEDDER
    if _TEXT_EMBEDDER is not None:
        return _TEXT_EMBEDDER
    try:
        _TEXT_EMBEDDER = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2",
            device="cpu",
        )
        return _TEXT_EMBEDDER
    except Exception as exc:
        print(f"[CHUNK_EMBED] ⚠️ SentenceTransformer unavailable ({exc}); using ONNX MiniLM")
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

        _TEXT_EMBEDDER = ONNXMiniLM_L6_V2()
        return _TEXT_EMBEDDER


def embed_texts(texts: List[str]) -> List[List[float]]:
    vectors = get_text_embedder()(list(texts))
    return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]


def open_docs_collection(path: Optional[Path] = None):
    """Open docs_rag without letting a DefaultEmbeddingFunction fallback trigger Chroma config rebuild."""
    db_path = Path(path) if path else CHROMA_DB_DIR
    if not db_path.exists():
        return None
    client = chromadb.PersistentClient(path=str(db_path))
    embedder = get_text_embedder()
    embedder_name = embedder.name() if hasattr(embedder, "name") else ""
    # Chroma only allows a mismatched handle when the stand-in is named "default".
    # Query/upsert always pass embeddings, so the handle EF is never used to encode.
    if embedder_name == "sentence_transformer":
        collection_ef = embedder
    else:
        collection_ef = embedding_functions.DefaultEmbeddingFunction()
    return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=collection_ef)


def query_collection(
    collection,
    query_text: str,
    where: Optional[Dict[str, Any]] = None,
    n_results: int = 4,
):
    """Query with precomputed embeddings so Chroma does not rebuild sentence_transformer from config."""
    kwargs: Dict[str, Any] = {
        "query_embeddings": embed_texts([query_text]),
        "n_results": n_results,
    }
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)


def split_text_into_chunks(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """Splits a document text string into overlapping paragraph chunks.

    Tiny heading-only fragments are merged into the following chunk so retrieval
    never returns a bare section title without the explanatory body/code.
    """
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

    # Merge heading-only / ultra-short chunks into the next body chunk
    merged: List[str] = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        is_heading_only = (
            len(chunk) < 80
            or (chunk.lstrip().startswith("###") and "\n" not in chunk.strip() and len(chunk) < 120)
        )
        if is_heading_only and i + 1 < len(chunks):
            merged.append(chunk + "\n\n" + chunks[i + 1])
            i += 2
        else:
            merged.append(chunk)
            i += 1

    return merged


def chunk_and_embed(input_path: Path = DEFAULT_INPUT_PATH, competitor_tag: str = None, page_scoped: bool = False) -> int:
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
    collection = open_docs_collection(CHROMA_DB_DIR)
    if collection is None:
        print("[CHUNK_EMBED] ❌ Could not open Chroma collection.")
        return 0

    print(f"[CHUNK_EMBED] ⚙️ Upserting {total_chunks} chunks into ChromaDB collection '{COLLECTION_NAME}'...")

    # Replace prior vectors so stale stub/mock pages cannot pollute retrieval.
    # page_scoped=True only drops chunks for the URLs being re-indexed.
    tag_for_delete = competitor_tag if competitor_tag else extract_competitor_tag(pages[0].get("url", ""))
    try:
        existing = collection.get(where={"competitor": tag_for_delete}, include=["metadatas"])
        old_ids = existing.get("ids") or []
        if page_scoped:
            keep_urls = {normalize_page_url(p.get("url", "")) for p in pages}
            old_ids = [
                i for i, m in zip(old_ids, existing.get("metadatas") or [])
                if normalize_page_url((m or {}).get("url", "")) in keep_urls
            ]
        if old_ids:
            collection.delete(ids=old_ids)
            print(f"[CHUNK_EMBED] 🧹 Removed {len(old_ids)} stale chunks for competitor '{tag_for_delete}'")
    except Exception as e:
        print(f"[CHUNK_EMBED] ⚠️ Stale-chunk cleanup skipped: {e}")

    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        embeddings=embed_texts(documents),
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
