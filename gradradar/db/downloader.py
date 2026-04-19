"""Publish database to R2 and download on first run.

Two paths for reading from R2:
  - Authenticated (publisher): boto3 / S3 client with credentials.
  - Public (end user): plain HTTPS via the bucket's public R2.dev URL.

`publish()` always uses the authenticated path. `download()` and
`fetch_remote_manifest()` prefer the authenticated path when credentials
are present, otherwise fall back to the public URL so end users without
R2 credentials can still install the database.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn

from gradradar.config import get_db_path, get_gradradar_home, get_r2_config

console = Console()


def _get_s3_client():
    """Create an S3 client configured for Cloudflare R2."""
    r2 = get_r2_config()
    if not r2["access_key_id"]:
        raise RuntimeError("R2 credentials not configured. Set CLOUDFLARE_R2_ACCESS_KEY_ID in .env")
    return boto3.client(
        "s3",
        endpoint_url=r2["endpoint_url"],
        aws_access_key_id=r2["access_key_id"],
        aws_secret_access_key=r2["secret_access_key"],
        region_name="auto",
    )


def _has_credentials() -> bool:
    return bool(get_r2_config()["access_key_id"])


def _get_public_base_url() -> str:
    """Return the bucket's public base URL, or empty string if unset."""
    return get_r2_config()["public_url"].rstrip("/")


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_manifest_path() -> Path:
    return get_gradradar_home() / "db" / "manifest.json"


def fetch_remote_manifest(s3=None, bucket=None, key: str = "latest/manifest.json") -> dict | None:
    """Fetch a manifest from R2. Returns None if not found.

    Uses S3 client when credentials are available (or explicitly passed in),
    otherwise falls back to public HTTPS via CLOUDFLARE_R2_PUBLIC_URL.
    """
    # Authenticated path: explicit s3 client OR credentials present
    if s3 is not None or _has_credentials():
        if s3 is None:
            s3 = _get_s3_client()
        if bucket is None:
            bucket = get_r2_config()["bucket_name"]
        try:
            resp = s3.get_object(Bucket=bucket, Key=key)
            return json.loads(resp["Body"].read())
        except s3.exceptions.NoSuchKey:
            return None
        except Exception:
            return None

    # Public path: no credentials, use public HTTPS
    public_url = _get_public_base_url()
    if not public_url:
        return None
    try:
        r = httpx.get(f"{public_url}/{key}", timeout=30.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def publish(version_override: str = None, message: str = None):
    """Publish the local database to R2.

    - Computes SHA-256 of the db file
    - Auto-increments version from remote manifest
    - Uploads db + manifest to R2 under [version]/ and latest/
    """
    db_path = get_db_path()
    if not db_path.exists():
        console.print("[red]No database found at {db_path}. Run 'gradradar build' first.[/red]")
        return

    r2 = get_r2_config()
    s3 = _get_s3_client()
    bucket = r2["bucket_name"]

    # Compute checksum
    console.print("[dim]Computing checksum...[/dim]")
    checksum = _sha256(db_path)
    db_size = db_path.stat().st_size

    # Determine version
    remote_manifest = fetch_remote_manifest(s3, bucket)
    if version_override:
        version = version_override
    elif remote_manifest:
        # Auto-increment patch version
        parts = remote_manifest["version"].split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        version = ".".join(parts)
    else:
        version = "0.1.0"

    manifest = {
        "version": version,
        "schema_version": "1.0",
        "build_date": datetime.now(timezone.utc).isoformat(),
        "sha256": checksum,
        "size_bytes": db_size,
        "ttl_days": 30,
        "message": message or "",
    }

    # Upload database file
    console.print(f"[blue]Uploading database ({db_size / 1024 / 1024:.1f} MB) as v{version}...[/blue]")
    with open(db_path, "rb") as f:
        s3.upload_fileobj(f, bucket, f"{version}/gradradar.duckdb")

    # Upload manifest to versioned path and latest/
    manifest_json = json.dumps(manifest, indent=2)
    s3.put_object(Bucket=bucket, Key=f"{version}/manifest.json", Body=manifest_json)
    s3.put_object(Bucket=bucket, Key="latest/manifest.json", Body=manifest_json)

    console.print(f"[green]Published v{version} to R2.[/green]")
    console.print(f"  SHA-256: {checksum}")
    console.print(f"  Size: {db_size / 1024 / 1024:.1f} MB")
    if r2["public_url"]:
        console.print(f"  URL: {r2['public_url']}/{version}/gradradar.duckdb")


def _download_via_s3(bucket: str, key: str, dest: Path, expected_size: int):
    """Download an object from R2 using the S3 client."""
    s3 = _get_s3_client()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
    ) as progress:
        task = progress.add_task("Downloading", total=expected_size)
        with open(dest, "wb") as f:
            s3.download_fileobj(
                bucket, key, f,
                Callback=lambda bytes_transferred: progress.update(task, advance=bytes_transferred),
            )


def _download_via_public_url(url: str, dest: Path, expected_size: int):
    """Download a file via plain HTTPS from a public URL."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
    ) as progress:
        task = progress.add_task("Downloading", total=expected_size)
        with httpx.stream("GET", url, timeout=None, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))


def download(version: str = None, force: bool = False, offline: bool = False):
    """Download the database from R2.

    - Fetches manifest to get version + checksum
    - Downloads db file with progress bar
    - Verifies SHA-256

    If R2 credentials are present, uses the S3 client. Otherwise falls back
    to the bucket's public HTTPS URL (CLOUDFLARE_R2_PUBLIC_URL).
    """
    db_path = get_db_path()
    manifest_path = _get_manifest_path()

    if db_path.exists() and not force:
        console.print("[yellow]Database already exists. Use --force to overwrite.[/yellow]")
        return

    if offline:
        console.print("[red]Cannot download in offline mode.[/red]")
        return

    r2 = get_r2_config()
    bucket = r2["bucket_name"]

    if not _has_credentials() and not _get_public_base_url():
        console.print("[red]No R2 credentials and no CLOUDFLARE_R2_PUBLIC_URL set. Cannot download.[/red]")
        return

    # Fetch manifest (auto-detects auth vs public path)
    manifest_key = f"{version}/manifest.json" if version else "latest/manifest.json"
    manifest = fetch_remote_manifest(key=manifest_key)
    if manifest is None:
        console.print("[red]Failed to fetch manifest from R2.[/red]")
        console.print("[dim]No database has been published yet, or the public URL is misconfigured.[/dim]")
        return

    target_version = manifest["version"]
    expected_sha = manifest["sha256"]
    expected_size = manifest.get("size_bytes", 0)

    console.print(f"[blue]Downloading v{target_version} ({expected_size / 1024 / 1024:.1f} MB)...[/blue]")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_key = f"{target_version}/gradradar.duckdb"

    try:
        if _has_credentials():
            _download_via_s3(bucket, db_key, db_path, expected_size)
        else:
            url = f"{_get_public_base_url()}/{db_key}"
            _download_via_public_url(url, db_path, expected_size)
    except Exception as e:
        if db_path.exists():
            db_path.unlink()
        console.print(f"[red]Download failed: {e}[/red]")
        return

    # Verify checksum
    console.print("[dim]Verifying checksum...[/dim]")
    actual_sha = _sha256(db_path)
    if actual_sha != expected_sha:
        db_path.unlink()
        console.print("[red]Checksum mismatch! Download may be corrupted. Please try again.[/red]")
        return

    # Save manifest locally
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Database v{target_version} installed successfully.[/green]")
    console.print(f"  Path: {db_path}")
