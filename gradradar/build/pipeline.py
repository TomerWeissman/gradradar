"""Orchestrates full and differential builds.

The build pipeline:
1. Load seed institutions into the database
2. For each institution, fetch CS/Math authors from OpenAlex
3. For each author batch, fetch their top papers
4. Build author-paper links and citation edges
5. Compute derived fields (citation_velocity, theory_category)
6. Build FTS indexes

Resume support: a checkpoint file tracks completed phases and batch progress.
Running with --resume skips already-completed work.
"""

import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from gradradar.build.sources.openalex import (
    extract_authorships,
    fetch_authors_for_institution,
    fetch_citations_for_works,
    fetch_works_batch,
    map_author_to_pi,
    map_work_to_paper,
)
from gradradar.config import get_gradradar_home
from gradradar.db.schema import create_fts_indexes, create_schema
from gradradar.db.writer import (
    insert_author_paper,
    insert_citation,
    log_scrape,
    upsert_institution,
    upsert_paper,
    upsert_pi,
)

console = Console()

# Theory venues for venue-derived theory_category
THEORY_VENUES = {"COLT", "ALT", "STOC", "FOCS", "SODA", "ITCS", "CCC", "SoCG"}
APPLIED_VENUES = {"NeurIPS", "ICML", "ICLR", "AAAI", "CVPR", "ICCV", "ECCV", "ACL", "EMNLP", "NAACL"}

CHECKPOINT_FILE = "build_checkpoint.json"


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


def run_build(
    db_path: Path,
    seeds_path: Path,
    sample: float = None,
    resume: bool = False,
):
    """Run the full OpenAlex ingestion pipeline.

    Args:
        db_path: Path to the DuckDB database file
        seeds_path: Path to the seeds/ directory
        sample: If set, only process this fraction of institutions (0.0-1.0)
        resume: If True, skip already-completed phases and batches
    """
    run_id = f"build_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Load checkpoint if resuming
    checkpoint = _load_checkpoint() if resume else {}
    if resume and checkpoint:
        console.print(f"\n[bold yellow]Resuming build from checkpoint[/bold yellow]")
        console.print(f"  Last completed phase: {checkpoint.get('last_completed_phase', 'none')}")
        run_id = checkpoint.get("run_id", run_id)
    else:
        console.print(f"\n[bold blue]Starting build run: {run_id}[/bold blue]\n")

    # Create or open database
    if not db_path.exists():
        console.print("[dim]Creating new database...[/dim]")
        con = create_schema(db_path)
    else:
        con = duckdb.connect(str(db_path))

    total_pis = 0
    total_papers = 0
    total_links = 0
    total_failed = 0
    last_phase = checkpoint.get("last_completed_phase", "")

    # --- Phase 1: Load institutions ---
    if last_phase < "phase_1":
        console.print("[bold]Phase 1: Loading institutions[/bold]")
        institutions_file = seeds_path / "institutions.json"
        with open(institutions_file) as f:
            seed_institutions = json.load(f)

        if sample:
            n = max(1, int(len(seed_institutions) * sample))
            seed_institutions = random.sample(seed_institutions, n)
            console.print(f"[dim]Sampling {n} institutions[/dim]")

        inst_id_map = {}
        for inst in seed_institutions:
            db_id = upsert_institution(con, {
                "name": inst["name"],
                "country": inst.get("country"),
                "region": inst.get("region"),
                "city": inst.get("city"),
                "type": inst.get("type"),
            })
            inst_id_map[inst["openalex_id"]] = db_id

        console.print(f"  Loaded {len(inst_id_map)} institutions\n")

        log_scrape(con, run_id, "build_phase_1", "build",
                   records_added=len(inst_id_map), notes="Loaded seed institutions")

        _save_checkpoint({
            "run_id": run_id,
            "last_completed_phase": "phase_1",
            "inst_id_map": inst_id_map,
            "seed_institutions": seed_institutions,
        })
    else:
        console.print("[dim]Phase 1: Skipped (already completed)[/dim]")
        inst_id_map = checkpoint.get("inst_id_map", {})
        seed_institutions = checkpoint.get("seed_institutions", [])

    # --- Phase 2: Fetch authors per institution ---
    if last_phase < "phase_2":
        console.print("[bold]Phase 2: Fetching authors from OpenAlex[/bold]")

        author_id_map = checkpoint.get("author_id_map", {})
        completed_institutions = set(checkpoint.get("completed_institutions", []))

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
            BarColumn(), MofNCompleteColumn(),
        ) as progress:
            task = progress.add_task("Institutions", total=len(seed_institutions))

            for inst in seed_institutions:
                oa_inst_id = inst["openalex_id"]
                db_inst_id = inst_id_map.get(oa_inst_id)

                if oa_inst_id in completed_institutions:
                    progress.update(task, advance=1, description=f"{inst['name']} (skipped)")
                    continue

                # Also skip if resume and institution already has PIs
                if resume and db_inst_id:
                    existing_count = con.execute(
                        "SELECT COUNT(*) FROM pis WHERE institution_id = ?", [db_inst_id]
                    ).fetchone()[0]
                    if existing_count > 0:
                        progress.update(task, advance=1, description=f"{inst['name']} (existing)")
                        completed_institutions.add(oa_inst_id)
                        continue

                progress.update(task, description=f"{inst['name']}")

                try:
                    authors = fetch_authors_for_institution(oa_inst_id)
                    for author in authors:
                        pi_data = map_author_to_pi(author, institution_id=db_inst_id)
                        db_pi_id = upsert_pi(con, pi_data)
                        oa_author_id = author["id"].replace("https://openalex.org/", "")
                        author_id_map[oa_author_id] = db_pi_id
                        total_pis += 1
                except Exception as e:
                    console.print(f"  [red]Error fetching authors for {inst['name']}: {e}[/red]")
                    total_failed += 1

                completed_institutions.add(oa_inst_id)
                progress.update(task, advance=1)

                # Checkpoint every 10 institutions
                if len(completed_institutions) % 10 == 0:
                    _save_checkpoint({
                        "run_id": run_id,
                        "last_completed_phase": "phase_1",
                        "inst_id_map": inst_id_map,
                        "seed_institutions": seed_institutions,
                        "author_id_map": author_id_map,
                        "completed_institutions": list(completed_institutions),
                    })

        console.print(f"  Fetched {total_pis} authors (total in map: {len(author_id_map)})\n")

        log_scrape(con, run_id, "build_phase_2", "build",
                   records_added=total_pis, records_failed=total_failed,
                   notes="Fetched authors from OpenAlex")

        _save_checkpoint({
            "run_id": run_id,
            "last_completed_phase": "phase_2",
            "inst_id_map": inst_id_map,
            "seed_institutions": seed_institutions,
            "author_id_map": author_id_map,
        })
    else:
        console.print("[dim]Phase 2: Skipped (already completed)[/dim]")
        author_id_map = checkpoint.get("author_id_map", {})

    # --- Phase 3: Fetch papers ---
    if last_phase < "phase_3":
        console.print("[bold]Phase 3: Fetching papers from OpenAlex[/bold]")

        all_author_oa_ids = list(author_id_map.keys())

        AUTHOR_BATCH = 50
        PAPERS_PER_BATCH = 500
        paper_id_map = checkpoint.get("paper_id_map", {})
        start_batch = checkpoint.get("phase3_batch", 0)

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
            BarColumn(), MofNCompleteColumn(),
        ) as progress:
            n_batches = (len(all_author_oa_ids) + AUTHOR_BATCH - 1) // AUTHOR_BATCH
            task = progress.add_task("Paper batches", total=n_batches, completed=start_batch)

            for i in range(start_batch * AUTHOR_BATCH, len(all_author_oa_ids), AUTHOR_BATCH):
                batch_ids = all_author_oa_ids[i:i + AUTHOR_BATCH]
                batch_num = i // AUTHOR_BATCH + 1
                progress.update(task, description=f"Batch {batch_num}/{n_batches}")

                try:
                    works = fetch_works_batch(batch_ids, max_results=PAPERS_PER_BATCH)
                    for work in works:
                        paper_data = map_work_to_paper(work)
                        if paper_data is None:
                            continue
                        db_paper_id = upsert_paper(con, paper_data)
                        oa_work_id = work["id"].replace("https://openalex.org/", "")
                        paper_id_map[oa_work_id] = db_paper_id
                        total_papers += 1

                        # Build author-paper links
                        for authorship in extract_authorships(work):
                            oa_aid = authorship["openalex_author_id"]
                            if oa_aid in author_id_map:
                                insert_author_paper(con, {
                                    "author_id": author_id_map[oa_aid],
                                    "paper_id": db_paper_id,
                                    "author_position": authorship["author_position"],
                                    "is_corresponding": authorship["is_corresponding"],
                                })
                                total_links += 1
                except Exception as e:
                    console.print(f"  [red]Error in batch {batch_num}: {e}[/red]")
                    total_failed += 1

                progress.update(task, advance=1)

                # Checkpoint every 50 batches
                if batch_num % 50 == 0:
                    con.execute("CHECKPOINT")
                    _save_checkpoint({
                        "run_id": run_id,
                        "last_completed_phase": "phase_2",
                        "inst_id_map": inst_id_map,
                        "seed_institutions": seed_institutions,
                        "author_id_map": author_id_map,
                        "paper_id_map": paper_id_map,
                        "phase3_batch": batch_num,
                    })

        console.print(f"  Fetched {total_papers} papers, {total_links} author-paper links\n")

        log_scrape(con, run_id, "build_phase_3", "build",
                   records_added=total_papers, records_failed=total_failed,
                   notes=f"Fetched papers, {total_links} author-paper links")

        _save_checkpoint({
            "run_id": run_id,
            "last_completed_phase": "phase_3",
            "inst_id_map": inst_id_map,
            "seed_institutions": seed_institutions,
            "author_id_map": author_id_map,
            "paper_id_map": paper_id_map,
        })
    else:
        console.print("[dim]Phase 3: Skipped (already completed)[/dim]")
        paper_id_map = checkpoint.get("paper_id_map", {})

    # --- Phase 4: Citation edges ---
    if last_phase < "phase_4":
        console.print("[bold]Phase 4: Building citation graph[/bold]")

        all_paper_oa_ids = list(paper_id_map.keys())
        citation_count = 0
        try:
            edges = fetch_citations_for_works(all_paper_oa_ids)
            for citing_oa_id, cited_oa_id in edges:
                if citing_oa_id in paper_id_map and cited_oa_id in paper_id_map:
                    insert_citation(con, paper_id_map[citing_oa_id], paper_id_map[cited_oa_id])
                    citation_count += 1
        except Exception as e:
            console.print(f"  [red]Error building citations: {e}[/red]")

        console.print(f"  Built {citation_count} citation edges\n")

        log_scrape(con, run_id, "build_phase_4", "build",
                   records_added=citation_count, notes="Citation graph")

        _save_checkpoint({
            "run_id": run_id,
            "last_completed_phase": "phase_4",
        })
    else:
        console.print("[dim]Phase 4: Skipped (already completed)[/dim]")

    # --- Phase 5: Compute derived fields ---
    if last_phase < "phase_5":
        console.print("[bold]Phase 5: Computing derived fields[/bold]")

        _compute_citation_velocity(con)
        _compute_theory_category(con)

        log_scrape(con, run_id, "build_phase_5", "build", notes="Computed derived fields")

        _save_checkpoint({
            "run_id": run_id,
            "last_completed_phase": "phase_5",
        })
    else:
        console.print("[dim]Phase 5: Skipped (already completed)[/dim]")

    # --- Phase 6: Build FTS indexes ---
    console.print("[bold]Phase 6: Building FTS indexes[/bold]")

    create_fts_indexes(con)
    console.print("  FTS indexes created\n")

    log_scrape(con, run_id, "build_phase_6", "build", notes="FTS indexes created")

    # Final log entry
    log_scrape(con, run_id, "build_complete", "build",
               records_added=total_pis + total_papers,
               notes=f"Build complete: {total_pis} PIs, {total_papers} papers")

    con.execute("CHECKPOINT")
    con.close()

    # Clear checkpoint on successful completion
    _clear_checkpoint()

    console.print(f"\n[bold green]Build complete![/bold green]")
    console.print(f"  PIs: {total_pis}")
    console.print(f"  Papers: {total_papers}")
    console.print(f"  Author-paper links: {total_links}")
    console.print(f"  Database: {db_path}")


def _compute_citation_velocity(con: duckdb.DuckDBPyConnection):
    """Compute citation_velocity and citation_velocity_source for all PIs."""
    pis = con.execute("""
        SELECT id, total_citations, citations_last_5_years, paper_count
        FROM pis
        WHERE total_citations > 0
    """).fetchall()

    updated = 0
    for pi_id, total_cit, cit_5yr, paper_count in pis:
        if total_cit == 0:
            continue

        velocity = cit_5yr / max(total_cit, 1)

        # Check if citations are concentrated in few papers
        top_paper = con.execute("""
            SELECT p.citation_count
            FROM author_paper ap
            JOIN papers p ON p.id = ap.paper_id
            WHERE ap.author_id = ?
            ORDER BY p.citation_count DESC
            LIMIT 1
        """, [str(pi_id)]).fetchone()

        if top_paper and cit_5yr > 0:
            top_cit = top_paper[0] or 0
            if top_cit > cit_5yr * 0.6:
                source = "depth"
            elif paper_count and paper_count > 10:
                source = "breadth"
            else:
                source = "mixed"
        else:
            source = "mixed"

        con.execute(
            "UPDATE pis SET citation_velocity = ?, citation_velocity_source = ? WHERE id = ?",
            [round(velocity, 4), source, str(pi_id)],
        )
        updated += 1

    console.print(f"  Updated citation velocity for {updated} PIs")


def _compute_theory_category(con: duckdb.DuckDBPyConnection):
    """Compute theory_category from venue distribution for PIs with >=5 papers."""
    pis = con.execute("SELECT id FROM pis WHERE paper_count >= 5").fetchall()

    updated = 0
    for (pi_id,) in pis:
        venues = con.execute("""
            SELECT p.venue
            FROM author_paper ap
            JOIN papers p ON p.id = ap.paper_id
            WHERE ap.author_id = ? AND p.venue IS NOT NULL
        """, [str(pi_id)]).fetchall()

        if len(venues) < 5:
            continue

        theory_count = 0
        applied_count = 0
        for (venue,) in venues:
            venue_upper = venue.upper() if venue else ""
            if any(tv in venue_upper for tv in THEORY_VENUES):
                theory_count += 1
            elif any(av in venue_upper for av in APPLIED_VENUES):
                applied_count += 1

        total = theory_count + applied_count
        if total == 0:
            continue

        theory_ratio = theory_count / total
        if theory_ratio > 0.6:
            category = "theory"
        elif theory_ratio < 0.2:
            category = "applied"
        else:
            category = "mixed"

        con.execute(
            "UPDATE pis SET theory_category = ?, theory_category_source = 'venue_derived' WHERE id = ?",
            [category, str(pi_id)],
        )
        updated += 1

    console.print(f"  Updated theory_category for {updated} PIs")
