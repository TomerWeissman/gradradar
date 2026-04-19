"""User profile management — markdown-based research profile.

The profile is a single .md file at ~/.gradradar/profile.md that the user
edits freely. `gradradar profile setup` generates a template with guiding
sections. The raw markdown is passed directly to the LLM for re-ranking
and narration — no structured parsing needed.
"""

import hashlib
from pathlib import Path

from gradradar.config import get_profile_path


PROFILE_TEMPLATE = """\
# My Research Profile

Edit this file to personalize your gradradar search results. The more detail
you provide, the better the AI can match you with researchers. Write freely —
there's no required format.

## Research Interests

What topics, methods, or problems excite you? Be specific.

Example: "I'm interested in reinforcement learning for robotics, specifically
sample-efficient methods and sim-to-real transfer. I care about methods that
work on real hardware, not just in simulation."



## Academic Background

Your degree(s), major, relevant coursework, thesis topic, etc.

Example: "BS in Math from UC Berkeley. Took graduate courses in optimization,
probability theory, and machine learning. Senior thesis on variational inference
for Bayesian neural networks."



## Research Experience

Labs, papers, projects, internships — anything hands-on.

Example: "Spent two summers in Prof. X's lab at MIT working on model-based RL.
Co-authored a workshop paper at NeurIPS 2024 on world models for manipulation.
Built a sim-to-real pipeline using Isaac Gym."



## What I'm Looking For

Degree type, geography, lab size, advisor style, funding needs, etc.

Example: "Looking for a PhD in the US or UK. I want a hands-on advisor with a
small-to-medium lab (3-8 students). Funding is required. I prefer applied work
with some theoretical grounding."



## Career Goals

Where do you see yourself after the degree?

Example: "I want to end up at an industry research lab (DeepMind, FAIR, etc.)
working on embodied AI. Open to a postdoc if it's at a top lab."



## Additional Context

Paste anything else that helps — your research statement, statement of purpose,
CV highlights, publications list, or notes about what matters to you.


"""


def load_profile() -> str | None:
    """Load the profile markdown from disk. Returns None if no profile exists."""
    path = get_profile_path()
    if not path.exists():
        return None
    text = path.read_text().strip()
    if not text:
        return None
    return text


def save_profile(content: str):
    """Save profile markdown to disk."""
    path = get_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def profile_hash(profile: str | None) -> str:
    """Stable hash of profile content for narration cache invalidation."""
    if not profile:
        return "no_profile"
    return hashlib.sha256(profile.encode()).hexdigest()[:16]


def format_profile_for_llm(profile: str | None) -> str:
    """Format the profile for inclusion in LLM prompts.

    Since the profile is already markdown, this just returns it directly
    with a fallback for missing profiles.
    """
    if not profile:
        return "No profile set."
    return profile


def create_template() -> Path:
    """Create the profile template file. Returns the path."""
    path = get_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(PROFILE_TEMPLATE)
    return path
