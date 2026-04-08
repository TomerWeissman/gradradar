"""OpenAlex API client for fetching authors, works, and citations.

Uses the OpenAlex REST API with polite pool access (email in User-Agent).
Rate limit: 10 req/s for polite pool, 100K req/day.
"""

import time
from datetime import datetime

import httpx
from rich.console import Console

console = Console()

BASE_URL = "https://api.openalex.org"
HEADERS = {"User-Agent": "mailto:gradradar@example.com"}
REQUEST_DELAY = 0.12  # ~8 req/s to stay well within limits


def _get(url: str, params: dict = None) -> dict:
    """Make a rate-limited GET request to OpenAlex."""
    time.sleep(REQUEST_DELAY)
    resp = httpx.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _paginate(url: str, params: dict, max_results: int = None) -> list[dict]:
    """Paginate through OpenAlex API results using cursor."""
    params = {**params, "per_page": 200}
    results = []
    cursor = "*"

    while cursor:
        params["cursor"] = cursor
        data = _get(url, params)
        batch = data.get("results", [])
        if not batch:
            break
        results.extend(batch)

        if max_results and len(results) >= max_results:
            results = results[:max_results]
            break

        cursor = data.get("meta", {}).get("next_cursor")

    return results


def _load_topic_ids() -> list[str]:
    """Load CS/Math topic IDs from seeds file."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent.parent.parent / "seeds" / "cs_math_topic_ids.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def fetch_authors_for_institution(openalex_institution_id: str, min_works: int = 5) -> list[dict]:
    """Fetch authors at an institution with works in CS/Math/Stats.

    Makes multiple API calls with batched topic IDs (max 90 per request)
    to cover all relevant CS/Math subfields. Deduplicates results.
    Returns raw OpenAlex author records.
    """
    topic_ids = _load_topic_ids()
    if not topic_ids:
        # Fallback: no topic filter, just institution + min works + h_index
        params = {
            "filter": (
                f"last_known_institutions.id:{openalex_institution_id},"
                f"summary_stats.h_index:>10,"
                f"works_count:>{min_works}"
            ),
            "sort": "cited_by_count:desc",
            "select": (
                "id,display_name,last_known_institutions,summary_stats,"
                "works_count,cited_by_count,counts_by_year,ids"
            ),
        }
        return _paginate(f"{BASE_URL}/authors", params)

    # Split topic IDs into batches of 90
    seen_ids = set()
    all_authors = []
    batch_size = 90

    for i in range(0, len(topic_ids), batch_size):
        batch = topic_ids[i:i + batch_size]
        topic_filter = "|".join(batch)
        params = {
            "filter": (
                f"last_known_institutions.id:{openalex_institution_id},"
                f"summary_stats.h_index:>5,"
                f"works_count:>{min_works},"
                f"topics.id:{topic_filter}"
            ),
            "sort": "cited_by_count:desc",
            "select": (
                "id,display_name,last_known_institutions,summary_stats,"
                "works_count,cited_by_count,counts_by_year,ids"
            ),
        }
        authors = _paginate(f"{BASE_URL}/authors", params)
        for a in authors:
            aid = a["id"]
            if aid not in seen_ids:
                seen_ids.add(aid)
                all_authors.append(a)

    return all_authors


def fetch_works_for_author(openalex_author_id: str, max_works: int = 100) -> list[dict]:
    """Fetch papers for a specific author, sorted by citation count."""
    params = {
        "filter": f"authorships.author.id:{openalex_author_id}",
        "sort": "cited_by_count:desc",
        "select": (
            "id,title,publication_year,primary_location,cited_by_count,"
            "counts_by_year,doi,ids,authorships,concepts,abstract_inverted_index"
        ),
    }
    return _paginate(f"{BASE_URL}/works", params, max_results=max_works)


def fetch_works_batch(openalex_author_ids: list[str], max_results: int = 500) -> list[dict]:
    """Fetch top papers for a batch of authors.

    Uses a single paginated call with all author IDs OR'd together.
    max_results caps total papers returned for the batch.
    """
    if not openalex_author_ids:
        return []
    author_filter = "|".join(openalex_author_ids)
    params = {
        "filter": f"authorships.author.id:{author_filter}",
        "sort": "cited_by_count:desc",
        "select": (
            "id,title,publication_year,primary_location,cited_by_count,"
            "counts_by_year,doi,ids,authorships,abstract_inverted_index"
        ),
    }
    return _paginate(f"{BASE_URL}/works", params, max_results=max_results)


def fetch_citations_for_works(openalex_work_ids: list[str]) -> list[tuple[str, str]]:
    """Fetch citation edges where both papers are in the input set.

    Returns list of (citing_work_id, cited_work_id) tuples.
    """
    work_id_set = set(openalex_work_ids)
    edges = []

    for i in range(0, len(openalex_work_ids), 50):
        batch = openalex_work_ids[i:i + 50]
        id_filter = "|".join(batch)
        params = {
            "filter": f"ids.openalex:{id_filter}",
            "select": "id,referenced_works",
            "per_page": 200,
        }
        data = _get(f"{BASE_URL}/works", params)
        for work in data.get("results", []):
            citing_id = work["id"].replace("https://openalex.org/", "")
            for ref in work.get("referenced_works", []):
                cited_id = ref.replace("https://openalex.org/", "")
                if cited_id in work_id_set:
                    edges.append((citing_id, cited_id))

    return edges


# --- Mapping helpers ---


def map_author_to_pi(author: dict, institution_id: str = None) -> dict:
    """Map an OpenAlex author record to gradradar PI fields."""
    openalex_id = author["id"].replace("https://openalex.org/", "")

    stats = author.get("summary_stats", {})
    h_index = stats.get("h_index")
    total_citations = author.get("cited_by_count", 0)

    current_year = datetime.now().year
    counts_by_year = author.get("counts_by_year", [])

    citations_5yr = sum(
        y.get("cited_by_count", 0) for y in counts_by_year
        if y.get("year", 0) >= current_year - 5
    )
    papers_3yr = sum(
        y.get("works_count", 0) for y in counts_by_year
        if y.get("year", 0) >= current_year - 3
    )

    return {
        "name": author["display_name"],
        "openalex_id": openalex_id,
        "institution_id": institution_id,
        "h_index": h_index,
        "total_citations": total_citations,
        "citations_last_5_years": citations_5yr,
        "paper_count": author.get("works_count", 0),
        "paper_count_last_3_years": papers_3yr,
        "is_taking_students": "unknown",
        "theory_category": "unknown",
    }


def map_work_to_paper(work: dict) -> dict:
    """Map an OpenAlex work record to gradradar paper fields."""
    openalex_id = work["id"].replace("https://openalex.org/", "")

    # Venue from primary_location
    venue = None
    primary_loc = work.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    if source.get("display_name"):
        venue_name = source["display_name"]
        year = work.get("publication_year")
        venue = f"{venue_name} {year}" if year else venue_name

    # Citation velocity
    citation_count = work.get("cited_by_count", 0)
    counts_by_year = work.get("counts_by_year", [])
    current_year = datetime.now().year
    citations_2yr = sum(
        y.get("cited_by_count", 0) for y in counts_by_year
        if y.get("year", 0) >= current_year - 2
    )
    year_age = max(current_year - (work.get("publication_year") or current_year), 1)
    citation_velocity = citations_2yr / year_age if year_age > 0 else 0

    # DOI
    doi = work.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    # Abstract from inverted index
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

    title = work.get("title")
    if not title:
        return None  # Skip papers with no title

    return {
        "title": title,
        "abstract": abstract,
        "year": work.get("publication_year"),
        "venue": venue,
        "citation_count": citation_count,
        "citation_count_last_2_years": citations_2yr,
        "citation_velocity": round(citation_velocity, 4),
        "doi": doi,
        "openalex_id": openalex_id,
        "url": work.get("doi") or primary_loc.get("landing_page_url"),
    }


def extract_authorships(work: dict) -> list[dict]:
    """Extract author-paper relationships from a work record."""
    authorships = []
    total_authors = len(work.get("authorships", []))
    for i, authorship in enumerate(work.get("authorships", [])):
        author_id = authorship.get("author", {}).get("id", "")
        if not author_id:
            continue
        author_id = author_id.replace("https://openalex.org/", "")

        if i == 0:
            position = "first"
        elif i == total_authors - 1:
            position = "last"
        else:
            position = "middle"

        authorships.append({
            "openalex_author_id": author_id,
            "author_position": position,
            "is_corresponding": authorship.get("is_corresponding"),
        })

    return authorships


def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Reconstruct abstract text from OpenAlex inverted index format."""
    if not inverted_index:
        return None
    words = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    if not words:
        return None
    max_pos = max(words.keys())
    return " ".join(words.get(i, "") for i in range(max_pos + 1)).strip()
