"""Discover PI homepage/faculty URLs via DuckDuckGo search.

For each PI, constructs a targeted search query and returns the best candidate URL.
"""

from __future__ import annotations

import time

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
}


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

    for r in results:
        url = r.get("href", "")
        if _is_good_faculty_url(url):
            return url

    # Fallback: return first non-skip result
    for r in results:
        url = r.get("href", "")
        if not any(skip in url for skip in SKIP_DOMAINS):
            return url

    return None


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

    # Skip known non-useful domains
    if any(skip in url_lower for skip in SKIP_DOMAINS):
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
