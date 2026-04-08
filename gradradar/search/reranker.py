"""LLM-based re-ranking of search results for relevance."""

from __future__ import annotations

import json

import instructor
import litellm
from pydantic import BaseModel, Field

from gradradar.config import get_llm_model

litellm.suppress_debug_info = True


class RankedResult(BaseModel):
    id: str
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        description="How relevant this PI is to the query (0=irrelevant, 1=perfect match).",
    )
    reason: str = Field(description="One-sentence explanation of the relevance score.")


class RerankedResults(BaseModel):
    results: list[RankedResult] = Field(
        description="PIs ranked by relevance to the query. Only include PIs with relevance >= 0.3."
    )


RERANK_PROMPT = """\
You are a search relevance judge for gradradar, a tool helping students find \
PhD labs in ML, CS, and Math.

Given a user's search query and a list of candidate PIs, score each PI's \
relevance to the query from 0.0 to 1.0.

Scoring guidelines:
- 1.0: PI's research directly matches the query topic
- 0.7-0.9: Strong topical overlap, closely related field
- 0.4-0.6: Some overlap but not a direct match
- 0.1-0.3: Tangential connection at best
- 0.0: Completely unrelated (e.g. biologist for a "reinforcement learning" query)

Only return PIs with relevance >= 0.3. Order by relevance_score descending.

User query: {query}
{profile_section}
Candidate PIs:
{candidates}
"""


def rerank(
    query: str,
    results: list[dict],
    top_k: int = 10,
    model: str | None = None,
    profile: dict | None = None,
) -> list[dict]:
    """Re-rank search results using LLM relevance scoring.

    Takes up to 30 candidates, returns the top_k most relevant.
    """
    if not results:
        return []

    model = model or get_llm_model()

    # Build compact candidate summaries for the LLM
    candidates = []
    for r in results[:30]:
        summary = {
            "id": r["id"],
            "name": r.get("name", ""),
            "institution": r.get("institution_name", ""),
            "research": (r.get("research_description") or "")[:300],
            "h_index": r.get("h_index"),
            "theory_category": r.get("theory_category"),
        }
        # Add top paper titles for context
        papers = r.get("top_papers", [])
        if papers:
            summary["top_papers"] = [p.get("title", "")[:80] for p in papers[:3]]
        candidates.append(summary)

    profile_section = ""
    if profile:
        profile_section = f"\nUser profile (use to boost relevant matches):\n{json.dumps(profile, indent=2)}\n"

    prompt = RERANK_PROMPT.format(
        query=query,
        candidates=json.dumps(candidates, indent=2),
        profile_section=profile_section,
    )

    try:
        client = instructor.from_litellm(litellm.completion)
        ranked = client.chat.completions.create(
            model=model,
            response_model=RerankedResults,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception:
        # If re-ranking fails, return original order
        return results[:top_k]

    # Map scores back to full result dicts
    score_map = {r.id: (r.relevance_score, r.reason) for r in ranked.results}

    scored_results = []
    for r in results[:30]:
        if r["id"] in score_map:
            score, reason = score_map[r["id"]]
            r["relevance_score"] = score
            r["relevance_reason"] = reason
            scored_results.append(r)

    scored_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return scored_results[:top_k]
