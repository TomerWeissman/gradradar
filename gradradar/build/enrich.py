"""PI enrichment pipeline: discover URLs, scrape pages, extract data via LLM.

Adds to the existing build pipeline as new phases:
- Phase 7: URL discovery (DuckDuckGo search for faculty pages)
- Phase 8: Scrape & extract (fetch HTML, LLM extraction, update DB)

Uses parallel workers for both phases to speed up processing.
"""

from __future__ import annotations

import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue

import duckdb
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from gradradar.build.extractors.department_parser import infer_department
from gradradar.build.extractors.llm_extractor import extract_pi_from_text, PIExtraction
from gradradar.build.sources.scraper import fetch_html, extract_text, extract_title
from gradradar.build.sources.url_discovery import find_pi_url
from gradradar.config import get_gradradar_home
from gradradar.db.schema import create_fts_indexes
from gradradar.db.writer import _update_record

console = Console()

CHECKPOINT_FILE = "enrich_checkpoint.json"
DEFAULT_WORKERS = 4


def _checkpoint_path() -> Path:
    return get_gradradar_home() / "db" / CHECKPOINT_FILE


def _load_checkpoint() -> dict:
    path = _checkpoint_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _save_checkpoint(data: dict):
    path = _checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _clear_checkpoint():
    path = _checkpoint_path()
    if path.exists():
        path.unlink()


def run_enrich(
    db_path: Path,
    limit: int | None = None,
    min_h_index: int = 20,
    resume: bool = False,
    skip_discovery: bool = False,
    skip_scrape: bool = False,
    dry_extract: bool = False,
    cs_only: bool = False,
    workers: int = DEFAULT_WORKERS,
):
    """Run the PI enrichment pipeline.

    Args:
        db_path: Path to the DuckDB database
        limit: Max number of PIs to enrich (None = all)
        min_h_index: Only enrich PIs with h_index >= this
        resume: Resume from last checkpoint
        skip_discovery: Skip URL discovery (use existing source_url)
        skip_scrape: Skip scraping (use cached HTML)
        dry_extract: Fetch HTML only, skip LLM extraction
        cs_only: Only enrich PIs with papers in CS-adjacent venues
        workers: Number of parallel workers
    """
    con = duckdb.connect(str(db_path))

    checkpoint = _load_checkpoint() if resume else {}
    completed_ids = set(checkpoint.get("completed_ids", []))
    discovered_urls = checkpoint.get("discovered_urls", {})

    if resume and completed_ids:
        console.print(f"[yellow]Resuming enrichment: {len(completed_ids)} already done[/yellow]")

    # Get PIs that need enrichment
    pis = _get_pis_to_enrich(con, min_h_index=min_h_index, limit=limit, cs_only=cs_only)
    pis = [p for p in pis if p["id"] not in completed_ids]

    if not pis:
        console.print("[green]All PIs already enriched![/green]")
        con.close()
        return

    console.print(f"\n[bold]Enriching {len(pis)} PIs (h_index >= {min_h_index}, {workers} workers)[/bold]\n")

    # Phase 7: URL discovery (parallel)
    if not skip_discovery:
        console.print("[bold]Phase 7: Discovering PI URLs[/bold]")
        pis_needing_urls = [p for p in pis if p["id"] not in discovered_urls and not p.get("source_url")]
        discovered_urls = _discover_urls_parallel(pis_needing_urls, discovered_urls, workers=workers)

        _save_checkpoint({
            "completed_ids": list(completed_ids),
            "discovered_urls": discovered_urls,
        })
    else:
        console.print("[dim]Phase 7: Skipped (--skip-discovery)[/dim]")

    if skip_scrape:
        console.print("[dim]Phase 8: Skipped (--skip-scrape)[/dim]")
        con.close()
        return

    # Phase 8: Scrape & extract (parallel scrape+extract, sequential DB write)
    console.print(f"\n[bold]Phase 8: Scraping & extracting PI data[/bold]")

    enriched = 0
    failed = 0
    skipped = 0

    # Build work items: (pi, url) pairs
    work_items = []
    for pi in pis:
        url = discovered_urls.get(pi["id"]) or pi.get("source_url")
        if not url:
            skipped += 1
        else:
            work_items.append((pi, url))

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Enriching", total=len(work_items))

        # Process in batches to allow periodic checkpointing
        batch_size = workers * 5
        for batch_start in range(0, len(work_items), batch_size):
            batch = work_items[batch_start:batch_start + batch_size]

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        _scrape_and_extract, pi, url, dry_extract
                    ): (pi, url)
                    for pi, url in batch
                }

                for future in as_completed(futures):
                    pi, url = futures[future]
                    pi_id = pi["id"]
                    progress.update(task, description=f"{pi['name'][:30]}")

                    try:
                        result = future.result()
                        if result is None:
                            failed += 1
                        elif result == "dry":
                            enriched += 1
                        else:
                            # result is (extraction, url) — write to DB on main thread
                            extraction, source_url = result
                            _apply_extraction(con, pi_id, source_url, extraction)
                            enriched += 1
                    except Exception as e:
                        console.print(f"  [red]Error enriching {pi['name']}: {e}[/red]")
                        failed += 1

                    completed_ids.add(pi_id)
                    progress.update(task, advance=1)

            # Checkpoint after each batch
            _save_checkpoint({
                "completed_ids": list(completed_ids),
                "discovered_urls": discovered_urls,
            })

    # Rebuild FTS indexes to include new research_descriptions
    if enriched > 0:
        console.print("\n[bold]Rebuilding FTS indexes...[/bold]")
        create_fts_indexes(con)
        console.print("  FTS indexes updated.")

    con.execute("CHECKPOINT")
    con.close()
    _clear_checkpoint()

    console.print(f"\n[bold green]Enrichment complete![/bold green]")
    console.print(f"  Enriched: {enriched}")
    console.print(f"  Failed: {failed}")
    console.print(f"  Skipped (no URL): {skipped}")


def _scrape_and_extract(
    pi: dict,
    url: str,
    dry_extract: bool = False,
) -> tuple[PIExtraction, str] | str | None:
    """Scrape a PI's page and extract data. Runs in a worker thread.

    Returns:
        (extraction, url) on success
        "dry" if dry_extract mode
        None on failure
    """
    html = fetch_html(url)
    if not html:
        return None

    if dry_extract:
        return "dry"

    page_text = extract_text(html)
    if not page_text or len(page_text) < 50:
        return None

    page_title = extract_title(html)

    extraction = extract_pi_from_text(
        page_text=page_text,
        pi_name=pi["name"],
        institution_name=pi.get("institution_name", ""),
        page_url=url,
        page_title=page_title,
    )

    # Deterministic department inference takes priority over LLM
    parsed_dept = infer_department(url, page_title)
    if parsed_dept:
        extraction.department = parsed_dept

    return (extraction, url)


def _discover_urls_parallel(
    pis: list[dict],
    existing_urls: dict,
    workers: int = DEFAULT_WORKERS,
) -> dict:
    """Discover URLs for PIs via DuckDuckGo search using parallel workers."""
    if not pis:
        console.print("  No PIs need URL discovery.")
        return existing_urls

    found = 0
    # Use a lock to stagger DuckDuckGo requests across threads
    # Each worker waits 0.5s between requests (total ~workers*2 req/sec)
    rate_lock = threading.Lock()
    last_request_time = [0.0]  # mutable container for closure
    min_interval = 0.5  # seconds between any two DuckDuckGo requests

    def _discover_one(pi: dict) -> tuple[str, str | None]:
        """Discover URL for a single PI, respecting global rate limit."""
        with rate_lock:
            elapsed = time.time() - last_request_time[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            last_request_time[0] = time.time()

        url = find_pi_url(pi["name"], pi["institution_name"], delay=0)
        return pi["id"], url

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("URL discovery", total=len(pis))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_discover_one, pi): pi for pi in pis}

            for future in as_completed(futures):
                pi = futures[future]
                progress.update(task, description=f"{pi['name'][:30]}")

                try:
                    pi_id, url = future.result()
                    if url:
                        existing_urls[pi_id] = url
                        found += 1
                except Exception:
                    pass

                progress.update(task, advance=1)

    console.print(f"  Found URLs for {found}/{len(pis)} PIs\n")
    return existing_urls


def _get_pis_to_enrich(
    con: duckdb.DuckDBPyConnection,
    min_h_index: int = 20,
    limit: int | None = None,
    cs_only: bool = False,
) -> list[dict]:
    """Get PIs that need enrichment, prioritized by h_index.

    If cs_only=True, only return PIs who have published in CS-adjacent venues.
    """
    cs_filter = ""
    if cs_only:
        # Filter to PIs with at least one paper in a CS-adjacent venue
        cs_venues = [
            "NeurIPS", "ICML", "ICLR", "CVPR", "ICCV", "ECCV", "ACL", "EMNLP",
            "NAACL", "AAAI", "IJCAI", "KDD", "WWW", "SIGIR", "ICDE", "VLDB",
            "SIGMOD", "STOC", "FOCS", "SODA", "POPL", "PLDI", "OSDI", "SOSP",
            "NSDI", "CCS", "CHI", "UIST", "SIGGRAPH", "RSS", "ICRA", "IROS",
            "Lecture notes in computer science",
            "arXiv", "IEEE", "ACM",
            "Machine Learning", "Artificial Intelligence", "Neural",
            "Computer", "Robotics", "Information", "Data Mining",
        ]
        venue_conditions = " OR ".join([f"pa.venue ILIKE '%{v}%'" for v in cs_venues])
        cs_filter = f"""
          AND p.id IN (
              SELECT DISTINCT ap.author_id
              FROM author_paper ap
              JOIN papers pa ON pa.id = ap.paper_id
              WHERE {venue_conditions}
          )
        """

    limit_clause = f"LIMIT {limit}" if limit else ""
    results = con.execute(f"""
        SELECT p.id, p.name, p.openalex_id, p.source_url, p.h_index,
               i.name as institution_name
        FROM pis p
        LEFT JOIN institutions i ON i.id = p.institution_id
        WHERE p.research_description IS NULL
          AND p.h_index >= ?
          {cs_filter}
        ORDER BY p.h_index DESC
        {limit_clause}
    """, [min_h_index]).fetchall()

    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "openalex_id": r[2],
            "source_url": r[3],
            "h_index": r[4],
            "institution_name": r[5] or "",
        }
        for r in results
    ]


def _apply_extraction(
    con: duckdb.DuckDBPyConnection,
    pi_id: str,
    source_url: str,
    extraction: PIExtraction,
):
    """Apply LLM extraction results to the PI record in the database."""
    update_data = {"source_url": source_url, "scraped_at": datetime.now(timezone.utc).isoformat()}

    if extraction.research_description:
        update_data["research_description"] = extraction.research_description
    if extraction.short_bio:
        update_data["short_bio"] = extraction.short_bio
    if extraction.department:
        update_data["department_name"] = extraction.department
    if extraction.is_taking_students:
        update_data["is_taking_students"] = extraction.is_taking_students
    if extraction.taking_students_confidence is not None:
        update_data["taking_students_confidence"] = extraction.taking_students_confidence
    if extraction.email:
        update_data["email"] = extraction.email
    if extraction.personal_url:
        update_data["personal_url"] = extraction.personal_url
    if extraction.lab_url:
        update_data["lab_url"] = extraction.lab_url
    if extraction.lab_name:
        update_data["lab_name"] = extraction.lab_name
    if extraction.career_stage:
        update_data["career_stage"] = extraction.career_stage
    if extraction.current_student_count is not None:
        update_data["current_student_count"] = extraction.current_student_count
    if extraction.funding_sources:
        update_data["funding_sources"] = extraction.funding_sources
    if extraction.taking_students_confidence is not None:
        now = datetime.now(timezone.utc).isoformat()
        update_data["taking_students_checked_at"] = now

    _update_record(con, "pis", pi_id, update_data)
