"""Structured SQL query execution against DuckDB."""

import duckdb


def sql_filter_pis(
    con: duckdb.DuckDBPyConnection,
    candidate_ids: list[str] = None,
    region: str = None,
    is_taking_students: str = None,
    theory_category: str = None,
    min_h_index: int = None,
    max_h_index: int = None,
    career_stage: str = None,
    institution_name: str = None,
    order_by: str = "total_citations DESC",
    limit: int = 50,
) -> list[dict]:
    """Filter PIs by structured criteria. Optionally restrict to candidate IDs from FTS."""
    conditions = []
    params = []

    if candidate_ids:
        placeholders = ", ".join(["?"] * len(candidate_ids))
        conditions.append(f"p.id IN ({placeholders})")
        params.extend(candidate_ids)

    if region:
        conditions.append("i.region = ?")
        params.append(region)

    if is_taking_students:
        conditions.append("p.is_taking_students = ?")
        params.append(is_taking_students)

    if theory_category:
        conditions.append("p.theory_category = ?")
        params.append(theory_category)

    if min_h_index is not None:
        conditions.append("p.h_index >= ?")
        params.append(min_h_index)

    if max_h_index is not None:
        conditions.append("p.h_index <= ?")
        params.append(max_h_index)

    if career_stage:
        conditions.append("p.career_stage = ?")
        params.append(career_stage)

    if institution_name:
        conditions.append("i.name ILIKE ?")
        params.append(f"%{institution_name}%")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Validate order_by to prevent injection
    allowed_orders = {
        "total_citations DESC", "total_citations ASC",
        "h_index DESC", "h_index ASC",
        "citations_last_5_years DESC", "citation_velocity DESC",
        "paper_count DESC", "name ASC",
    }
    if order_by not in allowed_orders:
        order_by = "total_citations DESC"

    params.append(limit)

    results = con.execute(f"""
        SELECT
            p.id, p.name, p.h_index, p.total_citations, p.citations_last_5_years,
            p.citation_velocity, p.citation_velocity_source,
            p.theory_category, p.is_taking_students, p.career_stage,
            p.research_description, p.short_bio, p.department_name,
            p.paper_count, p.paper_count_last_3_years,
            p.personal_url, p.lab_url, p.email, p.lab_name,
            p.taking_students_confidence, p.taking_students_checked_at,
            i.name as institution_name, i.region, i.country
        FROM pis p
        LEFT JOIN institutions i ON i.id = p.institution_id
        WHERE {where_clause}
        ORDER BY {order_by}
        LIMIT ?
    """, params).fetchall()

    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "h_index": r[2],
            "total_citations": r[3],
            "citations_last_5_years": r[4],
            "citation_velocity": r[5],
            "citation_velocity_source": r[6],
            "theory_category": r[7],
            "is_taking_students": r[8],
            "career_stage": r[9],
            "research_description": r[10],
            "short_bio": r[11],
            "department_name": r[12],
            "paper_count": r[13],
            "paper_count_last_3_years": r[14],
            "personal_url": r[15],
            "lab_url": r[16],
            "email": r[17],
            "lab_name": r[18],
            "taking_students_confidence": r[19],
            "taking_students_checked_at": r[20],
            "institution_name": r[21],
            "region": r[22],
            "country": r[23],
        }
        for r in results
    ]


def get_top_papers_for_pi(con: duckdb.DuckDBPyConnection, pi_id: str, limit: int = 5) -> list[dict]:
    """Get top papers for a PI by citation count."""
    results = con.execute("""
        SELECT p.title, p.venue, p.year, p.citation_count, p.doi
        FROM author_paper ap
        JOIN papers p ON p.id = ap.paper_id
        WHERE ap.author_id = ?
        ORDER BY p.citation_count DESC
        LIMIT ?
    """, [pi_id, limit]).fetchall()

    return [
        {"title": r[0], "venue": r[1], "year": r[2], "citation_count": r[3], "doi": r[4]}
        for r in results
    ]
