# GRADRADAR — Master Build Plan

**Created:** 2026-04-06
**Status:** Not started

This document is the step-by-step implementation plan for gradradar. Each step is self-contained and produces a working, testable artifact before moving to the next. Do not skip ahead.

---

## Step 1 — Project Setup, Dependencies, and External Services

**Goal:** A working repo with all dependencies installed, API keys configured, R2 bucket created, and a CLI entry point that runs `gradradar --version` successfully.

### 1.1 Repository and Python environment

- [ ] Create `pyproject.toml` with project metadata and all dependencies:
  ```
  duckdb, httpx, playwright, pdfplumber, instructor, litellm,
  beautifulsoup4, readability-lxml, trafilatura, pydantic,
  boto3, click, rich, duckduckgo-search
  ```
- [ ] Create venv: `python3 -m venv venv && source venv/bin/activate`
- [ ] `pip install -e ".[dev]"` — confirm it installs cleanly
- [ ] `playwright install chromium`
- [ ] Create `.gitignore` (venv/, .env, __pycache__, *.pyc, .DS_Store, ~/.gradradar/)
- [ ] Create `.env.example` with all environment variable stubs
- [ ] Create `.env` locally (never committed) and populate with real keys

### 1.2 API keys and accounts

- [ ] **Anthropic API key** — sign up at console.anthropic.com, add to `.env` as `ANTHROPIC_API_KEY`
- [ ] **OpenAlex** — no key needed, but register a polite email at `mailto:` in the User-Agent header for bulk access
- [ ] **Semantic Scholar API key** — register at semanticscholar.org/product/api (free tier, 10 req/s). Add to `.env` as `SEMANTIC_SCHOLAR_KEY`. This is a backup source, not primary.

### 1.3 Cloudflare R2 setup

- [ ] Create a free Cloudflare account at dash.cloudflare.com
- [ ] Navigate to R2 → Create bucket (name: `gradradar-db`)
- [ ] Enable public access on the bucket (either custom domain or `*.r2.dev` subdomain)
- [ ] Generate an R2 API token with "Object Read & Write" permissions
- [ ] Add to `.env`:
  ```
  CLOUDFLARE_R2_ACCOUNT_ID=
  CLOUDFLARE_R2_ACCESS_KEY_ID=
  CLOUDFLARE_R2_SECRET_ACCESS_KEY=
  CLOUDFLARE_R2_BUCKET_NAME=gradradar-db
  CLOUDFLARE_R2_PUBLIC_URL=
  ```
- [ ] Test R2 connectivity: write a small script that uploads a test file via boto3 and reads it back via the public URL

### 1.4 Directory structure and CLI skeleton

- [ ] Create the full directory structure:
  ```
  gradradar/
  ├── __init__.py
  ├── cli.py
  ├── config.py
  ├── build/
  │   ├── __init__.py
  │   ├── pipeline.py
  │   ├── sources/
  │   │   ├── __init__.py
  │   │   ├── openalex.py
  │   │   ├── semantic_scholar.py
  │   │   ├── scraper.py
  │   │   └── workshops.py
  │   └── extractors/
  │       ├── __init__.py
  │       └── llm_extractor.py
  ├── db/
  │   ├── __init__.py
  │   ├── schema.py
  │   ├── writer.py
  │   └── downloader.py
  └── search/
      ├── __init__.py
      ├── engine.py
      ├── sql_search.py
      ├── fts_search.py
      ├── llm_query.py
      └── web_search.py
  ```
- [ ] Create `seeds/` directory with empty JSON files:
  ```
  seeds/institutions.json
  seeds/programs.json       (empty for now — Step 5)
  seeds/anchor_pis.json
  seeds/seed_papers.json
  seeds/workshops.json
  ```
- [ ] Create `tests/` directory with empty test files
- [ ] Implement `cli.py` with a minimal click CLI that responds to `gradradar --version`
- [ ] Verify: `gradradar --version` prints `0.1.0`

### 1.5 Config module

- [ ] Implement `config.py`:
  - Reads environment variables from `.env` (using `python-dotenv`)
  - Creates `~/.gradradar/` directory structure on first run:
    ```
    ~/.gradradar/
    ├── db/
    │   └── snapshots/
    └── cache/
        ├── raw_html/
        └── llm_responses/
    ```
  - Provides a `get_db_path()`, `get_cache_path()`, `get_profile_path()` etc.
- [ ] Verify: running `gradradar init` (stub) creates the directory structure

### Step 1 — Done when:
- `gradradar --version` works
- `.env` has all keys populated and tested
- R2 bucket exists and can be read/written
- `~/.gradradar/` directory structure is created
- All dependencies install cleanly

---

## Step 2 — Database Schema and Core Infrastructure

**Goal:** A complete DuckDB schema with all tables, FTS indexes, and the writer/reader infrastructure. No data yet — just the empty database with all constraints, plus the publish/download pipeline.

### 2.1 DuckDB schema

- [ ] Implement `db/schema.py` with a `create_schema(db_path)` function that creates all tables:
  ```
  institutions, departments, pis, pi_students, pi_industry_connections,
  pi_media, pi_research_trajectory, papers, author_paper, citations,
  topics, pi_topics, paper_topics, programs, program_courses,
  program_admissions_profile, workshops, pi_workshops, research_groups,
  department_culture, co_advising_relationships, possible_duplicates,
  scrape_log, web_searches, update_queue, schema_migrations
  ```
- [ ] All CHECK constraints, foreign keys, and defaults as specified in the PRD
- [ ] Add `CREATE TABLE schema_migrations` for tracking applied migrations
- [ ] Write a test: `test_schema.py` — creates the schema in a temp DuckDB, verifies all tables exist with correct column counts

### 2.2 FTS indexes

- [ ] Implement FTS index creation in `db/schema.py`:
  - Install and load the `fts` extension
  - Create `pi_search_docs` and `program_search_docs` views
  - Create FTS indexes on `papers`, `pi_search_docs`, `program_search_docs`
- [ ] Write a test: insert 5 fake PI records and 5 fake papers, create FTS indexes, verify a BM25 query returns results

### 2.3 Writer module

- [ ] Implement `db/writer.py` with functions:
  - `upsert_institution(db, record)` — insert or update by name + country
  - `upsert_pi(db, record)` — insert or update by openalex_id (primary) or name + institution (fallback)
  - `upsert_paper(db, record)` — insert or update by DOI or openalex_id
  - `upsert_program(db, record)` — insert or update by name + institution
  - `log_scrape(db, run_id, phase, records_added, ...)` — write to scrape_log
  - `queue_update(db, record_type, source_url, priority, reason)` — write to update_queue
- [ ] All upserts use parameterized SQL (no string concatenation)
- [ ] All upserts return the UUID of the inserted/updated record
- [ ] Write tests for each upsert function: insert, then update with changed fields, verify only changed fields are updated

### 2.4 Deduplication logic

- [ ] Implement name matching utility: Jaro-Winkler similarity using `jellyfish` library (add to dependencies)
- [ ] Implement dedup logic in writer:
  - Primary key: `openalex_id` (if available)
  - Fallback: name + institution fuzzy match (threshold 0.85)
  - Near-matches (0.75–0.95) logged to `possible_duplicates`
- [ ] Write tests: insert "Wei Zhang" at MIT twice — second insert should update, not create duplicate. Insert "Wei Zhang" at MIT and "Wei Zhang" at Stanford — should create two records. Insert "Wei Zang" at MIT — should log to possible_duplicates.

### 2.5 Publish and download pipeline

- [ ] Implement `gradradar db publish` in `cli.py`:
  - Compute SHA-256 of `gradradar.duckdb`
  - Auto-increment version from R2 `latest/manifest.json`
  - Upload `gradradar.duckdb` + `manifest.json` to R2 `[version]/`
  - Update `latest/manifest.json`
  - Print public URL
- [ ] Implement `gradradar init` in `cli.py`:
  - Fetch `latest/manifest.json` from R2
  - Download `gradradar.duckdb` with progress bar (rich)
  - Verify SHA-256 checksum
  - Write `manifest.json` locally
- [ ] Test round-trip: create schema → publish → delete local → init → verify tables exist

### 2.6 Database management commands

- [ ] Implement `gradradar db stats` — prints table row counts, database size, last build date, stale record counts
- [ ] Implement `gradradar db validate` — runs integrity checks (orphaned FKs, all-null records, FTS index health, duplicate IDs)

### Step 2 — Done when:
- `gradradar db stats` shows all tables with 0 rows
- `gradradar db validate` passes on the empty database
- `gradradar db publish` uploads to R2 and `gradradar init` downloads it back
- All writer tests pass
- FTS indexes are created and queryable (even if empty)

---

## Step 3 — OpenAlex Snapshot Ingestion (PhD Lab Discovery)

**Goal:** A populated database with ~3,000–5,000 PIs, ~40,000+ papers, citations, institutions, and departments — all from OpenAlex. FTS indexes built and searchable. No web scraping yet.

### 3.1 Curate seed data

- [ ] Populate `seeds/institutions.json` with ~100–150 target institutions:
  - US: top 50 CS/Math departments (MIT, Stanford, CMU, Berkeley, etc.)
  - UK: top 20 (Oxford, Cambridge, Imperial, UCL, Edinburgh, etc.)
  - Europe: top 30 (ETH Zurich, EPFL, Max Planck institutes, INRIA, TU Munich, etc.)
  - Include: name, country, region, city, type, OpenAlex institution ID (look up via OpenAlex API)
  - Include department URLs for faculty pages (needed later in Step 4 enrichment)
- [ ] Populate `seeds/anchor_pis.json` with ~15–20 anchor PIs and their OpenAlex author IDs
- [ ] Populate `seeds/seed_papers.json` with ~10–15 foundational papers and their OpenAlex work IDs
- [ ] Populate `seeds/workshops.json` with ~10 workshop URLs

### 3.2 OpenAlex snapshot download and filtering

- [ ] Implement `build/sources/openalex.py`:
  - `download_snapshot(entity_type, output_dir)` — downloads Parquet files from `s3://openalex/data/[entity]/` to a local cache directory using `httpx` or `boto3` (public, no auth)
  - `filter_authors(parquet_path, institution_ids) -> DataFrame` — reads author Parquet, filters to authors at target institutions with >=5 papers in CS/Math/Stats
  - `filter_works(parquet_path, author_ids) -> DataFrame` — reads works Parquet, filters to papers by target authors
  - `extract_citations(parquet_path, paper_ids) -> DataFrame` — reads citation edges where both papers are in scope
- [ ] DuckDB can read Parquet directly — use `read_parquet()` with predicate pushdown for efficient filtering
- [ ] Cache downloaded Parquet files in `~/.gradradar/cache/openalex_snapshot/`

### 3.3 Data loading pipeline

- [ ] Implement `build/pipeline.py` — `run_openalex_load(db_path, seeds_path)`:
  1. Read `seeds/institutions.json` → insert into `institutions` and `departments` tables
  2. Download/filter OpenAlex authors snapshot → insert into `pis` table:
     - Map OpenAlex fields to gradradar schema: `display_name` → `name`, `last_known_institution` → `institution_id`, `summary_stats.h_index` → `h_index`, `cited_by_count` → `total_citations`, etc.
     - Compute `career_stage` heuristic from years since first publication
     - Compute `citations_last_5_years` from `counts_by_year`
     - Compute `citation_velocity` and `citation_velocity_source`
     - Set `is_taking_students = 'unknown'`, `research_description = NULL` (populated later by scraping)
  3. Download/filter OpenAlex works snapshot → insert into `papers` table
  4. Build `author_paper` junction table from work authorship data
  5. Build `citations` table from citation edges
  6. Compute `theory_category` from venue distribution (venue-derived for PIs with >=5 papers)
  7. Populate `pi_topics` and `paper_topics` from OpenAlex concepts
  8. Build FTS indexes
  9. Log to `scrape_log`
- [ ] Add `--sample FLOAT` flag: processes only a fraction of institutions/authors for testing
- [ ] Add progress bars (rich) for each substep

### 3.4 Citation graph expansion

- [ ] After loading papers for target-institution PIs, expand via citation graph:
  - Forward: papers that cite seed papers (1 hop, capped at 5000 per seed paper)
  - Backward: papers cited by seed papers (1 hop)
  - For each discovered paper: if any author is at a target institution, add that author to `pis` if not already present
- [ ] This is a local SQL operation on already-loaded data — no API calls needed
- [ ] Best-first by seed-author overlap

### 3.5 Co-author expansion

- [ ] For each anchor PI, find all co-authors via `author_paper` joins
- [ ] Add co-authors at target institutions (or with h_index > 10) to `pis` if not present
- [ ] Log new discoveries to `scrape_log`

### 3.6 Populate topics table

- [ ] Create `seeds/topics.json` with the hierarchical topic taxonomy (seeded manually from OpenAlex concepts relevant to ML/CS/Math)
- [ ] Load into `topics` table
- [ ] Map OpenAlex concept IDs to topic IDs in `pi_topics` and `paper_topics`

### 3.7 CLI commands for build

- [ ] `gradradar build --full` — runs the full OpenAlex load pipeline
- [ ] `gradradar build --sample 0.1` — runs on 10% of data
- [ ] `gradradar build --resume` — reads checkpoint, continues from last item
- [ ] `gradradar coverage` — prints PI count per topic, flags thin coverage

### 3.8 Verify data quality

- [ ] Run `gradradar db stats` — expect ~3,000–5,000 PIs, ~40,000+ papers, ~100–150 institutions
- [ ] Run `gradradar db validate` — all checks pass
- [ ] Run `gradradar coverage` — verify expected topic distribution
- [ ] Manually spot-check 10 PIs: correct institution? correct h-index? correct paper count?
- [ ] Test FTS: query "topological data analysis" — do the right PIs come back?
- [ ] Test FTS: query "mechanistic interpretability" — do the right PIs come back?
- [ ] Test FTS: query "reinforcement learning" — verify thin but present coverage

### Step 3 — Done when:
- Database has ~3,000–5,000 PIs with citations, papers, topics
- `gradradar db stats` and `gradradar db validate` both pass
- FTS queries return reasonable results for known research areas
- `gradradar coverage` shows the expected topic distribution
- `gradradar db publish` successfully uploads the populated database to R2
- `gradradar init` on a fresh machine downloads and can query it

---

## Step 4 — Search Interface and Iteration

**Goal:** A fully functional search CLI that accepts natural-language queries, translates them to hybrid FTS + SQL, re-ranks with LLM, and displays formatted result cards. Iterate until search quality is good.

### 4.1 Profile system

- [ ] Implement `gradradar profile setup` — 5-field interactive wizard:
  1. Degree preference (PhD / Masters / both)
  2. Primary research interests (freeform)
  3. Geography priority (ordered list: US, UK, Europe)
  4. International student (yes / no / null)
  5. Funding requirement (required / strongly_preferred / nice_to_have)
- [ ] Writes to `~/.gradradar/profile.json`
- [ ] Implement `gradradar profile show`
- [ ] Implement `gradradar profile extend` (optional deeper fields — lower priority)

### 4.2 LLM query translation

- [ ] Implement `search/llm_query.py`:
  - Input: user query string + profile (if exists)
  - LLM system prompt: schema reference, filterable fields, profile context
  - LLM must expand natural language into effective FTS search terms (synonyms, related concepts)
  - Output: `QueryPlan` pydantic model with `mode`, `search_terms`, `fts_tables`, `sql_filters`, `output_format`, `top_k`
- [ ] Test with 10 queries from the PRD user stories — verify query plans look correct
- [ ] Iterate on the system prompt until query plans are consistently good

### 4.3 FTS search

- [ ] Implement `search/fts_search.py`:
  - `fts_search(search_terms, tables, n_results=100) -> List[SearchResult]`
  - Runs BM25 queries against specified FTS indexes
  - Returns merged, deduplicated results sorted by BM25 score
- [ ] Test: "topological data analysis" returns PIs who work on TDA
- [ ] Test: "neural network theory" returns theory-focused PIs

### 4.4 SQL search

- [ ] Implement `search/sql_search.py`:
  - `sql_search(table, filters, candidate_ids=None, order_by=None, limit=50) -> List[Dict]`
  - Parameterized SQL — no string concatenation
  - Filter translation: string → `=`, list → `IN`, dict with `$gte/$lte` → `>=`/`<=`
- [ ] Test: filter by region=UK, is_taking_students=yes

### 4.5 Hybrid search engine

- [ ] Implement `search/engine.py`:
  1. FTS pass → 100 candidate IDs
  2. SQL pass → filter candidates by sql_filters
  3. LLM re-ranking (temperature=0) → top 20 re-ranked with match explanations
  4. Cache re-ranking results (query_plan_hash + candidate_ids_hash, 24h TTL)
- [ ] Always print one-line plan summary before results
- [ ] Implement `--explain` and `--explain-only` flags

### 4.6 Output formatting

- [ ] Implement `phd_pi` result card format using rich:
  ```
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Prof. Jane Smith — MIT EECS
    Assistant Professor | Taking Students: UNKNOWN | Theory: theory
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    RESEARCH
    [research_description — or "Not yet scraped" if NULL]

    WHY THIS MATCHES
    [LLM-generated explanation]

    TOP RELEVANT PAPERS
    1. "Paper Title" (NeurIPS 2023) — 142 citations

    STATS
    h-index:              18
    Citations (5yr):      1,240
    Citation velocity:    0.73 (breadth)
    ...
  ```
- [ ] Implement `--json` flag for raw JSON output
- [ ] Note: many fields will show "Not yet scraped" or "unknown" at this stage — that's expected

### 4.7 Clarifying questions (opt-in)

- [ ] Implement session system for `--clarify` flag:
  - LLM selects at most 2 questions from candidate pool
  - Answers are compiled into `SessionContext` and merged with profile
  - Stored in `~/.gradradar/cache/last_session.json`
- [ ] Lower priority than getting basic search working — implement after 4.1–4.6 are solid

### 4.8 Web search layer

- [ ] Implement `search/web_search.py`:
  - Trigger conditions: named PI query, taking students query, thin results fallback, explicit --web
  - LLM constructs 2–4 targeted DuckDuckGo search strings
  - Parse results into WebResult objects
  - Quality gate: name + institution + resolvable URL required, max 10 per session
  - Write new discoveries to update_queue with status='pending_verification'
- [ ] Tag web results as `source: web` in output

### 4.9 Iterate on search quality

- [ ] Run all 10 PhD user stories from the PRD. For each:
  - Does the query plan make sense? (use --explain)
  - Are the right PIs in the top 10?
  - Are obviously wrong PIs excluded?
  - Are match explanations grounded in real papers?
- [ ] Identify failure modes and fix:
  - Bad FTS terms → improve LLM query translation prompt
  - Missing PIs → check if they're in the database at all (coverage issue vs. search issue)
  - Wrong ranking → improve re-ranking prompt
- [ ] Run `gradradar db publish` with the validated database

### Step 4 — Done when:
- `gradradar search "query"` returns formatted results for all PhD user stories
- `--explain` shows sensible query plans
- Re-ranking produces stable, relevant results
- Web search layer supplements thin results
- Profile personalization works
- Database is published to R2 and downloadable via `gradradar init`
- You've personally used it to explore labs and found it useful

---

## Step 5 — Masters Program Scraping and Enrichment

**Goal:** Add Masters program data via web scraping, and add PI page scraping for enrichment of fields that OpenAlex doesn't provide (is_taking_students, research_description, lab details, student lists).

### 5.1 Curate program seeds

- [ ] Populate `seeds/programs.json` with ~150–200 Masters programs:
  - US: top ML/CS/Math Masters programs (~60)
  - UK: top programs (~50) — include MSc, MRes, MPhil variants
  - Europe: top programs (~50) — ETH, EPFL, TU Munich, etc.
  - Each entry: name, institution, degree_type, URL
- [ ] Validate all URLs are reachable

### 5.2 Scraping infrastructure

- [ ] Implement `build/sources/scraper.py`:
  - `fetch_html(url)` — httpx primary fetch
  - `fetch_html_js(url)` — playwright fallback (if content < 500 chars visible text)
  - Per-domain rate limiter (3s minimum between requests)
  - robots.txt compliance via `urllib.robotparser`
  - Content caching to `~/.gradradar/cache/raw_html/[sha256].html` (24h TTL)
- [ ] Implement HTML preprocessing:
  - `readability-lxml` or `trafilatura` to extract main content
  - Strip nav, footer, sidebar, scripts, styles
  - Truncate to per-schema character limit

### 5.3 LLM extraction

- [ ] Implement `build/extractors/llm_extractor.py`:
  - `extract_program(html, schema) -> ProgramProfile`
  - `extract_pi_profile(html, schema) -> PIProfile`
  - `extract_faculty_list(html, schema) -> FacultyListResult`
  - Uses `instructor` + litellm with Pydantic validation
  - 3 retries on validation failure
  - Extraction confidence check: >50% null required fields → skip
  - LLM response caching keyed by (prompt_hash, model, content_hash)
- [ ] Build extraction regression test suite:
  - Save ~20 representative HTML pages to `tests/extraction_fixtures/`
  - `test_extraction.py` validates key fields are correctly extracted

### 5.4 Program scraping pipeline

- [ ] Implement program scraping in `build/pipeline.py`:
  - For each program in `seeds/programs.json`:
    1. Fetch program landing page
    2. Check for linked curriculum/courses and admissions pages — fetch those too
    3. Concatenate HTML (truncated to 30K chars), preprocess
    4. LLM extraction → ProgramProfile
    5. Write to `programs`, `program_courses`, `program_admissions_profile`
  - Checkpoint every 50 programs
  - Log to `scrape_log`
- [ ] Add `masters_program` output format to search results

### 5.5 PI page enrichment pipeline

- [ ] Implement PI enrichment in `build/pipeline.py`:
  - For each PI in the database with `research_description IS NULL` and `personal_url IS NOT NULL`:
    1. Fetch PI personal page (+ lab page if different)
    2. Preprocess HTML
    3. Extract structured fields without LLM first (email via regex, Google Scholar URL, lab name)
    4. LLM extraction for remaining fields (research_description, is_taking_students, theory_category fallback, students, industry connections)
    5. Write enriched record
  - Content hash comparison: skip if page unchanged
  - Checkpoint every 100 PIs
- [ ] This can run lazily (only enrich PIs that users search for) or as a batch job

### 5.6 Department faculty page scraping

- [ ] Implement department scraping:
  - For each department in `seeds/institutions.json` with a `faculty_url`:
    1. Fetch faculty listing page
    2. Try structured HTML parsing first (CSS selectors for common CMS templates)
    3. Fall back to LLM extraction only if structured parsing fails
    4. Cross-reference extracted names against existing PIs in database
    5. New PIs → create stub records, queue for enrichment
- [ ] This discovers PIs that OpenAlex might have missed (new hires, etc.)

### 5.7 Workshop scraping

- [ ] Implement workshop scraping in `build/sources/workshops.py`:
  - Fetch workshop pages (HTML or PDF)
  - Extract speaker names and affiliations
  - Cross-reference against existing PIs
  - New PIs → stub records + enrichment queue

### 5.8 Update and discover commands

- [ ] Implement `gradradar update`:
  - Query for stale records by TTL
  - Re-fetch source URLs, compare content hash
  - Re-extract only changed content
  - Rebuild FTS indexes at end
  - Snapshot before update
- [ ] Implement `gradradar discover`:
  - Run all discovery methods (workshops, citations, co-authors, placements, departments)
  - Deduplicate against existing records
  - Create stubs → queue for enrichment
  - Optionally trigger immediate enrichment

### 5.9 Search updates for Masters

- [ ] Add `masters_program` output format card
- [ ] Update `llm_query.py` to handle Masters-specific queries
- [ ] Update FTS to search `program_search_docs`
- [ ] Update `--type` flag: `phd`, `masters`, `both`
- [ ] Test all 7 Masters user stories from the PRD

### 5.10 Full validation

- [ ] Run all user stories (3.1.1–3.1.10, 3.2.1–3.2.7, 3.3.1–3.3.3) — verify all are answerable
- [ ] Run `gradradar db stats` — verify expected record counts
- [ ] Run `gradradar db validate` — all checks pass
- [ ] Run `gradradar coverage` — verify topic distribution
- [ ] Publish final database to R2
- [ ] Test `gradradar init` on a fresh machine → search works end-to-end

### Step 5 — Done when:
- All user stories from the PRD are answerable
- Masters program search works with formatted cards
- PI enrichment fills in is_taking_students, research_description for scraped PIs
- Update and discover commands work for ongoing maintenance
- Database is published and downloadable
- README and CONTRIBUTING.md are written

---

## Milestone Summary

| Step | What you get | Time estimate | Cost estimate |
|---|---|---|---|
| Step 1 | Working repo, all external services connected | 1 day | $0 |
| Step 2 | Empty database with full schema, publish/download works | 2–3 days | $0 |
| Step 3 | ~4000 PIs searchable via FTS, PhD discovery works | 2–3 days | <$1 |
| Step 4 | Full search CLI, iterated to good quality | 3–5 days | ~$5–10 (LLM calls during iteration) |
| Step 5 | Masters programs, PI enrichment, full PRD coverage | 5–7 days | ~$10–15 (scraping + extraction) |
| **Total** | **Complete gradradar v1.0** | **~2–3 weeks** | **~$15–25** |
