"""Tests for the writer module: upserts, dedup, and logging."""

import pytest
import duckdb

from gradradar.db.schema import create_schema
from gradradar.db.writer import (
    insert_author_paper,
    insert_citation,
    log_scrape,
    queue_update,
    upsert_institution,
    upsert_paper,
    upsert_pi,
    upsert_program,
)


@pytest.fixture
def db(tmp_path):
    con = create_schema(tmp_path / "test.duckdb")
    yield con
    con.close()


# --- Institution tests ---


class TestUpsertInstitution:
    def test_insert_new(self, db):
        uid = upsert_institution(db, {"name": "MIT", "country": "US", "region": "US"})
        assert uid is not None
        row = db.execute("SELECT name, country FROM institutions WHERE id = ?", [uid]).fetchone()
        assert row == ("MIT", "US")

    def test_update_existing(self, db):
        uid1 = upsert_institution(db, {"name": "MIT", "country": "US", "region": "US"})
        uid2 = upsert_institution(db, {"name": "MIT", "country": "US", "region": "US", "city": "Cambridge"})
        assert uid1 == uid2
        row = db.execute("SELECT city FROM institutions WHERE id = ?", [uid1]).fetchone()
        assert row[0] == "Cambridge"

    def test_different_country_creates_new(self, db):
        uid1 = upsert_institution(db, {"name": "Cambridge", "country": "UK"})
        uid2 = upsert_institution(db, {"name": "Cambridge", "country": "US"})
        assert uid1 != uid2


# --- PI tests ---


class TestUpsertPI:
    def _insert_institution(self, db):
        return upsert_institution(db, {"name": "MIT", "country": "US", "region": "US"})

    def test_insert_new_pi(self, db):
        inst_id = self._insert_institution(db)
        uid = upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst_id, "openalex_id": "A123"})
        assert uid is not None
        count = db.execute("SELECT COUNT(*) FROM pis").fetchone()[0]
        assert count == 1

    def test_update_by_openalex_id(self, db):
        inst_id = self._insert_institution(db)
        uid1 = upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst_id, "openalex_id": "A123"})
        uid2 = upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst_id, "openalex_id": "A123", "h_index": 25})
        assert uid1 == uid2
        row = db.execute("SELECT h_index FROM pis WHERE id = ?", [uid1]).fetchone()
        assert row[0] == 25
        count = db.execute("SELECT COUNT(*) FROM pis").fetchone()[0]
        assert count == 1

    def test_same_name_different_institution(self, db):
        inst1 = upsert_institution(db, {"name": "MIT", "country": "US", "region": "US"})
        inst2 = upsert_institution(db, {"name": "Stanford", "country": "US", "region": "US"})
        uid1 = upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst1})
        uid2 = upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst2})
        assert uid1 != uid2
        count = db.execute("SELECT COUNT(*) FROM pis").fetchone()[0]
        assert count == 2

    def test_fuzzy_name_logs_duplicate(self, db):
        inst_id = self._insert_institution(db)
        upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst_id})
        # "Wei Zhu" scores ~0.90 — in the 0.75-0.95 near-match range
        upsert_pi(db, {"name": "Wei Zhu", "institution_id": inst_id})
        count = db.execute("SELECT COUNT(*) FROM pis").fetchone()[0]
        assert count == 2
        dupes = db.execute("SELECT COUNT(*) FROM possible_duplicates WHERE status = 'pending'").fetchone()[0]
        assert dupes >= 1

    def test_exact_name_match_updates(self, db):
        inst_id = self._insert_institution(db)
        uid1 = upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst_id})
        uid2 = upsert_pi(db, {"name": "Wei Zhang", "institution_id": inst_id, "h_index": 30})
        assert uid1 == uid2
        count = db.execute("SELECT COUNT(*) FROM pis").fetchone()[0]
        assert count == 1


# --- Paper tests ---


class TestUpsertPaper:
    def test_insert_new(self, db):
        uid = upsert_paper(db, {"title": "Attention Is All You Need", "doi": "10.1234/test", "year": 2017})
        assert uid is not None
        count = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        assert count == 1

    def test_update_by_doi(self, db):
        uid1 = upsert_paper(db, {"title": "Attention Is All You Need", "doi": "10.1234/test"})
        uid2 = upsert_paper(db, {"title": "Attention Is All You Need", "doi": "10.1234/test", "citation_count": 50000})
        assert uid1 == uid2
        row = db.execute("SELECT citation_count FROM papers WHERE id = ?", [uid1]).fetchone()
        assert row[0] == 50000

    def test_update_by_openalex_id(self, db):
        uid1 = upsert_paper(db, {"title": "Test Paper", "openalex_id": "W123"})
        uid2 = upsert_paper(db, {"title": "Test Paper", "openalex_id": "W123", "venue": "NeurIPS"})
        assert uid1 == uid2
        count = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        assert count == 1

    def test_no_match_creates_new(self, db):
        uid1 = upsert_paper(db, {"title": "Paper A"})
        uid2 = upsert_paper(db, {"title": "Paper B"})
        assert uid1 != uid2


# --- Program tests ---


class TestUpsertProgram:
    def test_insert_and_update(self, db):
        inst_id = upsert_institution(db, {"name": "MIT", "country": "US"})
        uid1 = upsert_program(db, {"name": "MS in CS", "institution_id": inst_id})
        uid2 = upsert_program(db, {"name": "MS in CS", "institution_id": inst_id, "duration_months": 24})
        assert uid1 == uid2
        row = db.execute("SELECT duration_months FROM programs WHERE id = ?", [uid1]).fetchone()
        assert row[0] == 24


# --- Junction table tests ---


class TestAuthorPaper:
    def test_insert_link(self, db):
        pi_id = upsert_pi(db, {"name": "Test PI"})
        paper_id = upsert_paper(db, {"title": "Test Paper"})
        ap_id = insert_author_paper(db, {"author_id": pi_id, "paper_id": paper_id, "author_position": "first"})
        assert ap_id is not None

    def test_duplicate_ignored(self, db):
        pi_id = upsert_pi(db, {"name": "Test PI"})
        paper_id = upsert_paper(db, {"title": "Test Paper"})
        ap1 = insert_author_paper(db, {"author_id": pi_id, "paper_id": paper_id})
        ap2 = insert_author_paper(db, {"author_id": pi_id, "paper_id": paper_id})
        assert ap1 == ap2
        count = db.execute("SELECT COUNT(*) FROM author_paper").fetchone()[0]
        assert count == 1


class TestCitation:
    def test_insert_citation(self, db):
        p1 = upsert_paper(db, {"title": "Paper A"})
        p2 = upsert_paper(db, {"title": "Paper B"})
        insert_citation(db, p1, p2)
        count = db.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
        assert count == 1

    def test_duplicate_citation_ignored(self, db):
        p1 = upsert_paper(db, {"title": "Paper A"})
        p2 = upsert_paper(db, {"title": "Paper B"})
        insert_citation(db, p1, p2)
        insert_citation(db, p1, p2)
        count = db.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
        assert count == 1


# --- Logging tests ---


class TestScrapeLog:
    def test_log_entry(self, db):
        log_id = log_scrape(db, run_id="run_001", phase="build_phase_1", command="build", records_added=100)
        assert log_id is not None
        row = db.execute("SELECT records_added, phase FROM scrape_log WHERE id = ?", [log_id]).fetchone()
        assert row[0] == 100
        assert row[1] == "build_phase_1"


class TestUpdateQueue:
    def test_queue_entry(self, db):
        qid = queue_update(db, record_type="pis", source_url="https://example.com", priority=2, reason="stale")
        row = db.execute("SELECT status, priority FROM update_queue WHERE id = ?", [qid]).fetchone()
        assert row[0] == "pending"
        assert row[1] == 2
