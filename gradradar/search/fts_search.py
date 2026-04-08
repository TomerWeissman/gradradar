"""DuckDB full-text search with BM25 ranking."""

import duckdb


def fts_search_pis(con: duckdb.DuckDBPyConnection, search_terms: str, limit: int = 100) -> list[dict]:
    """Search PIs using BM25 full-text search.

    Returns list of dicts with id, name, score, and basic PI info.
    """
    results = con.execute("""
        SELECT
            ps.id,
            ps.name,
            fts_main_pi_search_docs_fts.match_bm25(ps.id, ?) AS score,
            p.institution_id,
            p.h_index,
            p.total_citations,
            p.theory_category,
            p.is_taking_students,
            p.career_stage,
            p.research_description
        FROM pi_search_docs_fts ps
        JOIN pis p ON p.id = ps.id
        WHERE score IS NOT NULL
        ORDER BY score
        LIMIT ?
    """, [search_terms, limit]).fetchall()

    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "bm25_score": r[2],
            "institution_id": str(r[3]) if r[3] else None,
            "h_index": r[4],
            "total_citations": r[5],
            "theory_category": r[6],
            "is_taking_students": r[7],
            "career_stage": r[8],
            "research_description": r[9],
        }
        for r in results
    ]


def fts_search_papers(con: duckdb.DuckDBPyConnection, search_terms: str, limit: int = 100) -> list[dict]:
    """Search papers using BM25 full-text search."""
    results = con.execute("""
        SELECT
            id, title, abstract, year, venue, citation_count,
            fts_main_papers.match_bm25(id, ?) AS score
        FROM papers
        WHERE score IS NOT NULL
        ORDER BY score
        LIMIT ?
    """, [search_terms, limit]).fetchall()

    return [
        {
            "id": str(r[0]),
            "title": r[1],
            "abstract": r[2],
            "year": r[3],
            "venue": r[4],
            "citation_count": r[5],
            "bm25_score": r[6],
        }
        for r in results
    ]


def fts_search_programs(con: duckdb.DuckDBPyConnection, search_terms: str, limit: int = 100) -> list[dict]:
    """Search programs using BM25 full-text search."""
    results = con.execute("""
        SELECT
            ps.id,
            ps.name,
            fts_main_program_search_docs_fts.match_bm25(ps.id, ?) AS score
        FROM program_search_docs_fts ps
        WHERE score IS NOT NULL
        ORDER BY score
        LIMIT ?
    """, [search_terms, limit]).fetchall()

    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "bm25_score": r[2],
        }
        for r in results
    ]
