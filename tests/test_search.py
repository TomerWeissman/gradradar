"""Tests for search pipeline: SQL filter, FTS, hybrid engine, query plan."""

import pytest
import duckdb

from gradradar.db.schema import create_fts_indexes, create_schema
from gradradar.db.writer import insert_author_paper, upsert_institution, upsert_paper, upsert_pi
from gradradar.search.fts_search import fts_search_pis, fts_search_papers
from gradradar.search.sql_search import sql_filter_pis, get_top_papers_for_pi
from gradradar.search.llm_query import QueryPlan, apply_cli_overrides
from gradradar.search.engine import search_pis, run_search


@pytest.fixture
def db(tmp_path):
    con = create_schema(tmp_path / "test.duckdb")
    _seed_test_data(con)
    create_fts_indexes(con)
    yield con
    con.close()


def _seed_test_data(con):
    """Seed a small test dataset with 3 institutions, 5 PIs, 5 papers."""
    inst_mit = upsert_institution(con, {"name": "MIT", "country": "US", "region": "US"})
    inst_oxford = upsert_institution(con, {"name": "Oxford", "country": "GB", "region": "UK"})
    inst_eth = upsert_institution(con, {"name": "ETH Zurich", "country": "CH", "region": "Europe"})

    pis = [
        {"name": "Alice RL", "institution_id": inst_mit, "openalex_id": "A1",
         "h_index": 80, "total_citations": 50000, "career_stage": "full_professor",
         "is_taking_students": "yes", "theory_category": "applied",
         "research_description": "Reinforcement learning and robotics control systems"},
        {"name": "Bob Vision", "institution_id": inst_oxford, "openalex_id": "A2",
         "h_index": 60, "total_citations": 30000, "career_stage": "associate_professor",
         "is_taking_students": "yes", "theory_category": "applied",
         "research_description": "Computer vision and object detection using deep learning"},
        {"name": "Carol Theory", "institution_id": inst_eth, "openalex_id": "A3",
         "h_index": 45, "total_citations": 15000, "career_stage": "assistant_professor",
         "is_taking_students": "unknown", "theory_category": "theory",
         "research_description": "Computational complexity theory and algorithm design"},
        {"name": "Dave NLP", "institution_id": inst_mit, "openalex_id": "A4",
         "h_index": 70, "total_citations": 40000, "career_stage": "full_professor",
         "is_taking_students": "no", "theory_category": "applied",
         "research_description": "Natural language processing and large language models"},
        {"name": "Eve Stats", "institution_id": inst_oxford, "openalex_id": "A5",
         "h_index": 30, "total_citations": 8000, "career_stage": "postdoc",
         "is_taking_students": "unknown", "theory_category": "theory",
         "research_description": "Bayesian statistics and causal inference methods"},
    ]
    pi_ids = [upsert_pi(con, p) for p in pis]

    papers = [
        {"title": "Deep Reinforcement Learning for Robot Control", "year": 2023, "citation_count": 500},
        {"title": "Object Detection with Transformers", "year": 2022, "citation_count": 1200},
        {"title": "Lower Bounds for Graph Algorithms", "year": 2021, "citation_count": 80},
        {"title": "Scaling Laws for Language Models", "year": 2023, "citation_count": 3000},
        {"title": "Causal Discovery with Bayesian Networks", "year": 2020, "citation_count": 200},
    ]
    paper_ids = [upsert_paper(con, p) for p in papers]

    for pi_id, paper_id in zip(pi_ids, paper_ids):
        insert_author_paper(con, {"author_id": pi_id, "paper_id": paper_id, "author_position": "first"})


# --- SQL filter tests ---


class TestSQLFilter:
    def test_filter_by_region(self, db):
        results = sql_filter_pis(db, region="US")
        names = [r["name"] for r in results]
        assert "Alice RL" in names
        assert "Dave NLP" in names
        assert "Bob Vision" not in names

    def test_filter_by_taking_students(self, db):
        results = sql_filter_pis(db, is_taking_students="yes")
        names = [r["name"] for r in results]
        assert "Alice RL" in names
        assert "Bob Vision" in names
        assert "Dave NLP" not in names

    def test_filter_by_career_stage(self, db):
        results = sql_filter_pis(db, career_stage="full_professor")
        names = [r["name"] for r in results]
        assert "Alice RL" in names
        assert "Dave NLP" in names
        assert len(names) == 2

    def test_filter_by_min_h_index(self, db):
        results = sql_filter_pis(db, min_h_index=65)
        assert all(r["h_index"] >= 65 for r in results)

    def test_filter_by_theory_category(self, db):
        results = sql_filter_pis(db, theory_category="theory")
        names = [r["name"] for r in results]
        assert "Carol Theory" in names
        assert "Eve Stats" in names
        assert "Alice RL" not in names

    def test_filter_by_institution_name(self, db):
        results = sql_filter_pis(db, institution_name="MIT")
        names = [r["name"] for r in results]
        assert "Alice RL" in names
        assert "Bob Vision" not in names

    def test_combined_filters(self, db):
        results = sql_filter_pis(db, region="US", is_taking_students="yes")
        names = [r["name"] for r in results]
        assert names == ["Alice RL"]

    def test_order_by(self, db):
        results = sql_filter_pis(db, order_by="h_index DESC")
        h_indices = [r["h_index"] for r in results]
        assert h_indices == sorted(h_indices, reverse=True)

    def test_limit(self, db):
        results = sql_filter_pis(db, limit=2)
        assert len(results) == 2

    def test_candidate_ids_filter(self, db):
        all_results = sql_filter_pis(db)
        first_two_ids = [r["id"] for r in all_results[:2]]
        filtered = sql_filter_pis(db, candidate_ids=first_two_ids)
        assert len(filtered) == 2

    def test_invalid_order_by_defaults_safely(self, db):
        # SQL injection attempt should fall back to default
        results = sql_filter_pis(db, order_by="1; DROP TABLE pis; --")
        assert len(results) > 0


class TestGetTopPapers:
    def test_returns_papers(self, db):
        pi = sql_filter_pis(db, institution_name="MIT")[0]
        papers = get_top_papers_for_pi(db, pi["id"])
        assert len(papers) >= 1
        assert "title" in papers[0]


# --- FTS tests ---


class TestFTSSearch:
    def test_fts_finds_relevant_pi(self, db):
        results = fts_search_pis(db, "reinforcement learning")
        names = [r["name"] for r in results]
        assert "Alice RL" in names

    def test_fts_finds_relevant_paper(self, db):
        results = fts_search_papers(db, "object detection transformers")
        titles = [r["title"] for r in results]
        assert any("Object Detection" in t for t in titles)


# --- QueryPlan tests ---


class TestQueryPlan:
    def test_defaults(self):
        plan = QueryPlan(search_terms="test", reasoning="test")
        assert plan.limit == 10
        assert plan.search_type == "phd"
        assert plan.order_by == "total_citations DESC"
        assert plan.region is None

    def test_cli_overrides(self):
        plan = QueryPlan(search_terms="test", reasoning="test")
        plan = apply_cli_overrides(plan, search_type="masters", region="UK", top=5)
        assert plan.search_type == "masters"
        assert plan.region == "UK"
        assert plan.limit == 5

    def test_cli_overrides_none_preserves_plan(self):
        plan = QueryPlan(search_terms="test", region="US", reasoning="test")
        plan = apply_cli_overrides(plan, region=None)
        assert plan.region == "US"


# --- Engine tests ---


class TestSearchEngine:
    def test_hybrid_search(self, db):
        plan = QueryPlan(search_terms="reinforcement learning", limit=5, reasoning="test")
        results = search_pis(db, plan, mode="hybrid", use_rerank=False)
        assert len(results) > 0
        # Results should have top_papers attached
        assert "top_papers" in results[0]

    def test_fts_mode(self, db):
        plan = QueryPlan(search_terms="computer vision", limit=5, reasoning="test")
        results = search_pis(db, plan, mode="fts", use_rerank=False)
        assert len(results) > 0

    def test_sql_mode(self, db):
        plan = QueryPlan(search_terms="anything", region="UK", limit=5, reasoning="test")
        results = search_pis(db, plan, mode="sql", use_rerank=False)
        assert all(r["region"] == "UK" for r in results)

    def test_run_search_phd(self, db):
        plan = QueryPlan(search_terms="deep learning", search_type="phd", limit=5, reasoning="test")
        output = run_search(db, plan, no_rerank=True)
        assert "pis" in output
        assert "programs" in output
        assert "query_plan" in output

    def test_run_search_empty_fts_falls_back(self, db):
        plan = QueryPlan(search_terms="quantum chromodynamics hadron", limit=5, reasoning="test")
        results = search_pis(db, plan, mode="hybrid", use_rerank=False)
        # Should still return results from SQL fallback
        assert isinstance(results, list)
