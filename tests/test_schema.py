"""Tests for DuckDB schema creation."""

import tempfile
from pathlib import Path

import duckdb
import pytest

from gradradar.db.schema import (
    ALL_TABLES,
    TABLE_COLUMN_COUNTS,
    create_fts_indexes,
    create_schema,
    get_column_count,
    get_row_count,
    get_table_names,
    validate_schema,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.duckdb"


@pytest.fixture
def db(db_path):
    con = create_schema(db_path)
    yield con
    con.close()


def test_all_tables_created(db):
    tables = get_table_names(db)
    for expected in ALL_TABLES:
        assert expected in tables, f"Missing table: {expected}"


def test_correct_column_counts(db):
    for table, expected_count in TABLE_COLUMN_COUNTS.items():
        actual = get_column_count(db, table)
        assert actual == expected_count, f"{table}: expected {expected_count} columns, got {actual}"


def test_schema_migration_recorded(db):
    row = db.execute("SELECT migration_id FROM schema_migrations").fetchone()
    assert row is not None
    assert row[0] == "v1_initial_schema"


def test_empty_tables_have_zero_rows(db):
    for table in ALL_TABLES:
        if table == "schema_migrations":
            # Has the initial migration record
            assert get_row_count(db, table) == 1, f"{table} should have 1 migration row"
        else:
            assert get_row_count(db, table) == 0, f"{table} should be empty"


def test_validate_passes_on_clean_schema(db):
    errors = validate_schema(db)
    assert errors == [], f"Unexpected errors: {errors}"


def test_idempotent_schema_creation(db_path):
    """Creating schema twice should not fail."""
    con1 = create_schema(db_path)
    con1.close()
    con2 = create_schema(db_path)
    tables = get_table_names(con2)
    assert len(tables) >= len(ALL_TABLES)
    con2.close()


def test_check_constraints(db):
    """CHECK constraints should reject invalid values."""
    # Invalid region
    with pytest.raises(duckdb.ConstraintException):
        db.execute(
            "INSERT INTO institutions (id, name, region) VALUES (gen_random_uuid(), 'Test Uni', 'Asia')"
        )

    # Invalid career_stage
    with pytest.raises(duckdb.ConstraintException):
        db.execute(
            "INSERT INTO pis (id, name, career_stage) VALUES (gen_random_uuid(), 'Test PI', 'dean')"
        )

    # Invalid is_taking_students
    with pytest.raises(duckdb.ConstraintException):
        db.execute(
            "INSERT INTO pis (id, name, is_taking_students) VALUES (gen_random_uuid(), 'Test PI', 'maybe')"
        )


def test_default_values(db):
    """Default values should be applied correctly."""
    db.execute("INSERT INTO pis (id, name) VALUES (gen_random_uuid(), 'Test PI')")
    row = db.execute("SELECT is_taking_students, theory_category FROM pis WHERE name = 'Test PI'").fetchone()
    assert row[0] == "unknown"
    assert row[1] == "unknown"


def test_fts_indexes_on_empty_db(db):
    """FTS indexes should be creatable even on empty tables."""
    create_fts_indexes(db)
    # Verify the materialized tables exist
    tables = get_table_names(db)
    assert "pi_search_docs_fts" in tables
    assert "program_search_docs_fts" in tables
