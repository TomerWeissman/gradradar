"""Hybrid search orchestration (FTS + SQL + LLM re-ranking)."""

from __future__ import annotations

import duckdb

from gradradar.search.fts_search import fts_search_pis, fts_search_papers, fts_search_programs
from gradradar.search.sql_search import sql_filter_pis, get_top_papers_for_pi
from gradradar.search.llm_query import QueryPlan
from gradradar.search.narrator import narrate
from gradradar.search.reranker import rerank


def search_pis(
    con: duckdb.DuckDBPyConnection,
    plan: QueryPlan,
    mode: str = "hybrid",
    use_rerank: bool = True,
    profile: str | None = None,
) -> list[dict]:
    """Execute a PI search using the given QueryPlan.

    Modes:
      - "fts": BM25 full-text search only
      - "sql": structured SQL filter only
      - "hybrid": FTS to get candidates, then SQL filter + sort + LLM re-rank
    """
    if mode == "fts":
        results = fts_search_pis(con, plan.search_terms, limit=plan.limit)
        results = _enrich_results(con, results)
        if use_rerank:
            results = rerank(plan.search_terms, results, top_k=plan.limit, profile=profile)
        return results

    if mode == "sql":
        results = sql_filter_pis(
            con,
            region=plan.region,
            is_taking_students=plan.is_taking_students,
            theory_category=plan.theory_category,
            min_h_index=plan.min_h_index,
            max_h_index=plan.max_h_index,
            career_stage=plan.career_stage,
            institution_name=plan.institution_name,
            order_by=plan.order_by,
            limit=plan.limit,
        )
        return _enrich_results(con, results)

    # hybrid: FTS → SQL filter → enrich → LLM re-rank
    # Fetch more candidates than needed so re-ranker has good options
    fetch_limit = max(plan.limit * 3, 30)

    fts_results = fts_search_pis(con, plan.search_terms, limit=200)
    candidate_ids = [r["id"] for r in fts_results]

    if not candidate_ids:
        results = sql_filter_pis(
            con,
            region=plan.region,
            is_taking_students=plan.is_taking_students,
            theory_category=plan.theory_category,
            min_h_index=plan.min_h_index,
            max_h_index=plan.max_h_index,
            career_stage=plan.career_stage,
            institution_name=plan.institution_name,
            order_by=plan.order_by,
            limit=plan.limit,
        )
        return _enrich_results(con, results)

    results = sql_filter_pis(
        con,
        candidate_ids=candidate_ids,
        region=plan.region,
        is_taking_students=plan.is_taking_students,
        theory_category=plan.theory_category,
        min_h_index=plan.min_h_index,
        max_h_index=plan.max_h_index,
        career_stage=plan.career_stage,
        institution_name=plan.institution_name,
        order_by=plan.order_by,
        limit=fetch_limit,
    )
    results = _enrich_results(con, results)

    if use_rerank:
        results = rerank(plan.search_terms, results, top_k=plan.limit, profile=profile)

    return results[:plan.limit]


def search_programs(
    con: duckdb.DuckDBPyConnection,
    plan: QueryPlan,
) -> list[dict]:
    """Search Masters programs using FTS."""
    return fts_search_programs(con, plan.search_terms, limit=plan.limit)


def search_papers(
    con: duckdb.DuckDBPyConnection,
    plan: QueryPlan,
) -> list[dict]:
    """Search papers using FTS."""
    return fts_search_papers(con, plan.search_terms, limit=plan.limit)


def _enrich_results(
    con: duckdb.DuckDBPyConnection,
    results: list[dict],
) -> list[dict]:
    """Add top papers to each PI result."""
    for r in results:
        r["top_papers"] = get_top_papers_for_pi(con, r["id"], limit=3)
    return results


def run_search(
    con: duckdb.DuckDBPyConnection,
    plan: QueryPlan,
    mode: str = "hybrid",
    no_rerank: bool = False,
    profile: str | None = None,
    use_narrate: bool = False,
) -> dict:
    """Top-level search dispatcher. Returns a dict with results by type."""
    output = {"query_plan": plan.model_dump(), "pis": [], "programs": []}

    if plan.search_type in ("phd", "both"):
        output["pis"] = search_pis(con, plan, mode=mode, use_rerank=not no_rerank, profile=profile)

        if use_narrate and output["pis"]:
            output["pis"] = narrate(plan.search_terms, output["pis"], profile=profile, con=con)

    if plan.search_type in ("masters", "both"):
        output["programs"] = search_programs(con, plan)

    return output
