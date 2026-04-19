"""Generate detailed narrative explanations for top-k search results.

Takes the final ranked PIs and produces a personalized, evidence-based
narrative explaining why each PI is a good match for the user's query
and profile. All PIs are batched into a single LLM call to minimize cost.

Narrations are cached in the database keyed by (pi_id, query, profile_hash)
so repeated searches don't re-generate them.
"""

from __future__ import annotations

import json

import duckdb
import instructor
import litellm
from pydantic import BaseModel, Field

from gradradar.config import get_llm_model
from gradradar.profile import format_profile_for_llm, profile_hash

litellm.suppress_debug_info = True


class PINarrative(BaseModel):
    """Narrative for a single PI."""
    pi_id: str = Field(description="The PI's ID from the input")
    narrative: str = Field(
        description="A 3-5 sentence narrative explaining why this PI is a good match. "
        "Be specific: reference actual paper titles, research topics, and concrete "
        "connections to the user's interests. Evidence-based, not generic."
    )
    match_strength: str = Field(
        description="One of: strong, moderate, weak"
    )
    key_papers: list[str] = Field(
        default_factory=list,
        description="1-3 paper titles that are most relevant to the user's query"
    )


class NarrationResult(BaseModel):
    """Batch narration result for all PIs."""
    narratives: list[PINarrative]


NARRATION_PROMPT = """\
You are writing personalized research match narratives for a student exploring \
potential PhD advisors or research collaborators.

## User Query
{query}

## User Profile
{profile_text}

## Researchers to Narrate
{pi_summaries}

## Instructions
For each researcher, write a 3-5 sentence narrative that:
1. Identifies their most relevant work to the user's query — cite specific paper \
   titles and research directions, not vague summaries
2. Explains WHY this is a good match for the user's specific interests and background
3. Notes practical info: whether they're taking students, lab size, career stage
4. Highlights their most impactful or most recent relevant work
5. Is honest about match strength — if the connection is tangential, say so

Be specific and evidence-based. Don't use generic phrases like "well-positioned" or \
"strong track record." Instead, point to concrete papers, methods, or research directions \
that connect to the user's interests.

Also identify 1-3 of their papers most relevant to the query.
"""


def _load_cached_narrations(
    con: duckdb.DuckDBPyConnection,
    pi_ids: list[str],
    query: str,
    p_hash: str,
) -> dict[str, dict]:
    """Load any existing narrations from DB. Returns {pi_id: narration_dict}."""
    if not pi_ids:
        return {}
    placeholders = ", ".join(["?"] * len(pi_ids))
    rows = con.execute(f"""
        SELECT pi_id, narrative, match_strength, key_papers
        FROM narrations
        WHERE pi_id IN ({placeholders})
          AND query = ?
          AND profile_hash = ?
    """, pi_ids + [query, p_hash]).fetchall()

    cached = {}
    for r in rows:
        key_papers = json.loads(r[3]) if r[3] else []
        cached[str(r[0])] = {
            "narrative": r[1],
            "match_strength": r[2],
            "key_papers": key_papers,
        }
    return cached


def _save_narrations(
    con: duckdb.DuckDBPyConnection,
    narrations: list[PINarrative],
    query: str,
    p_hash: str,
    model: str,
):
    """Save generated narrations to the database."""
    for n in narrations:
        key_papers_json = json.dumps(n.key_papers)
        con.execute("""
            INSERT INTO narrations (pi_id, query, profile_hash, narrative, match_strength, key_papers, model)
            VALUES (?::UUID, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (pi_id, query, profile_hash) DO UPDATE SET
                narrative = EXCLUDED.narrative,
                match_strength = EXCLUDED.match_strength,
                key_papers = EXCLUDED.key_papers,
                model = EXCLUDED.model
        """, [n.pi_id, query, p_hash, n.narrative, n.match_strength, key_papers_json, model])


def narrate(
    query: str,
    pis: list[dict],
    profile: str | None = None,
    model: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> list[dict]:
    """Generate narratives for a list of PI results.

    Checks the database for cached narrations first, then generates
    missing ones via LLM. Saves new narrations to the database.

    Batches all uncached PIs into a single LLM call. Returns the same
    PI dicts with added 'narrative', 'match_strength', and 'key_papers' fields.
    """
    if not pis:
        return pis

    model = model or get_llm_model()
    p_hash = profile_hash(profile) if profile else "no_profile"
    profile_text = format_profile_for_llm(profile)

    # Check cache
    cached = {}
    if con is not None:
        try:
            pi_ids = [pi["id"] for pi in pis]
            cached = _load_cached_narrations(con, pi_ids, query, p_hash)
        except Exception:
            pass  # Table might not exist yet in old DBs

    # Apply cached narrations and find which PIs still need generation
    pis_to_generate = []
    for pi in pis:
        if pi["id"] in cached:
            c = cached[pi["id"]]
            pi["narrative"] = c["narrative"]
            pi["match_strength"] = c["match_strength"]
            pi["key_papers"] = c["key_papers"]
        else:
            pis_to_generate.append(pi)

    if not pis_to_generate:
        return pis

    # Build compact PI summaries for uncached PIs
    pi_summaries = [_build_pi_summary(pi) for pi in pis_to_generate]

    prompt = NARRATION_PROMPT.format(
        query=query,
        profile_text=profile_text,
        pi_summaries="\n\n".join(pi_summaries),
    )

    try:
        client = instructor.from_litellm(litellm.completion)
        result = client.chat.completions.create(
            model=model,
            response_model=NarrationResult,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )

        # Merge narratives back into PI dicts
        narrative_map = {n.pi_id: n for n in result.narratives}
        for pi in pis_to_generate:
            narr = narrative_map.get(pi["id"])
            if narr:
                pi["narrative"] = narr.narrative
                pi["match_strength"] = narr.match_strength
                pi["key_papers"] = narr.key_papers

        # Save to database
        if con is not None:
            try:
                _save_narrations(con, result.narratives, query, p_hash, model)
            except Exception:
                pass  # Don't crash if save fails

    except Exception:
        for pi in pis_to_generate:
            pi["narrative"] = None
            pi["match_strength"] = None

    return pis


def _build_pi_summary(pi: dict) -> str:
    """Build a compact text summary of a PI for the narration prompt."""
    parts = [f"### PI ID: {pi['id']}"]
    parts.append(f"Name: {pi.get('name', 'Unknown')}")

    if pi.get("institution_name"):
        parts.append(f"Institution: {pi['institution_name']}")
    if pi.get("department_name"):
        parts.append(f"Department: {pi['department_name']}")
    if pi.get("career_stage"):
        parts.append(f"Career stage: {pi['career_stage']}")
    if pi.get("h_index"):
        parts.append(f"h-index: {pi['h_index']}")
    if pi.get("is_taking_students") and pi["is_taking_students"] != "unknown":
        parts.append(f"Taking students: {pi['is_taking_students']}")
    if pi.get("lab_name"):
        parts.append(f"Lab: {pi['lab_name']}")
    if pi.get("research_description"):
        parts.append(f"Research: {pi['research_description']}")

    # Add top papers
    papers = pi.get("top_papers", [])
    if papers:
        paper_lines = []
        for p in papers[:5]:
            line = p.get("title", "Untitled")
            if p.get("year"):
                line += f" ({p['year']}"
                if p.get("citation_count"):
                    line += f", {p['citation_count']} citations"
                line += ")"
            if p.get("abstract"):
                line += f" — {p['abstract'][:150]}"
            paper_lines.append(f"  - {line}")
        parts.append("Papers:\n" + "\n".join(paper_lines))

    return "\n".join(parts)
