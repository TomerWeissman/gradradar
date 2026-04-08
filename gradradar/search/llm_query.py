"""Natural language to structured query translation via LLM."""

from __future__ import annotations

import json
from typing import Literal

import instructor
import litellm
from pydantic import BaseModel, Field

# Suppress litellm's noisy stderr logging
litellm.suppress_debug_info = True

from gradradar.config import get_llm_model


class QueryPlan(BaseModel):
    """Structured search plan derived from a natural-language query."""

    search_terms: str = Field(
        description="Keywords for BM25 full-text search against PI names, "
        "research descriptions, and paper titles. Keep concise."
    )
    region: str | None = Field(
        default=None,
        description="Geographic filter: 'US', 'UK', or 'Europe'.",
    )
    is_taking_students: Literal["yes", "no", "unknown"] | None = Field(
        default=None,
        description="Filter by whether PI is accepting students.",
    )
    theory_category: Literal["theory", "applied", "mixed"] | None = Field(
        default=None,
        description="Filter by research style: theory, applied, or mixed.",
    )
    min_h_index: int | None = Field(
        default=None, description="Minimum h-index filter."
    )
    max_h_index: int | None = Field(
        default=None, description="Maximum h-index filter."
    )
    career_stage: Literal[
        "assistant_professor",
        "associate_professor",
        "full_professor",
        "postdoc",
        "industry_researcher",
        "research_scientist",
    ] | None = Field(
        default=None, description="Filter by career stage."
    )
    institution_name: str | None = Field(
        default=None,
        description="Fuzzy match on institution name (e.g. 'MIT', 'Stanford').",
    )
    order_by: str = Field(
        default="total_citations DESC",
        description="Sort order. One of: total_citations DESC, h_index DESC, "
        "citations_last_5_years DESC, citation_velocity DESC, paper_count DESC, name ASC.",
    )
    limit: int = Field(
        default=10, ge=1, le=100, description="Max results to return."
    )
    search_type: Literal["phd", "masters", "both"] = Field(
        default="phd",
        description="Whether the user wants PhD labs, Masters programs, or both.",
    )
    web_search_needed: bool = Field(
        default=False,
        description="True if the query asks about very specific/recent info "
        "that the database likely doesn't have.",
    )
    reasoning: str = Field(
        description="Brief explanation of how you interpreted the query."
    )


SYSTEM_PROMPT = """\
You are a search query planner for gradradar, a tool that helps students find \
PhD labs and Masters programs in ML, CS, and Math.

Given a natural language query (and optionally a user profile), produce a \
structured QueryPlan to search the database.

Guidelines:
- Extract the most relevant BM25 search terms from the query. Use technical \
  terms and topic keywords, not conversational language.
- Only set filters when the user explicitly or strongly implies them.
- If the user mentions "junior" or "new" professors, set career_stage to \
  "assistant_professor". "Senior" maps to "full_professor".
- If the user asks about someone "taking students" or "looking for students", \
  set is_taking_students to "yes".
- If no region is mentioned, leave it null (search all regions).
- Default sort is total_citations DESC unless the user implies a preference \
  (e.g. "rising stars" → citation_velocity DESC, "prolific" → paper_count DESC).
- Set web_search_needed=true only if the query names a specific PI not likely \
  in the database, or asks about very recent events.
- If a user profile is provided, use it to refine the search:
  - Incorporate their research_interests into the search_terms if the query \
    is vague (e.g. "find me labs" + interests "RL, robotics" → search_terms \
    "reinforcement learning robotics").
  - Apply their region preferences as the region filter if no region is \
    explicitly mentioned in the query.
  - Set search_type based on their degree_preference if not specified in the query.
"""


def translate_query(
    query: str,
    profile: dict | None = None,
    model: str | None = None,
) -> QueryPlan:
    """Translate a natural language query into a structured QueryPlan."""
    model = model or get_llm_model()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_content = f"Query: {query}"
    if profile:
        user_content += f"\n\nUser profile:\n{json.dumps(profile, indent=2)}"

    messages.append({"role": "user", "content": user_content})

    client = instructor.from_litellm(litellm.completion)
    plan = client.chat.completions.create(
        model=model,
        response_model=QueryPlan,
        messages=messages,
        temperature=0.0,
        max_tokens=1024,
    )
    return plan


def apply_cli_overrides(
    plan: QueryPlan,
    search_type: str | None = None,
    region: str | None = None,
    top: int | None = None,
) -> QueryPlan:
    """Apply explicit CLI flags on top of the LLM-generated plan."""
    if search_type:
        plan.search_type = search_type
    if region:
        plan.region = region
    if top:
        plan.limit = top
    return plan
