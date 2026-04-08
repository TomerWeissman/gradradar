"""Insert and update logic for DuckDB with deduplication."""

import uuid
from datetime import datetime, timezone

import duckdb
import jellyfish


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _jaro_winkler(s1: str, s2: str) -> float:
    """Compute Jaro-Winkler similarity between two strings (case-insensitive)."""
    return jellyfish.jaro_winkler_similarity(s1.lower().strip(), s2.lower().strip())


# --- Institution ---


def upsert_institution(con: duckdb.DuckDBPyConnection, record: dict) -> str:
    """Insert or update an institution by name + country. Returns the UUID."""
    existing = con.execute(
        "SELECT id FROM institutions WHERE name = ? AND country = ?",
        [record["name"], record.get("country")],
    ).fetchone()

    if existing:
        record_id = existing[0]
        _update_record(con, "institutions", record_id, record)
        return str(record_id)

    record_id = record.get("id", _new_id())
    cols = ["id"] + [k for k in record if k != "id"]
    vals = [record_id] + [record[k] for k in record if k != "id"]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    con.execute(f"INSERT INTO institutions ({col_names}) VALUES ({placeholders})", vals)
    return str(record_id)


# --- PI ---


def upsert_pi(con: duckdb.DuckDBPyConnection, record: dict) -> str:
    """Insert or update a PI. Dedup by openalex_id, then name+institution fuzzy match.

    Returns the UUID. Logs near-matches to possible_duplicates.
    """
    # Primary key: openalex_id
    if record.get("openalex_id"):
        existing = con.execute(
            "SELECT id FROM pis WHERE openalex_id = ?", [record["openalex_id"]]
        ).fetchone()
        if existing:
            record_id = existing[0]
            _update_record(con, "pis", record_id, record)
            return str(record_id)

    # Fallback: name + institution fuzzy match
    institution_id = record.get("institution_id")
    if institution_id:
        candidates = con.execute(
            "SELECT id, name FROM pis WHERE institution_id = ?", [institution_id]
        ).fetchall()
    else:
        candidates = con.execute("SELECT id, name FROM pis").fetchall()

    best_match = None
    best_score = 0.0
    for cand_id, cand_name in candidates:
        score = _jaro_winkler(record["name"], cand_name)
        if score > best_score:
            best_score = score
            best_match = (cand_id, cand_name)

    # Exact enough match (>=0.95) — update existing
    if best_match and best_score >= 0.95:
        _update_record(con, "pis", best_match[0], record)
        return str(best_match[0])

    # Near match (0.75-0.95) — log as possible duplicate, still insert new
    if best_match and best_score >= 0.75:
        _log_possible_duplicate(
            con,
            record_type="pis",
            record_id_1=best_match[0],
            name_1=best_match[1],
            name_2=record["name"],
            similarity_score=best_score,
            institution_id=institution_id,
        )

    # Insert new record
    record_id = record.get("id", _new_id())
    cols = ["id"] + [k for k in record if k != "id"]
    vals = [record_id] + [record[k] for k in record if k != "id"]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    con.execute(f"INSERT INTO pis ({col_names}) VALUES ({placeholders})", vals)
    return str(record_id)


# --- Paper ---


def upsert_paper(con: duckdb.DuckDBPyConnection, record: dict) -> str:
    """Insert or update a paper by DOI or openalex_id. Returns the UUID."""
    # Try DOI first
    if record.get("doi"):
        existing = con.execute("SELECT id FROM papers WHERE doi = ?", [record["doi"]]).fetchone()
        if existing:
            _update_record(con, "papers", existing[0], record)
            return str(existing[0])

    # Try openalex_id
    if record.get("openalex_id"):
        existing = con.execute("SELECT id FROM papers WHERE openalex_id = ?", [record["openalex_id"]]).fetchone()
        if existing:
            _update_record(con, "papers", existing[0], record)
            return str(existing[0])

    record_id = record.get("id", _new_id())
    cols = ["id"] + [k for k in record if k != "id"]
    vals = [record_id] + [record[k] for k in record if k != "id"]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    con.execute(f"INSERT INTO papers ({col_names}) VALUES ({placeholders})", vals)
    return str(record_id)


# --- Program ---


def upsert_program(con: duckdb.DuckDBPyConnection, record: dict) -> str:
    """Insert or update a program by name + institution_id. Returns the UUID."""
    existing = con.execute(
        "SELECT id FROM programs WHERE name = ? AND institution_id = ?",
        [record["name"], record.get("institution_id")],
    ).fetchone()

    if existing:
        _update_record(con, "programs", existing[0], record)
        return str(existing[0])

    record_id = record.get("id", _new_id())
    cols = ["id"] + [k for k in record if k != "id"]
    vals = [record_id] + [record[k] for k in record if k != "id"]
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    con.execute(f"INSERT INTO programs ({col_names}) VALUES ({placeholders})", vals)
    return str(record_id)


# --- Author-Paper junction ---


def insert_author_paper(con: duckdb.DuckDBPyConnection, record: dict) -> str:
    """Insert an author-paper link. Returns the UUID."""
    # Check for existing link
    existing = con.execute(
        "SELECT id FROM author_paper WHERE author_id = ? AND paper_id = ?",
        [record["author_id"], record["paper_id"]],
    ).fetchone()
    if existing:
        return str(existing[0])

    record_id = _new_id()
    con.execute(
        "INSERT INTO author_paper (id, author_id, paper_id, author_position, is_corresponding) VALUES (?, ?, ?, ?, ?)",
        [record_id, record["author_id"], record["paper_id"],
         record.get("author_position"), record.get("is_corresponding")],
    )
    return record_id


# --- Citation ---


def insert_citation(con: duckdb.DuckDBPyConnection, citing_id: str, cited_id: str):
    """Insert a citation edge. Ignores duplicates."""
    con.execute(
        """INSERT INTO citations (citing_paper_id, cited_paper_id)
           SELECT ?, ? WHERE NOT EXISTS (
               SELECT 1 FROM citations WHERE citing_paper_id = ? AND cited_paper_id = ?
           )""",
        [citing_id, cited_id, citing_id, cited_id],
    )


# --- Scrape log ---


def log_scrape(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    phase: str,
    command: str,
    records_added: int = 0,
    records_updated: int = 0,
    records_failed: int = 0,
    notes: str = None,
) -> str:
    """Write to scrape_log. Returns the log entry UUID."""
    log_id = _new_id()
    con.execute(
        """INSERT INTO scrape_log
           (id, run_id, started_at, completed_at, records_added, records_updated, records_failed, phase, command, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [log_id, run_id, _now(), _now(), records_added, records_updated, records_failed, phase, command, notes],
    )
    return log_id


# --- Update queue ---


def queue_update(
    con: duckdb.DuckDBPyConnection,
    record_type: str,
    source_url: str,
    priority: int = 3,
    reason: str = None,
    record_id: str = None,
) -> str:
    """Write to update_queue. Returns the queue entry UUID."""
    queue_id = _new_id()
    con.execute(
        """INSERT INTO update_queue
           (id, record_type, record_id, source_url, priority, reason, queued_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
        [queue_id, record_type, record_id, source_url, priority, reason, _now()],
    )
    return queue_id


# --- Internal helpers ---


def _update_record(con: duckdb.DuckDBPyConnection, table: str, record_id, record: dict):
    """Update non-null fields of an existing record by id."""
    # Only update fields that are provided and not 'id'
    updates = {k: v for k, v in record.items() if k != "id" and v is not None}
    if not updates:
        return
    set_clause = ", ".join([f'"{k}" = ?' for k in updates])
    values = list(updates.values()) + [str(record_id)]
    con.execute(f'UPDATE "{table}" SET {set_clause} WHERE id = ?', values)


def _log_possible_duplicate(
    con: duckdb.DuckDBPyConnection,
    record_type: str,
    record_id_1,
    name_1: str,
    name_2: str,
    similarity_score: float,
    institution_id=None,
):
    """Log a near-match to the possible_duplicates table."""
    # Get institution names for context
    inst_1 = inst_2 = None
    if institution_id:
        row = con.execute("SELECT name FROM institutions WHERE id = ?", [str(institution_id)]).fetchone()
        if row:
            inst_1 = inst_2 = row[0]

    # Use a placeholder ID for the new record (it hasn't been inserted yet)
    placeholder_id = _new_id()
    con.execute(
        """INSERT INTO possible_duplicates
           (id, record_type, record_id_1, record_id_2, name_1, name_2,
            institution_1, institution_2, similarity_score, detection_method, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'name_match', 'pending')""",
        [_new_id(), record_type, str(record_id_1), placeholder_id,
         name_1, name_2, inst_1, inst_2, similarity_score],
    )
