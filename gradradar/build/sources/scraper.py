"""HTML fetching with httpx primary and playwright fallback.

Handles rate limiting, caching, and JS-rendered pages.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx

from gradradar.config import get_cache_path

# Domains that require JS rendering (expanded as we discover them)
JS_REQUIRED_DOMAINS = {
    "scholar.google.com",
    "research-hub.com",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def fetch_html(url: str, use_cache: bool = True, force_js: bool = False) -> str | None:
    """Fetch HTML from a URL. Returns None on failure.

    Tries httpx first, falls back to playwright for JS-heavy sites.
    Caches results in ~/.gradradar/cache/raw_html/.
    """
    if use_cache:
        cached = _read_cache(url)
        if cached is not None:
            return cached

    needs_js = force_js or any(d in url for d in JS_REQUIRED_DOMAINS)

    if needs_js:
        html = _fetch_playwright(url)
    else:
        html = _fetch_httpx(url)
        # If httpx returns very little content, try playwright as fallback
        if html and len(html) < 500 and "<noscript" in html.lower():
            html = _fetch_playwright(url)

    if html and use_cache:
        _write_cache(url, html)

    return html


def _fetch_httpx(url: str, timeout: float = 15.0) -> str | None:
    """Fetch with httpx. Handles redirects and common errors."""
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except (httpx.HTTPError, httpx.TimeoutException):
        return None


def _fetch_playwright(url: str, timeout: int = 20000) -> str | None:
    """Fetch with playwright for JS-rendered pages."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=timeout, wait_until="networkidle")
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def extract_text(html: str) -> str:
    """Extract readable text from HTML using trafilatura, falling back to BS4."""
    try:
        import trafilatura
        text = trafilatura.extract(html, include_links=False, include_tables=False)
        if text and len(text) > 100:
            return text
    except Exception:
        pass

    # Fallback: BeautifulSoup
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    # Remove script/style tags
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    return soup.get_text(separator="\n", strip=True)


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _cache_dir() -> Path:
    return get_cache_path() / "raw_html"


def _read_cache(url: str) -> str | None:
    path = _cache_dir() / f"{_cache_key(url)}.html"
    if path.exists():
        return path.read_text()
    return None


def _write_cache(url: str, html: str):
    path = _cache_dir() / f"{_cache_key(url)}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
