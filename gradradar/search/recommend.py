"""Profile-based PI recommendations without an explicit query."""

from __future__ import annotations

import duckdb

from gradradar.search.engine import search_pis
from gradradar.search.llm_query import QueryPlan


def recommend_pis(
    con: duckdb.DuckDBPyConnection,
    profile: dict,
    top: int = 10,
    use_rerank: bool = True,
) -> list[dict]:
    """Generate PI recommendations based on the user's profile.

    Builds a synthetic QueryPlan from profile fields and runs the hybrid search.
    """
    search_terms = profile.get("research_interests", "machine learning")

    # Map profile regions to a single filter (use first preference)
    regions = profile.get("regions", [])
    region = regions[0] if len(regions) == 1 else None

    # Map degree preference
    degree = profile.get("degree_preference", "phd")

    plan = QueryPlan(
        search_terms=search_terms,
        region=region,
        search_type=degree if degree != "both" else "phd",
        limit=top,
        order_by="citation_velocity DESC",
        reasoning=f"Profile-based recommendation: interests='{search_terms}'",
    )

    return search_pis(con, plan, mode="hybrid", use_rerank=use_rerank, profile=profile)
