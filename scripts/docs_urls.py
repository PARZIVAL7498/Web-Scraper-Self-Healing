#!/usr/bin/env python3
"""Shared URL, brand, and Bright Data credential helpers."""

from __future__ import annotations

import os
from urllib.parse import urlparse

DEFAULT_DOCS_URL = "https://duckdb.org/docs/"
DEFAULT_COLLECTOR_ID = "c_sample_collector_12345"

GENERIC_SUBDOMAINS = {
    "docs", "doc", "documentation", "documents", "api",
    "developer", "developers", "v1", "v2", "v3",
    "help", "guide", "learn", "blog", "app", "dev", "portal", "orm",
}
COMMON_TLDS = {
    "com", "org", "io", "co", "dev", "net", "ai", "app",
    "rs", "sh", "uk", "ca", "team", "tech", "xyz",
}
GENERIC_PATH_TOKENS = {
    "docs", "doc", "documentation", "en", "current", "latest",
    "api", "guide", "reference", "www",
}
PATH_STOP_WORDS = {
    "docs", "doc", "html", "htm", "api", "current", "latest", "www", "guide", "en",
}


def normalize_url(url: str | None, default: str = DEFAULT_DOCS_URL) -> str:
    """Prepend https:// when the scheme is missing."""
    if not url or not str(url).strip():
        return default
    cleaned = str(url).strip()
    if not cleaned.startswith(("http://", "https://")):
        return "https://" + cleaned
    return cleaned


def normalize_page_url(url: str | None) -> str:
    """Comparable page identity: lowercase, no fragment, no trailing slash."""
    return (url or "").strip().lower().split("#")[0].rstrip("/")


def get_domain(url: str | None) -> str:
    return urlparse(normalize_url(url)).netloc.lower()


def extract_brand(url: str | None) -> str:
    """Brand tag from a docs URL (expressjs.com -> Expressjs)."""
    parsed = urlparse(normalize_url(url))
    domain = (parsed.netloc or "unknown").replace("www.", "").lower()
    parts = domain.split(".")
    filtered = [p for p in parts if p not in GENERIC_SUBDOMAINS and p not in COMMON_TLDS]
    if filtered:
        name = filtered[0]
    else:
        non_tld = [p for p in parts if p not in COMMON_TLDS]
        name = non_tld[0] if non_tld else parts[0]
    return name.capitalize()


extract_competitor_tag = extract_brand
extract_clean_brand = extract_brand


def is_specific_docs_page(url: str | None) -> bool:
    """True for a concrete article, false for a site or /docs/ root."""
    parts = [p for p in urlparse(normalize_page_url(url)).path.split("/") if p]
    return any(p.lower() not in GENERIC_PATH_TOKENS for p in parts)


def url_path_query_terms(url: str | None) -> str:
    """Slug words from the path, used to ground retrieval to the posted page."""
    raw = urlparse(normalize_page_url(url)).path.replace("-", " ").replace("_", " ").replace("/", " ")
    return " ".join(t for t in raw.split() if len(t) > 2 and t.lower() not in PATH_STOP_WORDS)


def is_placeholder_api_key(key: str | None) -> bool:
    """True when Bright Data auth is missing or still the .env.example dummy."""
    k = (key or "").strip()
    if not k:
        return True
    lowered = k.lower()
    return lowered.startswith("your_") or "api_key_here" in lowered


def is_placeholder_collector(collector_id: str | None) -> bool:
    """True for empty / sample / .env.example collector ids."""
    cid = (collector_id or "").strip()
    if not cid:
        return True
    lowered = cid.lower()
    return (
        lowered.startswith("c_sample")
        or lowered.startswith("c_your_")
        or "your_collector" in lowered
        or "placeholder" in lowered
    )


def is_studio_ready(collector_id: str | None, api_key: str | None = None) -> bool:
    """Studio CLI path requires a real collector and a real API key."""
    if api_key is None:
        api_key = os.getenv("BRIGHTDATA_API_KEY")
    return not is_placeholder_collector(collector_id) and not is_placeholder_api_key(api_key)


def collector_id(default: str = DEFAULT_COLLECTOR_ID) -> str:
    return os.getenv("BRIGHTDATA_COLLECTOR_ID", default)
