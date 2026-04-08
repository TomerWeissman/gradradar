"""Tests for FTS index creation and BM25 querying."""

import pytest

from gradradar.db.schema import create_fts_indexes, create_schema
from gradradar.db.writer import insert_author_paper, upsert_paper, upsert_pi


@pytest.fixture
def db(tmp_path):
    con = create_schema(tmp_path / "test.duckdb")
    yield con
    con.close()


def _seed_data(db):
    """Insert 5 PIs and 5 papers with author links."""
    pis = [
        {"name": "Alice Topology", "research_description": "Topological data analysis and persistent homology"},
        {"name": "Bob Neural", "research_description": "Deep neural network theory and optimization"},
        {"name": "Carol RL", "research_description": "Reinforcement learning and multi-agent systems"},
        {"name": "Dave Algebra", "research_description": "Algebraic geometry and representation theory"},
        {"name": "Eve NLP", "research_description": "Natural language processing and large language models"},
    ]
    papers = [
        {"title": "Persistent Homology for Neural Networks", "abstract": "We apply topological data analysis methods to understand deep learning."},
        {"title": "Optimization Landscape of Deep Networks", "abstract": "A theoretical analysis of the loss landscape in neural network training."},
        {"title": "Multi-Agent Reinforcement Learning", "abstract": "Cooperative strategies in multi-agent reinforcement learning environments."},
        {"title": "Representation Theory in Machine Learning", "abstract": "Algebraic structures and their applications to equivariant neural networks."},
        {"title": "Scaling Laws for Large Language Models", "abstract": "Empirical scaling laws for language model performance with compute and data."},
    ]

    pi_ids = [upsert_pi(db, p) for p in pis]
    paper_ids = [upsert_paper(db, p) for p in papers]

    # Link each PI to their paper
    for pi_id, paper_id in zip(pi_ids, paper_ids):
        insert_author_paper(db, {"author_id": pi_id, "paper_id": paper_id, "author_position": "first"})

    return pi_ids, paper_ids


def test_fts_on_papers(db):
    """BM25 search on papers should return relevant results."""
    _seed_data(db)
    create_fts_indexes(db)

    results = db.execute("""
        SELECT title, fts_main_papers.match_bm25(id, 'topological data analysis') AS score
        FROM papers
        WHERE score IS NOT NULL
        ORDER BY score
    """).fetchall()

    assert len(results) > 0
    # BM25 scores are negative in DuckDB; most negative = best match
    # The topological paper should be among the results
    titles = [r[0] for r in results]
    assert any("Persistent Homology" in t or "topological" in t.lower() for t in titles)


def test_fts_on_pi_search_docs(db):
    """BM25 search on PI search docs should return relevant PIs."""
    _seed_data(db)
    create_fts_indexes(db)

    results = db.execute("""
        SELECT name, fts_main_pi_search_docs_fts.match_bm25(id, 'reinforcement learning') AS score
        FROM pi_search_docs_fts
        WHERE score IS NOT NULL
        ORDER BY score
    """).fetchall()

    assert len(results) > 0
    # Carol RL should be in the results
    names = [r[0] for r in results]
    assert any("Carol" in n for n in names)


def test_fts_returns_nothing_for_unrelated_query(db):
    """A query with no matching terms should return empty results."""
    _seed_data(db)
    create_fts_indexes(db)

    results = db.execute("""
        SELECT title, fts_main_papers.match_bm25(id, 'quantum chromodynamics hadron collider') AS score
        FROM papers
        WHERE score IS NOT NULL
    """).fetchall()

    assert len(results) == 0


def test_fts_multiple_matches(db):
    """A broad query should match multiple papers."""
    _seed_data(db)
    create_fts_indexes(db)

    results = db.execute("""
        SELECT title, fts_main_papers.match_bm25(id, 'neural network') AS score
        FROM papers
        WHERE score IS NOT NULL
        ORDER BY score
    """).fetchall()

    # Should match at least the topology and optimization papers
    assert len(results) >= 2
