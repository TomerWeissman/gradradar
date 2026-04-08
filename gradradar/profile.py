"""User profile management — 5-field interest profile stored locally."""

import json
from pathlib import Path

from gradradar.config import get_profile_path


def load_profile() -> dict | None:
    """Load the user profile from disk. Returns None if no profile exists."""
    path = get_profile_path()
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_profile(profile: dict):
    """Save the user profile to disk."""
    path = get_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)


def interactive_setup() -> dict:
    """Run the 5-field interactive profile setup wizard. Returns the profile dict."""
    import click

    click.echo("\n  gradradar profile setup\n")
    click.echo("  Answer 5 quick questions to personalize your search results.\n")

    # 1. Degree preference
    degree = click.prompt(
        "  1. What are you looking for?",
        type=click.Choice(["phd", "masters", "both"], case_sensitive=False),
        default="phd",
    )

    # 2. Research interests
    interests = click.prompt(
        "  2. Primary research interests (freeform, e.g. 'reinforcement learning, robotics')",
        type=str,
    )

    # 3. Geography priority
    click.echo("  3. Geography priority (rank your preferences)")
    regions = []
    for region in ["US", "UK", "Europe"]:
        if click.confirm(f"     Include {region}?", default=True):
            regions.append(region)

    # 4. International student
    international = click.prompt(
        "  4. Are you an international student?",
        type=click.Choice(["yes", "no"], case_sensitive=False),
        default="no",
    )

    # 5. Funding requirement
    funding = click.prompt(
        "  5. Funding requirement",
        type=click.Choice(["required", "strongly_preferred", "nice_to_have"], case_sensitive=False),
        default="strongly_preferred",
    )

    profile = {
        "degree_preference": degree,
        "research_interests": interests,
        "regions": regions,
        "international_student": international == "yes",
        "funding_requirement": funding,
    }

    save_profile(profile)
    return profile
