"""CLI entry point for all gradradar commands."""

import click
from rich.console import Console
from rich.table import Table

from gradradar import __version__
from gradradar.config import ensure_dirs, get_db_path

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="gradradar")
def main():
    """gradradar — Discover PhD labs and Masters programs in ML/CS/Math."""
    pass


# --- Setup commands ---


@main.command()
@click.option("--force", is_flag=True, help="Overwrite existing database without prompting.")
@click.option("--version", "ver", default=None, help="Download a specific version.")
@click.option("--offline", is_flag=True, help="Skip remote manifest check.")
def init(force, ver, offline):
    """Download the database from Cloudflare R2 and initialize ~/.gradradar/."""
    ensure_dirs()
    console.print("[green]Created ~/.gradradar/ directory structure.[/green]")

    from gradradar.db.downloader import download
    download(version=ver, force=force, offline=offline)


# --- Profile commands ---


@main.group()
def profile():
    """Manage your local interest profile."""
    pass


@profile.command("setup")
def profile_setup():
    """Interactive 5-field profile setup wizard."""
    ensure_dirs()
    from gradradar.profile import interactive_setup
    p = interactive_setup()
    console.print(f"\n[green]Profile saved with interests: {p['research_interests']}[/green]")


@profile.command("show")
def profile_show():
    """Display the current profile."""
    import json
    from gradradar.profile import load_profile

    p = load_profile()
    if not p:
        console.print("[yellow]No profile found. Run 'gradradar profile setup' first.[/yellow]")
        return
    console.print_json(json.dumps(p, indent=2))


# --- Search commands ---


@main.command()
@click.argument("query")
@click.option("--type", "search_type", default=None, help="phd, masters, or both")
@click.option("--region", default=None, help="US, UK, or Europe")
@click.option("--top", default=10, help="Number of results to return")
@click.option("--mode", default="hybrid", help="sql, fts, or hybrid")
@click.option("--no-profile", is_flag=True, help="Ignore user profile")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--web", is_flag=True, help="Force web search on")
@click.option("--no-web", is_flag=True, help="Force web search off")
@click.option("--explain", is_flag=True, help="Print full QueryPlan JSON")
@click.option("--explain-only", is_flag=True, help="Print QueryPlan and exit")
@click.option("--clarify", is_flag=True, help="Ask clarifying questions before search")
@click.option("--no-llm", is_flag=True, help="Skip LLM query translation, use raw query as search terms")
@click.option("--no-rerank", is_flag=True, help="Skip LLM re-ranking of results")
def search(query, search_type, region, top, mode, no_profile, as_json, web, no_web, explain, explain_only, clarify, no_llm, no_rerank):
    """Search for PhD labs or Masters programs."""
    import duckdb
    from gradradar.profile import load_profile
    from gradradar.search.llm_query import translate_query, apply_cli_overrides, QueryPlan
    from gradradar.search.engine import run_search
    from gradradar.search.formatting import print_results, print_query_plan

    db_path = get_db_path()
    if not db_path.exists():
        console.print("[red]No database found. Run 'gradradar init' or 'gradradar build' first.[/red]")
        return

    # Load profile unless --no-profile
    profile = None if no_profile else load_profile()

    if no_llm:
        # Build a plan directly from the raw query and CLI flags
        plan = QueryPlan(
            search_terms=query,
            region=region,
            search_type=search_type or "phd",
            limit=top,
            reasoning="Direct search (--no-llm)",
        )
    else:
        # Translate query to structured plan via LLM
        try:
            with console.status("[bold green]Analyzing query..."):
                plan = translate_query(query, profile=profile)
                plan = apply_cli_overrides(plan, search_type=search_type, region=region, top=top)
        except Exception as e:
            err_msg = str(e)
            if "credit balance" in err_msg or "api_key" in err_msg.lower():
                console.print("[yellow]LLM unavailable (check API key/credits). Falling back to direct search.[/yellow]")
                plan = QueryPlan(
                    search_terms=query,
                    region=region,
                    search_type=search_type or "phd",
                    limit=top,
                    reasoning="Fallback — LLM unavailable",
                )
            else:
                console.print(f"[red]Query translation failed: {e}[/red]")
                return

    if explain or explain_only:
        print_query_plan(plan.model_dump())
        if explain_only:
            return

    # Execute search
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        with console.status("[bold green]Searching..."):
            results = run_search(con, plan, mode=mode, no_rerank=no_rerank or no_llm, profile=profile)
    finally:
        con.close()

    print_results(results, as_json=as_json)


# --- Database commands ---


@main.group()
def db():
    """Database management commands."""
    pass


@db.command("stats")
def db_stats():
    """Display database statistics."""
    import duckdb
    from gradradar.db.schema import ALL_TABLES, get_row_count

    db_path = get_db_path()
    if not db_path.exists():
        console.print("[red]No database found. Run 'gradradar init' or 'gradradar build' first.[/red]")
        return

    con = duckdb.connect(str(db_path), read_only=True)

    # Database size
    size_mb = db_path.stat().st_size / 1024 / 1024
    console.print(f"\n[bold]Database:[/bold] {db_path}")
    console.print(f"[bold]Size:[/bold] {size_mb:.2f} MB\n")

    # Table row counts
    table = Table(title="Table Row Counts")
    table.add_column("Table", style="cyan")
    table.add_column("Rows", justify="right", style="green")

    total_rows = 0
    for t in ALL_TABLES:
        try:
            count = get_row_count(con, t)
            total_rows += count
            table.add_row(t, str(count))
        except Exception:
            table.add_row(t, "[red]ERROR[/red]")

    console.print(table)
    console.print(f"\n[bold]Total rows:[/bold] {total_rows}")

    # Last build info from scrape_log
    try:
        last_build = con.execute(
            "SELECT command, phase, completed_at, records_added FROM scrape_log ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        if last_build:
            console.print(f"[bold]Last operation:[/bold] {last_build[0]} ({last_build[1]}) at {last_build[2]}")
    except Exception:
        pass

    # Enrichment stats
    try:
        total_pis = con.execute("SELECT COUNT(*) FROM pis").fetchone()[0]
        enriched = con.execute("SELECT COUNT(*) FROM pis WHERE research_description IS NOT NULL").fetchone()[0]
        with_email = con.execute("SELECT COUNT(*) FROM pis WHERE email IS NOT NULL").fetchone()[0]
        taking_yes = con.execute("SELECT COUNT(*) FROM pis WHERE is_taking_students = 'yes'").fetchone()[0]
        taking_no = con.execute("SELECT COUNT(*) FROM pis WHERE is_taking_students = 'no'").fetchone()[0]
        console.print(f"\n[bold]Enrichment:[/bold] {enriched}/{total_pis} PIs ({enriched*100//max(total_pis,1)}%)")
        console.print(f"  With email: {with_email}  |  Taking students: {taking_yes} yes, {taking_no} no")
    except Exception:
        pass

    # Possible duplicates pending review
    try:
        pending_dupes = con.execute(
            "SELECT COUNT(*) FROM possible_duplicates WHERE status = 'pending'"
        ).fetchone()[0]
        if pending_dupes > 0:
            console.print(f"\n[yellow]Pending duplicate reviews: {pending_dupes}[/yellow]")
    except Exception:
        pass

    con.close()


@db.command("validate")
def db_validate():
    """Run data integrity checks."""
    import duckdb
    from gradradar.db.schema import validate_schema

    db_path = get_db_path()
    if not db_path.exists():
        console.print("[red]No database found. Run 'gradradar init' or 'gradradar build' first.[/red]")
        return

    con = duckdb.connect(str(db_path), read_only=True)
    errors = validate_schema(con)
    con.close()

    if errors:
        console.print(f"\n[red]Found {len(errors)} issue(s):[/red]")
        for err in errors:
            console.print(f"  [red]✗[/red] {err}")
    else:
        console.print("\n[green]All validation checks passed.[/green]")


@db.command("create")
def db_create():
    """Create an empty database with the full schema."""
    from gradradar.db.schema import create_schema, create_fts_indexes

    ensure_dirs()
    db_path = get_db_path()

    if db_path.exists():
        console.print(f"[yellow]Database already exists at {db_path}[/yellow]")
        return

    con = create_schema(db_path)
    create_fts_indexes(con)
    con.close()

    size_kb = db_path.stat().st_size / 1024
    console.print(f"[green]Created database at {db_path} ({size_kb:.1f} KB)[/green]")


@db.command("publish")
@click.option("--version", "ver", default=None, help="Override version string.")
@click.option("--message", default=None, help="Changelog note.")
def db_publish(ver, message):
    """Push local database to Cloudflare R2."""
    from gradradar.db.downloader import publish
    publish(version_override=ver, message=message)


# --- Build commands ---


@main.command()
@click.option("--full", is_flag=True, help="Run all phases.")
@click.option("--phase", type=int, default=None, help="Run a specific phase (1-7).")
@click.option("--resume", is_flag=True, help="Resume from last checkpoint.")
@click.option("--sample", type=float, default=None, help="Process only a fraction of data.")
@click.option("--dry-extract", is_flag=True, help="Fetch HTML only, skip LLM extraction.")
def build(full, phase, resume, sample, dry_extract):
    """Run the build pipeline."""
    from pathlib import Path
    from gradradar.build.pipeline import run_build

    ensure_dirs()
    db_path = get_db_path()
    seeds_path = Path(__file__).parent.parent / "seeds"

    run_build(db_path=db_path, seeds_path=seeds_path, sample=sample, resume=resume)


@main.command()
@click.option("--top", default=10, help="Number of recommendations")
@click.option("--no-rerank", is_flag=True, help="Skip LLM re-ranking")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def recommend(top, no_rerank, as_json):
    """Get personalized PI recommendations based on your profile."""
    import duckdb
    from gradradar.profile import load_profile
    from gradradar.search.recommend import recommend_pis
    from gradradar.search.formatting import print_results

    profile = load_profile()
    if not profile:
        console.print("[yellow]No profile found. Run 'gradradar profile setup' first.[/yellow]")
        return

    db_path = get_db_path()
    if not db_path.exists():
        console.print("[red]No database found. Run 'gradradar init' or 'gradradar build' first.[/red]")
        return

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        with console.status("[bold green]Generating recommendations..."):
            pis = recommend_pis(con, profile, top=top, use_rerank=not no_rerank)
    finally:
        con.close()

    console.print(f"\n[bold]Recommendations based on: {profile.get('research_interests', '')}[/bold]")
    print_results({"pis": pis, "programs": []}, as_json=as_json)


@main.command()
@click.option("--limit", default=None, type=int, help="Max number of PIs to enrich.")
@click.option("--min-h-index", default=20, type=int, help="Only enrich PIs with h_index >= this.")
@click.option("--resume", is_flag=True, help="Resume from last checkpoint.")
@click.option("--skip-discovery", is_flag=True, help="Skip URL discovery, use existing source_url.")
@click.option("--skip-scrape", is_flag=True, help="Skip scraping, only discover URLs.")
@click.option("--dry-extract", is_flag=True, help="Fetch HTML only, skip LLM extraction.")
def enrich(limit, min_h_index, resume, skip_discovery, skip_scrape, dry_extract):
    """Enrich PI records by scraping faculty pages and extracting data via LLM."""
    from gradradar.build.enrich import run_enrich

    ensure_dirs()
    db_path = get_db_path()
    if not db_path.exists():
        console.print("[red]No database found. Run 'gradradar init' or 'gradradar build' first.[/red]")
        return

    run_enrich(
        db_path=db_path,
        limit=limit,
        min_h_index=min_h_index,
        resume=resume,
        skip_discovery=skip_discovery,
        skip_scrape=skip_scrape,
        dry_extract=dry_extract,
    )


# --- Other commands ---


@main.command()
@click.option("--min", "min_count", type=int, default=None, help="Show topics with fewer than N PIs.")
def coverage(min_count):
    """Display topic distribution and coverage gaps."""
    # TODO: implement in Step 3
    console.print("[dim]Coverage not yet implemented.[/dim]")


@main.group()
def cache():
    """Manage local caches."""
    pass


@cache.command("clear")
@click.option("--html", "clear_html", is_flag=True, help="Clear only HTML cache.")
@click.option("--llm", "clear_llm", is_flag=True, help="Clear only LLM response cache.")
def cache_clear(clear_html, clear_llm):
    """Clear local caches."""
    import shutil
    from gradradar.config import get_cache_path

    cache = get_cache_path()
    clear_all = not clear_html and not clear_llm

    if clear_all or clear_html:
        html_dir = cache / "raw_html"
        if html_dir.exists():
            count = len(list(html_dir.iterdir()))
            shutil.rmtree(html_dir)
            html_dir.mkdir()
            console.print(f"[green]Cleared {count} HTML cache files.[/green]")
        else:
            console.print("[dim]No HTML cache to clear.[/dim]")

    if clear_all or clear_llm:
        llm_dir = cache / "llm_responses"
        if llm_dir.exists():
            count = len(list(llm_dir.iterdir()))
            shutil.rmtree(llm_dir)
            llm_dir.mkdir()
            console.print(f"[green]Cleared {count} LLM cache files.[/green]")
        else:
            console.print("[dim]No LLM cache to clear.[/dim]")


if __name__ == "__main__":
    main()
