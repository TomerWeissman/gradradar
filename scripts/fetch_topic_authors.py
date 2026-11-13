"""Fast incremental fetch of authors + papers for one topic set, optionally one country.

A lighter alternative to `gradradar build --topics`: skips the citation graph and the
full-DB derived-field recompute, so adding a field to an existing DB takes minutes.
Writes the fetched OpenAlex author IDs to <db dir>/authors_<topics stem>[_<country>].json
for `gradradar enrich --openalex-ids` and scripts/push_pis.py.

Usage:
    GRADRADAR_HOME=~/.gradradar/finance_build \\
        python scripts/fetch_topic_authors.py --topics optimization_topic_ids.json --country US
"""

import argparse
import json
from pathlib import Path

import duckdb

from gradradar.build.sources.openalex import (
    extract_authorships, fetch_authors_for_institution, fetch_works_batch,
    map_author_to_pi, map_work_to_paper,
)
from gradradar.config import get_db_path, get_gradradar_home
from gradradar.db.writer import insert_author_paper, upsert_institution, upsert_paper, upsert_pi

SEEDS = Path(__file__).parent.parent / "seeds"


def fetch_authors(con, institutions: list[dict], topics_file: str) -> dict[str, str]:
    """Upsert authors for each institution; return {openalex_author_id: pi_id}."""
    author_map = {}
    for inst in institutions:
        inst_id = upsert_institution(con, {k: inst.get(k) for k in ("name", "country", "region", "city", "type")})
        try:
            authors = fetch_authors_for_institution(inst["openalex_id"], topics_file=topics_file)
        except Exception as e:  # one institution failing shouldn't stop the run
            print(f"  {inst['name']}: ERROR {e}", flush=True)
            continue
        for a in authors:
            author_map[a["id"].replace("https://openalex.org/", "")] = upsert_pi(con, map_author_to_pi(a, institution_id=inst_id))
        print(f"  {inst['name']}: {len(authors)} authors", flush=True)
    return author_map


def fetch_papers(con, author_map: dict[str, str]) -> int:
    """Fetch top papers per 50-author batch and link them to the authors."""
    ids, papers = list(author_map), 0
    for i in range(0, len(ids), 50):
        try:
            works = fetch_works_batch(ids[i:i + 50], max_results=500)
        except Exception as e:
            print(f"  paper batch {i // 50}: ERROR {e}", flush=True)
            continue
        for work in works:
            paper = map_work_to_paper(work)
            if paper is None:
                continue
            paper_id = upsert_paper(con, paper)
            papers += 1
            for au in extract_authorships(work):
                if au["openalex_author_id"] in author_map:
                    insert_author_paper(con, {
                        "author_id": author_map[au["openalex_author_id"]], "paper_id": paper_id,
                        "author_position": au["author_position"], "is_corresponding": au["is_corresponding"],
                    })
    return papers


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topics", required=True, help="Seeds file of OpenAlex topic IDs")
    parser.add_argument("--country", default=None, help="Only institutions with this country code (e.g. US)")
    args = parser.parse_args()

    institutions = json.load(open(SEEDS / "institutions.json"))
    if args.country:
        institutions = [i for i in institutions if i.get("country") == args.country]
    print(f"{len(institutions)} institutions", flush=True)

    con = duckdb.connect(str(get_db_path()))
    author_map = fetch_authors(con, institutions, args.topics)
    print(f"authors: {len(author_map)}", flush=True)
    print(f"papers: {fetch_papers(con, author_map)}", flush=True)
    con.execute("CHECKPOINT")
    con.close()

    suffix = f"_{args.country}" if args.country else ""
    out = get_gradradar_home() / "db" / f"authors_{Path(args.topics).stem}{suffix}.json"
    json.dump(sorted(author_map), open(out, "w"))
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
