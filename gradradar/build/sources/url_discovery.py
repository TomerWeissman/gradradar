"""Discover PI homepage/faculty URLs via DuckDuckGo search.

For each PI, constructs a targeted search query and returns the best candidate URL.
"""

from __future__ import annotations

import re
import time
import unicodedata
from urllib.parse import urlparse

from ddgs import DDGS


# Domains that typically host faculty profiles
FACULTY_DOMAINS = {
    "edu", "ac.uk", "ethz.ch", "epfl.ch", "mpi-inf.mpg.de",
    "cam.ac.uk", "ox.ac.uk", "inria.fr", "mila.quebec",
}

# Domains to skip (not useful as PI pages)
SKIP_DOMAINS = {
    "scholar.google.com", "semanticscholar.org", "linkedin.com",
    "twitter.com", "x.com", "researchgate.net", "orcid.org",
    "openalex.org", "dblp.org", "arxiv.org", "youtube.com",
    "wikipedia.org", "github.com", "amazon.com",
    # Seen returning wrong or useless pages for finance PIs
    "ratemyprofessors.com", "scholar.google.", "research.com",
    "nytimes.com", "foxnews.com", "wsj.com", "bloomberg.com", "cnn.com",
}

# Path fragments of login / SSO redirects, which never hold profile content
LOGIN_MARKERS = ("/idp/", "/sso", "/saml", "/login", "/cas/login")


def find_pi_url(
    pi_name: str,
    institution_name: str,
    delay: float = 1.0,
) -> str | None:
    """Search DuckDuckGo for a PI's faculty/homepage URL.

    Returns the best candidate URL, or None if no good result found.
    """
    query = f'{pi_name} {institution_name} professor homepage'

    try:
        results = DDGS().text(query, max_results=5)
    except Exception:
        return None

    if delay > 0:
        time.sleep(delay)

    # Only consider results whose title/snippet/URL mention the PI; otherwise search
    # tends to hand back a colleague's page or a department directory.
    results = [r for r in results if name_on_page(pi_name, " ".join(
        [r.get("title", ""), r.get("body", ""), r.get("href", "")]))]

    for r in results:
        url = r.get("href", "")
        if _is_good_faculty_url(url):
            return url

    # Fallback: return first usable result even if it doesn't look like a faculty page
    for r in results:
        url = r.get("href", "")
        if _is_usable_url(url):
            return url

    return None


def _fold(text: str) -> str:
    """Lowercase and strip accents so 'Święch' matches 'Swiech'."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


def name_on_page(pi_name: str, text: str) -> bool:
    """True if the PI's surname (last name token longer than an initial) appears in text as a word."""
    tokens = [t for t in re.split(r"[\s.,]+", _fold(pi_name)) if len(t) > 1]
    if not tokens:
        return True  # nothing to check against
    surname = tokens[-1]
    return re.search(rf"\b{re.escape(surname)}\b", _fold(text)) is not None


def _is_usable_url(url: str) -> bool:
    """Reject skip-listed domains, bare site roots (e.g. https://www.mit.edu/) and login pages."""
    url_lower = url.lower()
    if not url_lower or any(skip in url_lower for skip in SKIP_DOMAINS):
        return False
    if any(marker in url_lower for marker in LOGIN_MARKERS):
        return False
    return urlparse(url_lower).path not in ("", "/")


def find_pi_urls_batch(
    pis: list[dict],
    delay: float = 1.5,
) -> dict[str, str | None]:
    """Find URLs for a batch of PIs. Returns {pi_id: url}.

    Each dict in pis must have 'id', 'name', 'institution_name'.
    """
    results = {}
    for pi in pis:
        url = find_pi_url(
            pi["name"],
            pi.get("institution_name", ""),
            delay=delay,
        )
        results[pi["id"]] = url

    return results


def _is_good_faculty_url(url: str) -> bool:
    """Check if a URL looks like a faculty/lab page."""
    url_lower = url.lower()

    if not _is_usable_url(url):
        return False

    # Prefer .edu and known academic domains
    if any(domain in url_lower for domain in FACULTY_DOMAINS):
        return True

    # Accept URLs with faculty-like path components
    faculty_signals = ["/faculty/", "/people/", "/~", "/staff/", "/professor/",
                       "/researcher/", "/lab/", "/group/", "/team/"]
    if any(signal in url_lower for signal in faculty_signals):
        return True

    return False
