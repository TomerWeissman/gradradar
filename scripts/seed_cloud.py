"""Seed Supabase Postgres with institutions/departments/pis from local DuckDB.

Reads connection string from SUPABASE_DB_URL env var. Exports each table from
DuckDB as CSV and streams it into Postgres with COPY — fastest path for 67K rows
and handles quoting correctly.

Usage:
    export SUPABASE_DB_URL='postgresql://postgres:[PASSWORD]@db.<ref>.supabase.co:5432/postgres'
    python scripts/seed_cloud.py
"""

import io
import os
import sys
from pathlib import Path

import duckdb
import psycopg2

from gradradar.config import get_db_path

# Columns to copy per table. Must match CSV column order produced by DuckDB.
# search_vector is intentionally excluded — it's populated by the Postgres trigger.
TABLE_COLUMNS = {
    "institutions": [
        "id", "name", "country", "region", "city", "type",
        "qs_cs_ranking", "us_news_ranking", "shanghai_ranking", "prestige_tier",
        "url", "scraped_at", "content_hash", "source_url",
    ],
    "departments": [
        "id", "institution_id", "name", "field",
        "phd_cohort_size", "phd_acceptance_rate", "phd_funding_guarantee",
        "phd_funding_years", "phd_average_stipend", "admission_type",
        "application_deadline", "gre_required", "english_proficiency",
        "url", "scraped_at", "content_hash", "source_url",
    ],
    "pis": [
        "id", "name", "department_id", "institution_id",
        "personal_url", "lab_url", "google_scholar_url",
        "semantic_scholar_id", "openalex_id", "email",
        "career_stage", "phd_year", "phd_institution", "advisor_id",
        "year_started_position", "h_index", "total_citations",
        "citations_last_5_years", "citation_velocity", "citation_velocity_source",
        "paper_count", "paper_count_last_3_years",
        "is_taking_students", "taking_students_confidence", "taking_students_checked_at",
        "current_student_count", "funding_sources", "funding_expiry",
        "lab_name", "short_bio", "department_name", "research_description",
        "theory_category", "theory_category_source",
        "scraped_at", "content_hash", "source_url",
    ],
}


def export_table_to_csv(duck_con: duckdb.DuckDBPyConnection, table: str, cols: list[str]) -> str:
    """Return the table as a CSV string (header + rows, RFC 4180 quoting)."""
    col_list = ", ".join(cols)
    buf = io.StringIO()
    # DuckDB's COPY supports writing to a file; for streaming to a Python string
    # we fetch rows and format manually. But 67K rows with psycopg2's copy_expert
    # needs a file-like object — use DuckDB's to_csv via a temp file or just
    # iterate. Simpler and fast enough: use DuckDB's native COPY to a tempfile.
    import tempfile
    with tempfile.NamedTemporaryFile(mode="r", suffix=".csv", delete=False) as tmp:
        path = tmp.name
    duck_con.execute(f"""
        COPY (SELECT {col_list} FROM {table})
        TO '{path}' (FORMAT CSV, HEADER, QUOTE '"', ESCAPE '"')
    """)
    with open(path) as f:
        csv_text = f.read()
    Path(path).unlink()
    return csv_text


def copy_into_postgres(pg_con, table: str, cols: list[str], csv_text: str) -> int:
    """Stream a CSV string into Postgres via COPY. Returns row count inserted."""
    col_list = ", ".join(cols)
    with pg_con.cursor() as cur:
        cur.copy_expert(
            f"COPY public.{table} ({col_list}) FROM STDIN WITH (FORMAT CSV, HEADER true)",
            io.StringIO(csv_text),
        )
        rows = cur.rowcount
    return rows


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set.", file=sys.stderr)
        print("Get it from Supabase Dashboard → Project Settings → Database → Connection string.", file=sys.stderr)
        return 1

    duck_path = get_db_path()
    print(f"Reading from DuckDB: {duck_path}")
    duck_con = duckdb.connect(str(duck_path), read_only=True)

    print(f"Connecting to Postgres...")
    pg_con = psycopg2.connect(db_url)
    pg_con.autocommit = False

    try:
        for table, cols in TABLE_COLUMNS.items():
            local_count = duck_con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"\n[{table}] exporting {local_count:,} rows from DuckDB...")
            if local_count == 0:
                print(f"[{table}] empty, skipping")
                continue
            csv_text = export_table_to_csv(duck_con, table, cols)
            print(f"[{table}] CSV size: {len(csv_text):,} bytes")

            print(f"[{table}] streaming to Postgres...")
            inserted = copy_into_postgres(pg_con, table, cols, csv_text)
            print(f"[{table}] inserted {inserted:,} rows")

        pg_con.commit()
        print("\nCommitted.")

        # Verification
        print("\nVerification (remote row counts):")
        with pg_con.cursor() as cur:
            for table in TABLE_COLUMNS:
                cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                n = cur.fetchone()[0]
                print(f"  {table}: {n:,}")
    except Exception:
        pg_con.rollback()
        print("\nRolled back due to error.", file=sys.stderr)
        raise
    finally:
        pg_con.close()
        duck_con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
