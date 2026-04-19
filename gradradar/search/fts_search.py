"""DuckDB full-text search with BM25 ranking."""

import duckdb


def fts_search_pis(con: duckdb.DuckDBPyConnection, search_terms: str, limit: int = 100) -> list[dict]:
    """Search PIs using BM25 full-text search.

    Uses a two-pass approach:
    1. Search research_description (high signal, enriched PIs only)
    2. Fall back to paper title search if not enough results

    Returns list of dicts with id, name, score, and basic PI info.
    """
    # Primary: search enriched PIs by research description using ILIKE
    # This is more accurate than BM25 on paper titles for finding relevant PIs
    terms = [t.strip() for t in search_terms.split() if len(t.strip()) > 2]
    if not terms:
        return []

    # Build ILIKE conditions — match any term in research_description or name
    desc_conditions = " OR ".join(
        [f"p.research_description ILIKE '%' || ? || '%'" for _ in terms]
    )
    params = list(terms)

    results = con.execute(f"""
        SELECT
            p.id, p.name, p.institution_id, p.h_index, p.total_citations,
            p.theory_category, p.is_taking_students, p.career_stage,
            p.research_description
        FROM pis p
        WHERE p.research_description IS NOT NULL
          AND ({desc_conditions})
        ORDER BY p.h_index DESC
        LIMIT ?
    """, params + [limit]).fetchall()

    # If not enough results, supplement with BM25 on paper titles
    if len(results) < limit:
        existing_ids = {str(r[0]) for r in results}
        bm25_results = con.execute("""
            SELECT * FROM (
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
                WHERE p.research_description IS NOT NULL
            ) sub
            WHERE score IS NOT NULL
            ORDER BY score
            LIMIT ?
        """, [search_terms, limit]).fetchall()

        for r in bm25_results:
            if str(r[0]) not in existing_ids and len(results) < limit:
                results.append((r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8], r[9]))
                existing_ids.add(str(r[0]))

    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "bm25_score": 0.0,
            "institution_id": str(r[2]) if r[2] else None,
            "h_index": r[3],
            "total_citations": r[4],
            "theory_category": r[5],
            "is_taking_students": r[6],
            "career_stage": r[7],
            "research_description": r[8],
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
