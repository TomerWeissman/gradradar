"""Rich output formatting for search results."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


console = Console()


def print_results(results: dict, as_json: bool = False):
    """Print search results in rich format or raw JSON."""
    if as_json:
        console.print_json(json.dumps(results, default=str))
        return

    pis = results.get("pis", [])
    programs = results.get("programs", [])

    if not pis and not programs:
        console.print("\n[yellow]No results found.[/yellow]\n")
        return

    if pis:
        console.print(f"\n[bold]Found {len(pis)} PI(s):[/bold]\n")
        for i, pi in enumerate(pis, 1):
            _print_pi_card(i, pi)

    if programs:
        console.print(f"\n[bold]Found {len(programs)} program(s):[/bold]\n")
        for i, prog in enumerate(programs, 1):
            _print_program_card(i, prog)


def print_query_plan(plan: dict):
    """Print the QueryPlan as a formatted panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    for key, value in plan.items():
        if value is not None:
            table.add_row(key, str(value))

    console.print(Panel(table, title="Query Plan", border_style="blue"))


def _print_pi_card(rank: int, pi: dict):
    """Print a single PI result card."""
    name = pi.get("name", "Unknown")
    institution = pi.get("institution_name", "Unknown institution")
    region = pi.get("region", "")
    country = pi.get("country", "")
    location = f"{country}" if country else region

    # Header line
    header = Text()
    header.append(f"{rank}. ", style="bold yellow")
    header.append(f"{name}", style="bold white")
    header.append(f"  {institution}", style="dim")
    if location:
        header.append(f" ({location})", style="dim")

    # Metadata line
    meta_parts = []
    if pi.get("career_stage"):
        meta_parts.append(pi["career_stage"].replace("_", " ").title())
    if pi.get("h_index"):
        meta_parts.append(f"h-index: {pi['h_index']}")
    if pi.get("total_citations"):
        meta_parts.append(f"citations: {pi['total_citations']:,}")
    if pi.get("paper_count"):
        meta_parts.append(f"papers: {pi['paper_count']}")

    taking = pi.get("is_taking_students", "unknown")
    if taking == "yes":
        meta_parts.append("[green]taking students[/green]")
    elif taking == "no":
        meta_parts.append("[red]not taking students[/red]")

    theory = pi.get("theory_category")
    if theory and theory != "unknown":
        meta_parts.append(f"[cyan]{theory}[/cyan]")

    meta = "  |  ".join(meta_parts)

    # Research description
    desc = pi.get("research_description", "")
    if desc and len(desc) > 200:
        desc = desc[:200] + "..."

    # Top papers
    papers = pi.get("top_papers", [])

    content = Text()
    content.append(meta + "\n", style="")

    # Relevance score from LLM re-ranker
    relevance = pi.get("relevance_score")
    reason = pi.get("relevance_reason")
    if relevance is not None:
        content.append(f"\nRelevance: {relevance:.0%}", style="bold magenta")
        if reason:
            content.append(f" — {reason}", style="magenta")
        content.append("\n")

    if desc:
        content.append(f"\n{desc}\n", style="dim")

    if papers:
        content.append("\nTop papers:\n", style="bold")
        for p in papers[:3]:
            year = p.get("year", "")
            cites = p.get("citation_count", 0)
            title = p.get("title", "Untitled")
            if len(title) > 80:
                title = title[:80] + "..."
            content.append(f"  - {title} ({year}, {cites} cites)\n", style="")

    # Links
    links = []
    if pi.get("personal_url"):
        links.append(pi["personal_url"])
    if pi.get("lab_url"):
        links.append(pi["lab_url"])
    if pi.get("email"):
        links.append(pi["email"])
    if links:
        content.append("\n" + "  ".join(links) + "\n", style="dim blue")

    console.print(Panel(content, title=str(header), border_style="green", padding=(0, 1)))


def _print_program_card(rank: int, prog: dict):
    """Print a single program result card."""
    name = prog.get("name", "Unknown Program")

    header = Text()
    header.append(f"{rank}. ", style="bold yellow")
    header.append(f"{name}", style="bold white")

    score = prog.get("bm25_score")
    content = ""
    if score is not None:
        content += f"Relevance score: {score:.2f}\n"

    console.print(Panel(content or "No details available.", title=str(header), border_style="cyan", padding=(0, 1)))
