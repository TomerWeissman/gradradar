"""Write a research description from top paper titles for PIs whose faculty page gave none.

Hosted search only indexes name/description/department/lab, so a PI without a description
is effectively unsearchable. Descriptions written here start with PAPER_PREFIX so they are
recognizable (and replaceable by `gradradar contribute`), and source_url points at the
OpenAlex profile they were derived from.

Usage:
    GRADRADAR_HOME=~/.gradradar/finance_build \\
        python scripts/describe_from_papers.py --openalex-ids ~/.gradradar/finance_build/db/authors_finance_us.json
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import duckdb
import litellm

from gradradar.config import get_db_path, get_extraction_model

litellm.suppress_debug_info = True

PAPER_PREFIX = "Based on publications: "
TITLES_PER_PI = 8

PROMPT = """\
Below are the most-cited paper titles of a researcher. In 2-3 sentences, describe their \
research areas and methods for a prospective PhD student. Describe only what the titles \
support; do not invent affiliations, awards or claims. Output only the description.

Researcher: {name}
Paper titles:
{titles}"""


def pis_needing_description(con, openalex_ids: list[str]) -> list[tuple]:
    """(id, name, openalex_id, [titles]) for PIs with no description but some papers."""
    return con.execute(f"""
        SELECT p.id, p.name, p.openalex_id,
               list(pa.title ORDER BY pa.citation_count DESC NULLS LAST)[1:{TITLES_PER_PI}] AS titles
        FROM pis p
        JOIN author_paper ap ON ap.author_id = p.id
        JOIN papers pa ON pa.id = ap.paper_id
        WHERE list_contains(?, p.openalex_id) AND p.research_description IS NULL AND pa.title IS NOT NULL
        GROUP BY p.id, p.name, p.openalex_id
    """, [openalex_ids]).fetchall()


def describe(name: str, titles: list[str]) -> tuple[str | None, int, int]:
    """Return (description, input_tokens, output_tokens)."""
    resp = litellm.completion(
        model=get_extraction_model(),
        messages=[{"role": "user", "content": PROMPT.format(name=name, titles="\n".join(f"- {t}" for t in titles))}],
        max_tokens=1024,
    )
    text = (resp.choices[0].message.content or "").strip()
    return (text or None), resp.usage.prompt_tokens, resp.usage.completion_tokens


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--openalex-ids", required=True, help="JSON list of OpenAlex author IDs to consider")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    con = duckdb.connect(str(get_db_path()))
    todo = pis_needing_description(con, json.load(open(args.openalex_ids)))
    print(f"{len(todo)} PIs need a paper-based description")

    def work(row):
        pi_id, name, oa_id, titles = row
        try:
            return pi_id, oa_id, *describe(name, titles)
        except Exception as e:
            print(f"  failed {name}: {str(e)[:120]}")
            return pi_id, oa_id, None, 0, 0

    written = tokens_in = tokens_out = 0
    now = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for pi_id, oa_id, text, t_in, t_out in pool.map(work, todo):
            tokens_in += t_in
            tokens_out += t_out
            if not text:
                continue
            # Writes stay on the main thread: DuckDB connections aren't shared across threads.
            con.execute(
                "UPDATE pis SET research_description = ?, source_url = coalesce(source_url, ?), scraped_at = ? WHERE id = ?",
                [PAPER_PREFIX + text, f"https://openalex.org/{oa_id}", now, str(pi_id)],
            )
            written += 1

    from gradradar.db.schema import create_fts_indexes
    create_fts_indexes(con)
    con.execute("CHECKPOINT")
    con.close()
    # Haiku 5.5 short-prompt rates: $0.10 / $0.50 per MTok
    print(f"wrote {written}; tokens in {tokens_in:,} out {tokens_out:,}; "
          f"cost ≈ ${tokens_in * 0.1e-6 + tokens_out * 0.5e-6:.2f}")


if __name__ == "__main__":
    main()
