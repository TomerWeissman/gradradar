"""Incrementally push a set of PIs (and their institutions) from local DuckDB to Supabase.

Unlike seed_cloud.py (a one-time bulk COPY into empty tables), this is safe against the
live DB: new rows are inserted, OpenAlex stats are refreshed, and enrichment fields are
only filled where the hosted value is empty — community contributions always win.

Dry run by default (rolls back); pass --apply to commit.

Usage:
    export SUPABASE_DB_URL='postgresql://...'
    GRADRADAR_HOME=~/.gradradar/finance_build \\
        python scripts/push_pis.py --openalex-ids ~/.gradradar/finance_build/db/authors_finance_us.json [--apply]
"""

import argparse
import io
import json
import os
import sys

import duckdb
import psycopg2

from gradradar.config import get_db_path

INSTITUTION_COLS = ["id", "name", "country", "region", "city", "type"]

# Refreshed from OpenAlex on every build, so the local value is newer.
STAT_COLS = [
    "h_index", "total_citations", "citations_last_5_years", "citation_velocity",
    "citation_velocity_source", "paper_count", "paper_count_last_3_years",
    "theory_category", "theory_category_source",
]

# Scraped/contributed fields: never overwrite a non-empty hosted value.
ENRICH_COLS = [
    "personal_url", "lab_url", "email", "career_stage", "is_taking_students",
    "taking_students_confidence", "taking_students_checked_at", "current_student_count",
    "funding_sources", "lab_name", "short_bio", "department_name", "research_description",
    "scraped_at", "source_url",
]

PI_COLS = ["id", "name", "institution_id", "openalex_id"] + STAT_COLS + ENRICH_COLS


def export_csv(duck, sql: str, params: list) -> str:
    """Run a query against DuckDB and return the result as CSV text."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        path = tmp.name
    # Materialize first: COPY (query) doesn't accept bound parameters.
    duck.execute(f"CREATE OR REPLACE TEMP TABLE _push AS {sql}", params)
    duck.execute(f"COPY _push TO '{path}' (FORMAT CSV, HEADER, QUOTE '\"', ESCAPE '\"')")
    text = Path(path).read_text()
    Path(path).unlink()
    return text


def load_temp(cur, table: str, cols: list[str], csv_text: str):
    """Create a temp copy of a public table's shape and COPY rows into it."""
    cur.execute(f"CREATE TEMP TABLE tmp_{table} (LIKE public.{table} INCLUDING DEFAULTS) ON COMMIT DROP")
    cur.copy_expert(
        f"COPY tmp_{table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT CSV, HEADER true)",
        io.StringIO(csv_text),
    )


def push(pg, duck, openalex_ids: list[str]) -> dict:
    pis_csv = export_csv(
        duck, f"SELECT {', '.join(PI_COLS)} FROM pis WHERE list_contains(?, openalex_id)", [openalex_ids]
    )
    inst_csv = export_csv(duck, f"""
        SELECT DISTINCT {', '.join('i.' + c for c in INSTITUTION_COLS)}
        FROM institutions i JOIN pis p ON p.institution_id = i.id
        WHERE list_contains(?, p.openalex_id)
    """, [openalex_ids])

    stats = {}
    with pg.cursor() as cur:
        load_temp(cur, "institutions", INSTITUTION_COLS, inst_csv)
        load_temp(cur, "pis", PI_COLS, pis_csv)

        cur.execute(f"""
            INSERT INTO public.institutions ({', '.join(INSTITUTION_COLS)})
            SELECT {', '.join(INSTITUTION_COLS)} FROM tmp_institutions
            ON CONFLICT (id) DO NOTHING
        """)
        stats["institutions_inserted"] = cur.rowcount

        cur.execute("SELECT count(*) FROM tmp_pis t WHERE NOT EXISTS (SELECT 1 FROM public.pis p WHERE p.id = t.id)")
        stats["pis_new"] = cur.fetchone()[0]

        stat_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in STAT_COLS)
        # NULLIF(.., '') treats empty strings as missing so they get filled too.
        enrich_set = ", ".join(
            f"{c} = COALESCE(NULLIF(public.pis.{c}::text, '')::{_pg_type(cur, c)}, EXCLUDED.{c})"
            for c in ENRICH_COLS
        )
        cur.execute(f"""
            INSERT INTO public.pis ({', '.join(PI_COLS)})
            SELECT {', '.join(PI_COLS)} FROM tmp_pis
            ON CONFLICT (id) DO UPDATE SET {stat_set}, {enrich_set}
        """)
        stats["pis_upserted"] = cur.rowcount

        cur.execute("SELECT count(*) FROM tmp_pis WHERE research_description IS NOT NULL")
        stats["pis_with_description"] = cur.fetchone()[0]
    return stats


_type_cache: dict[str, str] = {}


def _pg_type(cur, col: str) -> str:
    """Postgres type of a public.pis column, for casting back after NULLIF on text."""
    if col not in _type_cache:
        cur.execute(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'public.pis'::regclass AND attname = %s", [col]
        )
        _type_cache[col] = cur.fetchone()[0]
    return _type_cache[col]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--openalex-ids", required=True, help="JSON list of OpenAlex author IDs to push")
    parser.add_argument("--apply", action="store_true", help="Commit (default is a dry run that rolls back)")
    args = parser.parse_args()

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set (Supabase → Project Settings → Database).", file=sys.stderr)
        return 1

    with open(args.openalex_ids) as f:
        openalex_ids = json.load(f)

    duck = duckdb.connect(str(get_db_path()), read_only=True)
    pg = psycopg2.connect(db_url)
    try:
        stats = push(pg, duck, openalex_ids)
        for k, v in stats.items():
            print(f"  {k}: {v:,}")
        if args.apply:
            pg.commit()
            print("Committed.")
        else:
            pg.rollback()
            print("Dry run — rolled back. Re-run with --apply to commit.")
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
        duck.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
