"""Manages ~/.gradradar/ local config and environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (for development) or system env
load_dotenv()


def get_gradradar_home() -> Path:
    """Return the base gradradar directory (~/.gradradar/)."""
    return Path(os.environ.get("GRADRADAR_HOME", Path.home() / ".gradradar"))


def get_db_path() -> Path:
    """Return the path to the DuckDB database file."""
    custom = os.environ.get("GRADRADAR_DB_PATH")
    if custom:
        return Path(custom) / "gradradar.duckdb"
    return get_gradradar_home() / "db" / "gradradar.duckdb"


def get_profile_path() -> Path:
    return get_gradradar_home() / "profile.md"


def get_cache_path() -> Path:
    return get_gradradar_home() / "cache"


def get_snapshot_path() -> Path:
    return get_gradradar_home() / "db" / "snapshots"


def ensure_dirs():
    """Create the ~/.gradradar/ directory structure if it doesn't exist."""
    dirs = [
        get_gradradar_home() / "db" / "snapshots",
        get_cache_path() / "raw_html",
        get_cache_path() / "llm_responses",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def get_r2_config() -> dict:
    """Return R2 credentials from environment. Raises if missing."""
    account_id = os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID", "")
    keys = {
        "account_id": account_id,
        "access_key_id": os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", ""),
        "secret_access_key": os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", ""),
        "bucket_name": os.environ.get("CLOUDFLARE_R2_BUCKET_NAME", "gradradar-db"),
        "public_url": os.environ.get("CLOUDFLARE_R2_PUBLIC_URL", ""),
        "endpoint_url": f"https://{account_id}.r2.cloudflarestorage.com" if account_id else "",
    }
    return keys


def get_llm_model() -> str:
    return os.environ.get("GRADRADAR_LLM_MODEL", "anthropic/claude-sonnet-4-5")


def get_anthropic_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def get_openai_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "")
