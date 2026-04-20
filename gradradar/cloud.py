"""Client for the gradradar cloud backend (Supabase + Edge Function).

Read path uses PostgREST's `plfts` operator directly (no Edge Function needed).
Write path (contributions) goes through the `contribute` Edge Function so the
service_role key never leaves the server side.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from gradradar.config import get_gradradar_home

DEFAULT_SUPABASE_URL = "https://dtmkfqldnungnqvikizq.supabase.co"
# Publishable key is safe to ship — RLS policies enforce read-only access, and
# all writes go through the contribute Edge Function (which uses service_role
# internally). Equivalent pattern to CLOUDFLARE_R2_PUBLIC_URL in config.py.
DEFAULT_PUBLISHABLE_KEY = "sb_publishable_1Iv7VHSCHXJAz-RbzQOhug_M59llPuh"


def get_supabase_url() -> str:
    return os.environ.get("SUPABASE_URL") or DEFAULT_SUPABASE_URL


def get_publishable_key() -> str:
    # Supabase's new name for the "anon" key. Safe in client code (RLS-guarded).
    return os.environ.get("SUPABASE_PUBLISHABLE_KEY") or DEFAULT_PUBLISHABLE_KEY


def _rest_headers() -> dict:
    key = get_publishable_key()
    if not key:
        raise RuntimeError(
            "SUPABASE_PUBLISHABLE_KEY not set. Add it to ~/.gradradar/.env or a project .env."
        )
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def get_contributor_id() -> str:
    """Return (or create) an anonymous contributor UUID stored locally."""
    path = get_gradradar_home() / "contributor_id"
    if path.exists():
        val = path.read_text().strip()
        if val:
            return val
    path.parent.mkdir(parents=True, exist_ok=True)
    new_id = str(uuid.uuid4())
    path.write_text(new_id + "\n")
    path.chmod(0o600)
    return new_id


# Columns selected for search results. Must match the dict shape used by the
# existing reranker/narrator (see fts_search.fts_search_pis).
PI_SEARCH_COLUMNS = [
    "id",
    "name",
    "institution_id",
    "h_index",
    "total_citations",
    "theory_category",
    "is_taking_students",
    "career_stage",
    "research_description",
]


def cloud_search_pis(query: str, limit: int = 100) -> list[dict]:
    """Full-text search against the cloud `pis` table via PostgREST `plfts`.

    Returns the same dict shape as gradradar.search.fts_search.fts_search_pis
    so downstream stages (reranker, narrator) are drop-in compatible.
    """
    if not query.strip():
        return []

    base = get_supabase_url().rstrip("/")
    # PostgREST embedded select: pulls institution name in a single round trip.
    params = {
        "select": ",".join(PI_SEARCH_COLUMNS) + ",institutions(name)",
        "search_vector": f"plfts(english).{query}",
        "order": "h_index.desc.nullslast",
        "limit": str(limit),
    }
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{base}/rest/v1/pis", headers=_rest_headers(), params=params)
        r.raise_for_status()
        rows = r.json()

    out = []
    for row in rows:
        inst = row.get("institutions") or {}
        out.append({
            "id": str(row["id"]),
            "name": row["name"],
            "bm25_score": 0.0,
            "institution_id": str(row["institution_id"]) if row.get("institution_id") else None,
            "institution_name": inst.get("name"),
            "h_index": row.get("h_index"),
            "total_citations": row.get("total_citations"),
            "theory_category": row.get("theory_category"),
            "is_taking_students": row.get("is_taking_students"),
            "career_stage": row.get("career_stage"),
            "research_description": row.get("research_description"),
        })
    return out


def cloud_get_pi(pi_id: str) -> dict | None:
    """Fetch a single PI row by id."""
    base = get_supabase_url().rstrip("/")
    params = {"select": "*", "id": f"eq.{pi_id}", "limit": "1"}
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{base}/rest/v1/pis", headers=_rest_headers(), params=params)
        r.raise_for_status()
        rows = r.json()
    return rows[0] if rows else None


def cloud_get_institution(institution_id: str) -> dict | None:
    base = get_supabase_url().rstrip("/")
    params = {"select": "*", "id": f"eq.{institution_id}", "limit": "1"}
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{base}/rest/v1/institutions", headers=_rest_headers(), params=params)
        r.raise_for_status()
        rows = r.json()
    return rows[0] if rows else None


def cloud_contribute(
    pi_id: str,
    fields: dict,
    source_url: str,
    content_hash: str | None,
    model: str,
) -> dict:
    """POST an enrichment contribution to the Edge Function.

    Raises httpx.HTTPStatusError on non-2xx. The function returns a small JSON
    payload: {ok, pi_id, fields_written, rate_limit}.
    """
    base = get_supabase_url().rstrip("/")
    payload = {
        "pi_id": pi_id,
        "source_url": source_url,
        "content_hash": content_hash,
        "model": model,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "contributor_id": get_contributor_id(),
        "fields": fields,
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{base}/functions/v1/contribute",
            headers=_rest_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()
