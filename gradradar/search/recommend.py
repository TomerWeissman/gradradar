"""Profile-based PI recommendations without an explicit query."""

from __future__ import annotations

import re

import duckdb

from gradradar.search.engine import search_pis
from gradradar.search.llm_query import QueryPlan


def recommend_pis(
    con: duckdb.DuckDBPyConnection,
    profile: str,
    top: int = 10,
    use_rerank: bool = True,
) -> list[dict]:
    """Generate PI recommendations based on the user's profile.

    Extracts the Research Interests section from the profile markdown
    and uses it as search terms.
    """
    search_terms = _extract_interests(profile)

    plan = QueryPlan(
        search_terms=search_terms,
        search_type="phd",
        limit=top,
        order_by="citation_velocity DESC",
        reasoning=f"Profile-based recommendation: '{search_terms[:80]}'",
    )

    return search_pis(con, plan, mode="hybrid", use_rerank=use_rerank, profile=profile)


def _extract_interests(profile: str) -> str:
    """Pull the Research Interests section content from profile markdown."""
    # Find text between "## Research Interests" and the next "##" heading
    match = re.search(
        r"##\s*Research Interests\s*\n(.*?)(?=\n##|\Z)",
        profile,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        text = match.group(1).strip()
        # Remove template example lines
        lines = [
            l for l in text.splitlines()
            if l.strip() and not l.strip().startswith("Example:")
            and not l.strip().startswith("What topics")
        ]
        text = " ".join(lines).strip()
        if text:
            return text

    # Fallback: use first 200 chars of the profile
    clean = re.sub(r"#.*?\n", "", profile)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:200] if clean else "machine learning"
