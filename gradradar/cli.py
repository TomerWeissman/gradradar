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


def _write_env_key(path, key_name: str, value: str):
    """Write or update a KEY=VALUE line in a .env file with 0600 perms."""
    lines = path.read_text().splitlines() if path.exists() else []
    new_line = f"{key_name}={value}"
    for i, line in enumerate(lines):
        if line.startswith(f"{key_name}="):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


@main.command()
def setup():
    """Interactive first-run wizard: DB, profile, API key, demo search."""
    import os
    import subprocess
    import webbrowser

    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt

    from gradradar.config import get_gradradar_home, get_profile_path
    from gradradar.db.downloader import download
    from gradradar.profile import create_template, load_profile

    ensure_dirs()

    console.print(Panel.fit(
        "[bold]Welcome to gradradar[/bold]\n\n"
        "This wizard will walk you through:\n"
        "  1. Downloading the research database (~1.6 GB)\n"
        "  2. Creating your profile for personalized results\n"
        "  3. (Optional) Setting up an Anthropic API key for smart search\n"
        "  4. Running your first search",
        title="Setup",
        border_style="cyan",
    ))

    # --- Step 1: Database ---
    console.print("\n[bold cyan]Step 1/4 — Database[/bold cyan]")
    db_path = get_db_path()
    if db_path.exists():
        size_gb = db_path.stat().st_size / 1024 / 1024 / 1024
        console.print(f"[green]✓[/green] Database already installed ({size_gb:.1f} GB) at {db_path}")
    else:
        console.print("Downloading database from Cloudflare R2 (~1.6 GB, one-time)...")
        download()
        if not db_path.exists():
            console.print("[red]Database download failed. Retry with `gradradar init`.[/red]")
            return

    # --- Step 2: Profile ---
    console.print("\n[bold cyan]Step 2/4 — Profile[/bold cyan]")
    if load_profile():
        console.print(f"[green]✓[/green] Profile already exists at {get_profile_path()}")
    else:
        console.print(
            "A profile is a Markdown file describing your research interests, background,\n"
            "and what you're looking for. It powers personalized ranking and match narratives."
        )
        if Confirm.ask("Create a profile now?", default=True):
            path = create_template()
            editor = os.environ.get("EDITOR", "nano")
            console.print(f"[dim]Opening {path} in {editor}. Edit, save, and close to continue.[/dim]")
            subprocess.run([editor, str(path)])
            if load_profile():
                console.print("[green]✓[/green] Profile saved.")
            else:
                console.print("[yellow]Profile is still empty. Edit it later with `gradradar profile setup`.[/yellow]")
        else:
            console.print("[dim]Skipped. Create one later with `gradradar profile setup`.[/dim]")

    # --- Step 3: Anthropic API key ---
    console.print("\n[bold cyan]Step 3/4 — Anthropic API key[/bold cyan]")
    if os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[green]✓[/green] ANTHROPIC_API_KEY already set in your environment.")
    else:
        console.print(
            "An API key unlocks smart query translation, LLM re-ranking, and match narratives.\n"
            "  Cost: ~$0.015/search, ~$0.045/search with [cyan]--narrate[/cyan].\n"
            "  Without a key, plain keyword search ([cyan]--no-llm[/cyan]) still works free."
        )
        if Confirm.ask("Set up an API key now?", default=True):
            url = "https://console.anthropic.com/settings/keys"
            console.print(f"\nOpening [cyan]{url}[/cyan] in your browser.")
            console.print("[dim]Sign in, create a key (enable billing if needed), then paste it here.[/dim]")
            try:
                webbrowser.open(url)
            except Exception:
                pass

            key = Prompt.ask("\nPaste your API key", password=True).strip()
            if not key.startswith("sk-ant-"):
                console.print("[yellow]That doesn't look like an Anthropic key (should start with sk-ant-). Skipping.[/yellow]")
                console.print("[dim]Re-run `gradradar setup` to retry.[/dim]")
            else:
                env_path = get_gradradar_home() / ".env"
                _write_env_key(env_path, "ANTHROPIC_API_KEY", key)
                os.environ["ANTHROPIC_API_KEY"] = key
                console.print(f"[green]✓[/green] Key saved to {env_path} (permissions 600)")
        else:
            console.print("[dim]Skipped. You can run `gradradar setup` again, or export the key in your shell.[/dim]")

    # --- Step 4: Demo search ---
    console.print("\n[bold cyan]Step 4/4 — Try it out[/bold cyan]")
    query = Prompt.ask(
        "Type a search query to try (or press Enter to skip)",
        default="",
        show_default=False,
    ).strip()
    if query:
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        args = ["gradradar", "search", query, "--top", "5"]
        if not has_key:
            args.append("--no-llm")
        console.print(f"[dim]Running: {' '.join(args)}[/dim]\n")
        subprocess.run(args)

    console.print("\n[bold green]Setup complete.[/bold green]")
    console.print("Common next commands:")
    console.print("  [cyan]gradradar search \"your topic\" --top 5[/cyan]          smart search")
    console.print("  [cyan]gradradar search \"your topic\" --narrate[/cyan]         add match narratives")
    console.print("  [cyan]gradradar recommend[/cyan]                             profile-driven recs")
    console.print("  [cyan]gradradar profile show[/cyan]                          see your profile")


# --- Profile commands ---


@main.group()
def profile():
    """Manage your local interest profile."""
    pass


@profile.command("setup")
def profile_setup():
    """Create profile template and open it in your editor."""
    ensure_dirs()
    from gradradar.profile import create_template, load_profile
    import subprocess, os

    path = create_template()
    editor = os.environ.get("EDITOR", "nano")

    if load_profile():
        console.print(f"[dim]Profile already exists at {path}[/dim]")
    else:
        console.print(f"[green]Created profile template at {path}[/green]")

    console.print(f"[bold]Opening in {editor}...[/bold]")
    console.print("[dim]Edit the file to personalize your search results, then save and close.[/dim]")
    subprocess.run([editor, str(path)])

    if load_profile():
        console.print(f"\n[green]Profile saved at {path}[/green]")
    else:
        console.print(f"\n[yellow]Profile is empty. Edit {path} when ready.[/yellow]")


@profile.command("show")
def profile_show():
    """Display the current profile."""
    from gradradar.profile import load_profile
    from gradradar.config import get_profile_path

    p = load_profile()
    if not p:
        console.print("[yellow]No profile found. Run 'gradradar profile setup' first.[/yellow]")
        return
    console.print(f"[dim]{get_profile_path()}[/dim]\n")
    console.print(p)


@profile.command("path")
def profile_path():
    """Print the profile file path."""
    from gradradar.config import get_profile_path
    console.print(str(get_profile_path()))


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
@click.option("--narrate", is_flag=True, help="Generate detailed match narratives for top results")
def search(query, search_type, region, top, mode, no_profile, as_json, web, no_web, explain, explain_only, clarify, no_llm, no_rerank, narrate):
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

    # Execute search (read-write when narrating so we can cache narrations)
    use_narrate = narrate and not no_llm
    con = duckdb.connect(str(db_path), read_only=not use_narrate)
    try:
        with console.status("[bold green]Searching..."):
            results = run_search(
                con, plan, mode=mode, no_rerank=no_rerank or no_llm,
                profile=profile, use_narrate=use_narrate,
            )
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

    console.print(f"\n[bold]Recommendations based on your profile[/bold]")
    print_results({"pis": pis, "programs": []}, as_json=as_json)


@main.command()
@click.option("--limit", default=None, type=int, help="Max number of PIs to enrich.")
@click.option("--min-h-index", default=20, type=int, help="Only enrich PIs with h_index >= this.")
@click.option("--resume", is_flag=True, help="Resume from last checkpoint.")
@click.option("--skip-discovery", is_flag=True, help="Skip URL discovery, use existing source_url.")
@click.option("--skip-scrape", is_flag=True, help="Skip scraping, only discover URLs.")
@click.option("--dry-extract", is_flag=True, help="Fetch HTML only, skip LLM extraction.")
@click.option("--cs-only", is_flag=True, help="Only enrich PIs with papers in CS-adjacent venues.")
def enrich(limit, min_h_index, resume, skip_discovery, skip_scrape, dry_extract, cs_only):
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
        cs_only=cs_only,
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
