#!/usr/bin/env python3
"""HTML → docs prose: strip chrome, keep tables/code, rank in-domain links."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from docs_urls import normalize_url


def content_root(soup: BeautifulSoup):
    """Prefer main/article content regions over full-page nav shells."""
    for sel in ("main", "article", "[role='main']", ".markdown", ".theme-doc-markdown", "#content", ".content"):
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 80:
            return node
    return soup


def clean_html_content(soup: BeautifulSoup) -> str:
    """Strip boilerplate and keep headings, paragraphs, lists, code, and tables."""
    root = content_root(soup)
    work = BeautifulSoup(str(root), "html.parser")

    for tag in work(["script", "style", "nav", "footer", "header", "aside", "form", "svg", "noscript", "iframe"]):
        tag.decompose()

    noise_selectors = [
        ".toc", ".sidebar", ".on-this-page", ".table-of-contents",
        ".breadcrumb", ".nav-link", "#table-of-contents", ".onthispage",
        ".theme-doc-toc-mobile", ".theme-doc-sidebar-container",
        ".menu", ".navbar", ".DocSearch", ".sidebar-menu",
    ]
    for sel in noise_selectors:
        for match in work.select(sel):
            match.decompose()

    elements = work.find_all(["h1", "h2", "h3", "p", "pre", "li", "tr"])
    extracted_text = []
    noise_phrases = [
        "on this page", "table of contents", "skip to main content",
        "edit this page", "was this page helpful", "next page", "previous page",
        "search shortcut", "click here if you are not redirected",
    ]

    for elem in elements:
        if elem.name in ("p", "li", "pre") and elem.find_parent("table"):
            continue
        text = elem.get_text(" ", strip=True)
        if not text or len(text) < 3:
            continue
        if any(phrase in text.lower() for phrase in noise_phrases):
            continue

        if elem.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in elem.find_all(["th", "td"])]
            cells = [c for c in cells if c]
            if len(cells) >= 2:
                extracted_text.append(f"{cells[0]}: {' '.join(cells[1:])}")
            continue

        if elem.name in ["h1", "h2", "h3"]:
            extracted_text.append(f"\n### {text}\n")
        elif elem.name == "pre":
            extracted_text.append(f"```\n{text}\n```")
        elif elem.name == "li":
            if len(text) < 45 and "\n" not in text and text.count(" ") < 6:
                continue
            if text.lower() in {
                "copying an in-memory database to a file",
                "see this page as markdown",
                "report content issue",
            }:
                continue
            extracted_text.append(f"• {text}")
        else:
            extracted_text.append(text)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(extracted_text)).strip()


def link_content_score(url: str, anchor_text: str = "") -> int:
    """Higher score = more likely a prose docs page (not install/home/TOC)."""
    path = urlparse(url).path.lower()
    text = (anchor_text or "").lower()
    score = 0
    preferred = (
        "overview", "getting-started", "guide", "tutorial", "api",
        "connect", "client", "python", "installing", "starter", "introduction",
        "sql", "query", "architecture", "feature", "hello-world",
    )
    demoted = ("#", "/install/", "/blog/", "/community/", "/search", "/cdn-cgi/", "/reference")
    for token in preferred:
        if token in path or token in text:
            score += 3
    if path.rstrip("/").endswith("/reference") or "/reference/" in path:
        score -= 4
    for token in demoted:
        if token in path:
            score -= 5
    if path.count("/") >= 3:
        score += 2
    if path.endswith("/") or path.endswith("/index") or path.endswith("/index.html"):
        score -= 1
    return score


def extract_subpage_links(soup: BeautifulSoup, base_url: str, max_links: int = 4) -> list[str]:
    """Ranked internal documentation links on the same host."""
    base_url = normalize_url(base_url)
    base_domain = urlparse(base_url).netloc
    candidates = []

    for a_tag in content_root(soup).find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        full_url = urljoin(base_url, href).split("#")[0].rstrip("/") or urljoin(base_url, href)
        parsed_url = urlparse(full_url)
        if (
            parsed_url.netloc == base_domain
            and parsed_url.scheme in ["http", "https"]
            and full_url != base_url.rstrip("/")
            and not any(ext in parsed_url.path.lower() for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".css", ".js"])
        ):
            candidates.append((link_content_score(full_url, a_tag.get_text(" ", strip=True)), full_url))

    seen: set[str] = set()
    ranked: list[str] = []
    for _score, url in sorted(candidates, key=lambda x: x[0], reverse=True):
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(url)
        if len(ranked) >= max_links:
            break
    return ranked


def looks_like_html(text: str) -> bool:
    sample = (text or "")[:2000].lower()
    return "<html" in sample or "<div" in sample or "<p" in sample or "<article" in sample


def clean_studio_content(content: str) -> str:
    """If Bright Data returns HTML, strip to prose/code."""
    content = (content or "").strip()
    if not content:
        return ""
    if looks_like_html(content):
        try:
            soup = BeautifulSoup(content, "html.parser")
            cleaned = clean_html_content(soup)
            return cleaned if cleaned else soup.get_text("\n", strip=True)
        except Exception:
            return content
    return content
