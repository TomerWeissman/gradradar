# GRADRADAR — Product Requirements Document

**Version:** 1.0
**Date:** 2026-04-06
**Status:** Final Draft

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Goals and Non-Goals](#2-goals-and-non-goals)
3. [User Stories](#3-user-stories)
4. [System Architecture](#4-system-architecture)
5. [Database Schema](#5-database-schema)
6. [Build Pipeline Specification](#6-build-pipeline-specification)
7. [Search Architecture](#7-search-architecture)
8. [CLI Specification](#8-cli-specification)
9. [Session Workflow and Clarifying-Question System](#9-session-workflow-and-clarifying-question-system)
10. [Cloudflare R2 Publishing and Versioning](#10-cloudflare-r2-publishing-and-versioning)
11. [Update and Refresh Mechanism](#11-update-and-refresh-mechanism)
12. [Dependencies and Setup Instructions](#12-dependencies-and-setup-instructions)
13. [Estimated Costs and Build Time](#13-estimated-costs-and-build-time)
14. [Known Limitations and Future Work](#14-known-limitations-and-future-work)

---

## 1. Executive Summary

### What It Is

**gradradar** is a two-phase Python tool for discovering and evaluating PhD labs and Masters programs in Machine Learning, Computer Science, and Mathematics. It builds an exhaustive, structured, and semantically searchable database of academic researchers and graduate programs at institutions in the US, UK, and Europe — and exposes that database through a natural-language query interface.

The project is split cleanly into two phases:

**Phase 1 — Build:** A long-running data pipeline that scrapes, ingests, and enriches records from multiple academic data sources (Semantic Scholar, OpenAlex, institution faculty pages, workshop speaker lists, and program pages). The pipeline runs once in 11–15 hours, writes to a local DuckDB database (single file, with built-in full-text search indexes), and publishes the result to Cloudflare R2 as a versioned dataset. The pipeline can also be re-run differentially to refresh stale records without a full rebuild.

**Phase 2 — Search:** A CLI and Cowork-compatible interface through which a user submits a natural-language query, which is translated into a hybrid SQL + full-text search against the local database and returns ranked, formatted results. Results are presented either as PhD lab profiles or Masters program profiles, each with a personalized match explanation grounded in the user's local interest profile.

### Who It Is For

gradradar is built for prospective graduate students — particularly those targeting research-focused programs in ML/CS/Math — who want to identify relevant PhD advisors and Masters programs without spending weeks manually combing through department pages, Google Scholar profiles, and program websites. It is particularly useful for students interested in research areas that cut across department boundaries (e.g., geometric deep learning, mechanistic interpretability, applied topology), where the most relevant faculty may not be easily discoverable through traditional department-browsing.

The tool is open-source and self-hostable. Any user can install the CLI, download the pre-built database from Cloudflare R2, configure their local interest profile, and begin searching immediately. Users with access to API keys can also run or update the database themselves.

---

## 2. Goals and Non-Goals

### Goals

- Build a comprehensive, structured database of PhD labs and Masters programs in ML/CS/Math at US, UK, and European research institutions, with sufficient depth to answer nuanced research-fit questions.
- Implement a multi-source, multi-method PI discovery pipeline that achieves exhaustive coverage of the target research space, including emerging researchers with low citation counts.
- Enable natural-language search via hybrid SQL + full-text search (BM25) + LLM re-ranking that returns ranked results with human-readable match explanations grounded in specific papers and courses.
- Support both PhD advisor discovery (with research fit, lab details, and application signals) and Masters program discovery (with curriculum fit, funding, and placement signals).
- Allow any user to use the search interface immediately after `pip install gradradar` + `gradradar init`, without running the build pipeline.
- Support differential database updates so the maintainer can keep the Cloudflare R2 bucket fresh without a full 14–18 hour rebuild each time.
- Publish the database to Cloudflare R2 with versioning and a manifest, and allow users to detect and pull updates.
- Support local user profiles that personalize match explanations at query time, without requiring any PII to be transmitted to a server.

### Non-Goals

- gradradar does **not** submit applications, draft emails, or manage deadlines. It is a research and discovery tool only.
- gradradar does **not** scrape or store student-identifying information (e.g., individual GRE scores, transcripts, personal statements).
- gradradar does **not** guarantee completeness. It makes a best-effort attempt at exhaustive coverage of the target research space, but faculty at obscure departments or researchers who publish under non-standard names may be missing.
- gradradar does **not** provide real-time data. The database is a periodic snapshot, not a live feed. Users should verify time-sensitive fields (application deadlines, is_taking_students) directly with the institution.
- gradradar does **not** index programs or faculty outside of ML, CS, Math, Statistics, ECE, CogSci, and Physics. Adjacent fields (biology, chemistry, economics) are out of scope.
- gradradar does **not** provide a web or mobile interface. The primary interface is the CLI and Cowork mode.
- gradradar does **not** rate or rank institutions or programs beyond the structured fields in the database (which include externally sourced rankings like QS and US News). It does not generate an overall "score."

---

## 3. User Stories

The following user stories cover the realistic range of queries a graduate applicant would make. Each story specifies the query input, the expected search mode, and the expected output format.

### 3.1 PhD Lab Discovery

**US-3.1.1 — Find labs by research topic**
> "I'm interested in topological data analysis applied to neural networks. Who should I work with?"

- Mode: Hybrid (FTS over research_description + papers, SQL filter on region and career_stage)
- Output: phd_pi format — ranked list of PIs with match explanation citing specific relevant papers
- Filters: none enforced, all regions

**US-3.1.2 — Find labs by topic and geography**
> "Who are the best mechanistic interpretability researchers in the UK taking students?"

- Mode: Hybrid
- Output: phd_pi format
- Filters: region=UK, is_taking_students=yes

**US-3.1.3 — Find labs by theoretical style**
> "I want a very math-heavy lab, ideally with connections to algebraic topology or category theory"

- Mode: Hybrid (FTS over research_description, papers, topics; SQL filter on theory_category if available)
- Output: phd_pi format with curriculum and research description emphasis

**US-3.1.4 — Find labs by PI career stage**
> "I want to work with an assistant professor who is building their lab — someone hungry and accessible"

- Mode: Hybrid with SQL filter career_stage=assistant_professor
- Output: phd_pi format

**US-3.1.5 — Find labs similar to a known paper**
> "Find me labs doing work like 'Towards Monosemanticity'"

- Mode: Hybrid (LLM extracts key terms from the paper title, FTS over papers + pis; SQL join on shared topics)
- Output: phd_pi format with explanation tying PI papers to the seed paper

**US-3.1.6 — Find labs by PI's academic lineage**
> "I want to work with someone who trained under Max Welling or in his research tradition"

- Mode: Hybrid (SQL join on advisor_id, FTS over research_description)
- Output: phd_pi format

**US-3.1.7 — Find highly cited emerging researchers**
> "Who are the rising stars in geometric deep learning — people gaining momentum in the last 2 years?"

- Mode: Hybrid (SQL order by citation_velocity, SQL filter citations_last_5_years > threshold)
- Output: phd_pi format with citation velocity stats

**US-3.1.8 — Find labs with industry connections**
> "I want a lab with strong industry connections so I can do internships at top AI labs"

- Mode: Hybrid (FTS on research_description + SQL join on pi_industry_connections)
- Output: phd_pi format with industry connection details

**US-3.1.9 — Find labs with good placement records**
> "Where do students from top geometric ML labs end up after their PhDs?"

- Mode: SQL query joining pis and pi_students on placement_type and placement_institution
- Output: phd_pi format with student placement section emphasized

**US-3.1.10 — Find labs with funding expiry signals**
> "Who has active NSF or DARPA grants that will need students soon?"

- Mode: Hybrid (SQL filter on funding_sources containing 'NSF' or 'DARPA', FTS on research_description)
- Output: phd_pi format

### 3.2 Masters Program Discovery

**US-3.2.1 — Find programs by topic area**
> "What are the best Masters programs for studying machine learning theory?"

- Mode: Hybrid (FTS over program courses, research descriptions; SQL filter on degree_type)
- Output: masters_program format

**US-3.2.2 — Find funded Masters programs**
> "Are there any funded Masters programs in the UK for ML?"

- Mode: SQL filter (region=UK, scholarships_available=true or percent_funded > 0)
- Output: masters_program format with funding fields emphasized

**US-3.2.3 — Find Masters programs as a PhD pipeline**
> "I want a Masters that will help me get into a strong PhD program afterward"

- Mode: Hybrid (SQL order by percent_to_phd, FTS on notable_phd_placements)
- Output: masters_program format with PhD placement emphasis

**US-3.2.4 — Find programs with thesis option**
> "I want a Masters with a research thesis, not just coursework"

- Mode: SQL filter (thesis_option=true)
- Output: masters_program format

**US-3.2.5 — Find programs by curriculum fit**
> "I want to take courses in differential geometry, algebraic topology, and neural network theory"

- Mode: Hybrid (FTS over program course names and descriptions; fallback SQL search on exact course names)
- Output: masters_program format with curriculum detail

**US-3.2.6 — Find programs for international students**
> "I'm an international student. Which programs are most likely to fund me?"

- Mode: SQL filter (international_funded=true)
- Output: masters_program format

**US-3.2.7 — Find programs with research access**
> "I want a Masters where I can do actual research with faculty, not just take classes"

- Mode: Hybrid (SQL filter ra_available=true or thesis_option=true, FTS on program description)
- Output: masters_program format

### 3.3 Cross-Type and Profile-Aware Queries

**US-3.3.1 — Compare PhD and Masters options**
> "Should I do a PhD directly or get a Masters first? What are my options in Europe for interpretability research?"

- Mode: Hybrid, both output types
- Output: mixed phd_pi and masters_program results, separated by type

**US-3.3.2 — Profile-aware matching**
> "Based on my profile, what are my best options?"

- Mode: Hybrid using phd_interests.primary_topics and phd_interests.style_preference from profile.json
- Output: ranked mix of phd_pi and masters_program results with match explanation referencing profile fields

**US-3.3.3 — GRE-constrained search**
> "I don't want to take the GRE. What programs still accept me?"

- Mode: SQL filter (gre_required='no' OR gre_required='optional')
- Output: masters_program format (and phd_pi format noting departments with optional GRE)

---

## 4. System Architecture

### 4.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        gradradar                                │
│                                                                 │
│  ┌──────────────┐    ┌────────────────────────────────────────┐ │
│  │  BUILD PATH  │    │             SEARCH PATH                │ │
│  │              │    │                                        │ │
│  │  seeds/      │    │  gradradar search "natural language"   │ │
│  │  (JSON)      │    │          │                             │ │
│  │      │       │    │          ▼                             │ │
│  │      ▼       │    │   llm_query.py                         │ │
│  │  pipeline.py │    │   (LLM → structured query plan)        │ │
│  │      │       │    │          │                             │ │
│  │      ├───────┼────┼──►  engine.py (hybrid orchestration)   │ │
│  │      │       │    │  ┌──────────┴──────────────────┐       │ │
│  │  sources/    │    │  ▼ DB search                   ▼       │ │
│  │  ├ semantic  │    │  sql_search.py          web_search.py  │ │
│  │  ├ openalex  │    │  fts_search.py          (conditional)  │ │
│  │  ├ scraper   │    │  (DuckDB + FTS)               │        │ │
│  │  └ workshops │    │        └──────────┬───────────┘        │ │
│  │      │       │    │                   ▼                    │ │
│  │  extractors/ │    │   Merge + dedup (DB + web results)     │ │
│  │  └ llm_extr  │    │   New records → update_queue           │ │
│  │      │       │    │                   ▼                    │ │
│  │      ▼       │    │   Output formatter                     │ │
│  │  db/writer.py│    │   (phd_pi / masters_program)           │ │
│  │      │       │    │   source-tagged: db | web              │ │
│  │      ▼       │    │                   ▼                    │ │
│  │  ┌──────────┐│    │   rich terminal output                 │ │
│  │  │  DuckDB  ││    │                                        │ │
│  │  │  .db     ││    └────────────────────────────────────────┘ │
│  │  │  + FTS   ││                                               │
│  │  └──────────┘│                                               │
│  │      │       │                                               │
│  │      ▼       │                                               │
│  │  db/publisher.py → Cloudflare R2 bucket                       │
│  └──────────────────────────────────────────────────────────────┘
│                                                                  │
│  ~/.gradradar/                                                   │
│  ├── profile.json                                                │
│  ├── db/                                                         │
│  │   ├── gradradar.duckdb (includes FTS indexes)                 │
│  │   └── snapshots/                                              │
│  └── cache/                                                      │
│      └── raw_html/                                               │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Repository Structure

```
gradradar/
├── README.md
├── LICENSE                         # CC BY 4.0
├── pyproject.toml                  # installable via pip install gradradar
├── .env.example                    # SEMANTIC_SCHOLAR_KEY, OPENAI_KEY or ANTHROPIC_KEY, CLOUDFLARE_R2_KEYS
│
├── gradradar/
│   ├── __init__.py
│   ├── cli.py                      # entry point for all CLI commands
│   ├── config.py                   # manages ~/.gradradar/ local profile
│   │
│   ├── build/
│   │   ├── pipeline.py             # orchestrates full and differential builds
│   │   ├── sources/
│   │   │   ├── semantic_scholar.py # Semantic Scholar API ingestion
│   │   │   ├── openalex.py         # OpenAlex API ingestion
│   │   │   ├── scraper.py          # httpx + playwright HTML fetching
│   │   │   └── workshops.py        # workshop speaker list scraping
│   │   └── extractors/
│   │       └── llm_extractor.py    # instructor + LLM structured extraction from HTML
│   │
│   ├── db/
│   │   ├── schema.py               # DuckDB schema definitions, FTS indexes, and migrations
│   │   ├── writer.py               # insert and update logic
│   │   └── downloader.py           # pulls database from Cloudflare R2 on first run
│   │
│   └── search/
│       ├── engine.py               # hybrid search orchestration (DB + web merge)
│       ├── sql_search.py           # structured SQL query execution
│       ├── fts_search.py           # DuckDB full-text search (BM25 ranking)
│       ├── llm_query.py            # natural language to query translation
│       └── web_search.py           # conditional web search + DB feedback loop
│
├── seeds/
│   ├── institutions.json           # curated list of target institutions with department URLs
│   ├── programs.json               # curated masters programs seed list
│   ├── anchor_pis.json             # anchor PI names for citation graph seeding
│   ├── seed_papers.json            # foundational papers for citation traversal
│   └── workshops.json              # workshop URLs to scrape for PI discovery
│
├── docs/
│   ├── build.md
│   ├── search.md
│   └── schema.md
│
├── CONTRIBUTING.md                  # build/publish process, seed contribution guide
│
└── tests/
    ├── test_search.py
    ├── test_build.py
    ├── test_extraction.py           # regression tests against HTML fixtures
    └── extraction_fixtures/         # ~20 representative HTML pages for extraction testing
        ├── react_spa_faculty.html
        ├── wordpress_lab_page.html
        ├── static_html_faculty.html
        └── ...
```

### 4.3 Data Flow — Build Path

```
seeds/*.json
     │
     ▼
pipeline.py
  Phase 1: semantic_scholar.py ─────► papers, author_paper, citations, pis (partial)
  Phase 2: openalex.py ──────────────► institutions, departments, pis (enrichment)
  Phase 3: scraper.py (dept pages) ──► pis (names, URLs)
  Phase 4: scraper.py (PI pages) ────► pis (full profile), pi_students, pi_industry_connections
  Phase 5: scraper.py (programs) ────► programs, program_courses, program_admissions_profile
  Phase 6: workshops.py ─────────────► workshops, pi_workshops
  Phase 7: FTS index creation ────────► DuckDB full-text search indexes (papers, pis, programs)
     │
     └─► db/writer.py ──► DuckDB (gradradar.duckdb, single file with FTS indexes)
```

### 4.4 Data Flow — Search Path

```
User: gradradar search "query text" [--web | --no-web]
          │
          ▼
     llm_query.py
     (LLM receives: query text + full schema docs + user profile)
     (LLM returns: structured QueryPlan + WebSearchPlan JSON)
          │
          ├──────────────────────────────────────────────┐
          ▼                                              ▼
     engine.py (DB path)                      web_search.py
     ┌───────────────────────────┐            (conditional on
     │  mode = "hybrid" (default)│             WebSearchPlan.should_search
     │                           │             or --web flag)
     │  1. fts_search.py:        │             │
     │     DuckDB FTS query      │             ▼
     │     (BM25 ranking)        │      LLM constructs 2-4
     │     → candidate_ids[]     │      targeted search strings
     │                           │             │
     │  2. sql_search.py:        │             ▼
     │     WHERE id IN candidates│      Web search API calls
     │     AND [sql_filters]     │             │
     │     → filtered_results[]  │             ▼
     │                           │      LLM parses results
     │  3. LLM re-ranks top 20   │      → WebResult objects
     │     + match explanations  │             │
     └───────────────────────────┘             │
          │                                    │
          └─────────────────┬──────────────────┘
                            ▼
               Merge + deduplicate results
               (tag each result: source=db | source=web)
                            │
                            ▼
               New web results → update_queue
               (reason: discovered_via_web_search)
                            │
                            ▼
               LLM unified re-rank + explanations
                            │
                            ▼
               Output formatter (rich)
               → phd_pi or masters_program card per result
               → source badge on each card
```

### 4.5 Local Storage Layout

All user-local data lives under `~/.gradradar/`:

```
~/.gradradar/
├── profile.json                    # user interest profile (never committed to repo)
├── db/
│   ├── gradradar.duckdb            # relational database + FTS indexes (single file)
│   └── snapshots/                  # pre-update snapshots
│       ├── gradradar_2026-04-01.duckdb
│       └── ...
├── cache/
│   ├── raw_html/                   # content-addressed HTML cache
│   │   ├── [content_hash].html
│   │   └── ...
│   ├── llm_responses/              # cached LLM extraction responses keyed by (prompt_hash, model, content_hash)
│   ├── checkpoint.json             # within-phase build checkpoint for --resume
│   └── last_session.json           # last search session context (for --session-file reuse)
```

---

## 5. Database Schema

The database is a single DuckDB file (`gradradar.duckdb`) containing all relational data and full-text search indexes. There is no separate vector database.

**Full-text search** is provided by DuckDB's built-in `fts` extension, which creates inverted indexes with BM25 ranking. FTS indexes are created on text fields used for semantic matching (research descriptions, paper titles/abstracts, course names). This replaces the need for a separate embedding/vector database while keeping the entire database in a single portable file.

### 5.1 institutions

Stores one record per university, research institute, or industry lab.

```sql
CREATE TABLE institutions (
    id                  UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    country             TEXT,
    region              TEXT CHECK (region IN ('US', 'UK', 'Europe')),
    city                TEXT,
    type                TEXT CHECK (type IN ('university', 'research_institute', 'industry_lab')),
    qs_cs_ranking       INTEGER,
    us_news_ranking     INTEGER,
    shanghai_ranking    INTEGER,
    prestige_tier       INTEGER CHECK (prestige_tier IN (1, 2, 3)),
    url                 TEXT,
    scraped_at          TIMESTAMP,
    content_hash        TEXT,
    source_url          TEXT
);
```

**Field notes:**
- `prestige_tier` is derived from ranking data: tier 1 = top 20 globally, tier 2 = top 100, tier 3 = all others in scope.
- `type` distinguishes universities (degree-granting) from research institutes (e.g., MPI, INRIA) and industry labs (e.g., DeepMind, MSR).
- `content_hash` is the SHA-256 of the scraped source page content, used for differential update detection.
- `source_url` is the specific URL that was scraped to populate this record.

### 5.2 departments

One record per academic department within an institution.

```sql
CREATE TABLE departments (
    id                      UUID PRIMARY KEY,
    institution_id          UUID REFERENCES institutions(id),
    name                    TEXT NOT NULL,
    field                   TEXT CHECK (field IN ('CS', 'Math', 'Statistics', 'ECE', 'CogSci', 'Physics', 'Other')),
    phd_cohort_size         INTEGER,
    phd_acceptance_rate     FLOAT,
    phd_funding_guarantee   BOOLEAN,
    phd_funding_years       INTEGER,
    phd_average_stipend     INTEGER,
    admission_type          TEXT CHECK (admission_type IN ('rotation', 'direct', 'both')),
    application_deadline    TEXT,
    gre_required            TEXT CHECK (gre_required IN ('yes', 'no', 'optional')),
    english_proficiency     TEXT,
    url                     TEXT,
    scraped_at              TIMESTAMP,
    content_hash            TEXT,
    source_url              TEXT
);
```

**Field notes:**
- `admission_type` distinguishes rotation-based programs (student rotates through labs before choosing an advisor) from direct-admit (student is matched to an advisor at admission).
- `phd_average_stipend` is stored as USD integer regardless of country; non-USD stipends are converted at time of scraping.
- `english_proficiency` stores freeform text (e.g., "TOEFL 100 or IELTS 7.0") extracted from the department page.

### 5.3 pis

Central table for principal investigators, faculty, and researchers. This is the most data-rich and most frequently updated table.

```sql
CREATE TABLE pis (
    id                          UUID PRIMARY KEY,
    name                        TEXT NOT NULL,
    department_id               UUID REFERENCES departments(id),
    institution_id              UUID REFERENCES institutions(id),
    personal_url                TEXT,
    lab_url                     TEXT,
    google_scholar_url          TEXT,
    semantic_scholar_id         TEXT,
    openalex_id                 TEXT,
    email                       TEXT,
    career_stage                TEXT CHECK (career_stage IN (
                                    'assistant_professor', 'associate_professor',
                                    'full_professor', 'postdoc',
                                    'industry_researcher', 'research_scientist')),
    phd_year                    INTEGER,
    phd_institution             TEXT,
    advisor_id                  UUID REFERENCES pis(id),
    year_started_position       INTEGER,
    h_index                     INTEGER,
    total_citations             INTEGER,
    citations_last_5_years      INTEGER,
    citation_velocity           FLOAT,
    citation_velocity_source    TEXT CHECK (citation_velocity_source IN ('breadth', 'depth', 'mixed')),
    paper_count                 INTEGER,
    paper_count_last_3_years    INTEGER,
    is_taking_students          TEXT CHECK (is_taking_students IN ('yes', 'no', 'unknown')) DEFAULT 'unknown',
    taking_students_confidence  FLOAT CHECK (taking_students_confidence BETWEEN 0.0 AND 1.0),
    taking_students_checked_at  TIMESTAMP,
    current_student_count       INTEGER,
    funding_sources             TEXT,
    funding_expiry              TEXT,
    lab_name                    TEXT,
    research_description        TEXT,
    theory_category             TEXT CHECK (theory_category IN ('theory', 'applied', 'mixed', 'unknown')) DEFAULT 'unknown',
    theory_category_source      TEXT CHECK (theory_category_source IN ('venue_derived', 'llm_assigned')),
    scraped_at                  TIMESTAMP,
    content_hash                TEXT,
    source_url                  TEXT
);
```

**Field notes:**
- `advisor_id` is a self-referential FK for academic lineage tracing. NULL if not in database.
- `citation_velocity` is computed as: `(citations_last_2_years / total_citations) / (current_year - phd_year + 1)`, normalized to a 0–1 scale. Self-citations are excluded: if any author on the citing paper overlaps with the cited paper's authors, that citation is skipped. If a single paper accounts for >60% of a PI's recent citations, the velocity is flagged as `depth` rather than `breadth` to distinguish viral one-offs from broad momentum.
- `citation_velocity_source` categorizes the shape of the PI's recent citation activity: `breadth` (many papers gaining citations), `depth` (one paper carrying the number), or `mixed`.
- `theory_category` is a categorical label reflecting the theoretical vs. empirical nature of the PI's research. It is derived deterministically from venue distribution when the PI has ≥5 papers in the database: PIs who publish predominantly at theory venues (COLT, ALT, STOC, FOCS, SODA) are labeled `theory`; PIs who publish predominantly at empirical venues are labeled `applied`; otherwise `mixed`. For PIs with <5 papers, the LLM assigns the label during extraction as a fallback. `theory_category_source` records which method was used (`venue_derived` or `llm_assigned`).
- `is_taking_students` is extracted from the PI's personal or lab page. Default is `'unknown'`. The LLM must never infer `'no'` from the absence of information — only an explicit statement on the page (e.g., "I am not currently accepting students") should produce `'no'`. TTL is 30 days.
- `taking_students_confidence` is a 0.0–1.0 float reflecting the extraction confidence. 1.0 = explicit statement found on page; 0.5 = inferred from indirect signals (e.g., recent job posting); 0.0 = no signal found (defaults to `'unknown'`).
- `taking_students_checked_at` records the timestamp of the last check for this specific field, independent of `scraped_at`. This is displayed in the output as "as of [date]".
- `funding_sources` and `funding_expiry` are freeform text extracted from lab pages and OpenAlex grant data.
- `research_description` stores the combined text used for full-text search: lab page text + OpenAlex abstract summary. This field is indexed by the DuckDB FTS extension.

### 5.4 pi_students

Tracks PhD students (current and alumni) for each PI, used for placement tracing.

```sql
CREATE TABLE pi_students (
    id                      UUID PRIMARY KEY,
    pi_id                   UUID REFERENCES pis(id),
    student_name            TEXT NOT NULL,
    status                  TEXT CHECK (status IN ('current', 'alumni')),
    phd_start_year          INTEGER,
    phd_end_year            INTEGER,
    placement_type          TEXT CHECK (placement_type IN ('faculty', 'industry', 'postdoc', 'unknown')),
    placement_institution   TEXT,
    placement_company       TEXT,
    scraped_at              TIMESTAMP,
    source_url              TEXT
);
```

**Field notes:**
- `placement_type` is extracted from the PI's lab page student/alumni section, then normalized by LLM.
- `placement_institution` is populated for faculty and postdoc placements; `placement_company` for industry placements. Both may be NULL.

### 5.5 pi_industry_connections

Records documented connections between a PI and an industry organization.

```sql
CREATE TABLE pi_industry_connections (
    id                  UUID PRIMARY KEY,
    pi_id               UUID REFERENCES pis(id),
    organization        TEXT,
    connection_type     TEXT CHECK (connection_type IN (
                            'joint_paper', 'grant',
                            'internship_pipeline', 'advisory')),
    details             TEXT,
    year                INTEGER
);
```

**Field notes:**
- `joint_paper` connections are derived automatically by joining pis with papers and checking author affiliations for industry organizations.
- `internship_pipeline` and `advisory` connections are extracted from lab pages and bios.

### 5.6 pi_media

Stores media appearances and content created by a PI that may signal research direction or mentorship style.

```sql
CREATE TABLE pi_media (
    id                  UUID PRIMARY KEY,
    pi_id               UUID REFERENCES pis(id),
    media_type          TEXT CHECK (media_type IN (
                            'talk', 'blog_post', 'interview',
                            'twitter_thread', 'application_advice')),
    title               TEXT,
    url                 TEXT,
    date                DATE,
    content_summary     TEXT,
    raw_content         TEXT,
    scraped_at          TIMESTAMP
);
```

**Field notes:**
- `application_advice` media type is specifically tagged when a PI publishes advice about how to apply to their lab or what they look for in students. This is high-value signal for applicants.
- `content_summary` is a 2–3 sentence LLM-generated summary of the media content.
- `raw_content` stores the raw extracted text (truncated to 10,000 characters) for later re-summarization or analysis.

### 5.7 pi_research_trajectory

Stores per-PI research topic evolution over time, bucketed by year. Used to detect shifting focus areas.

```sql
CREATE TABLE pi_research_trajectory (
    id              UUID PRIMARY KEY,
    pi_id           UUID REFERENCES pis(id),
    year_bucket     INTEGER,
    topic           TEXT,
    paper_count     INTEGER,
    citation_count  INTEGER
);
```

**Field notes:**
- One record per (pi_id, year_bucket, topic) triple.
- `topic` is a string normalized to the canonical topic names in the `topics` table.
- `year_bucket` is a 2-year window (e.g., 2022 represents 2022–2023).

### 5.8 papers

Stores paper metadata. Not every paper in the world — only papers authored by PIs in the database or seed papers used for citation traversal.

```sql
CREATE TABLE papers (
    id                          UUID PRIMARY KEY,
    title                       TEXT NOT NULL,
    abstract                    TEXT,
    year                        INTEGER,
    venue                       TEXT,
    citation_count              INTEGER,
    citation_count_last_2_years INTEGER,
    citation_velocity           FLOAT,
    doi                         TEXT,
    arxiv_id                    TEXT,
    semantic_scholar_id         TEXT,
    fields_of_study             TEXT,
    url                         TEXT
);
```

**Field notes:**
- `fields_of_study` is a JSON-encoded list of field strings as returned by Semantic Scholar.
- `citation_velocity` at the paper level is computed as `citation_count_last_2_years / max(year_age, 1)` where year_age is the number of years since publication.
- `venue` stores the canonical venue name (e.g., "NeurIPS 2023", "ICLR 2024", "arXiv").

### 5.9 author_paper

Junction table linking PIs to their papers.

```sql
CREATE TABLE author_paper (
    id                  UUID PRIMARY KEY,
    author_id           UUID REFERENCES pis(id),
    paper_id            UUID REFERENCES papers(id),
    author_position     TEXT CHECK (author_position IN ('first', 'last', 'middle')),
    is_corresponding    BOOLEAN
);
```

**Field notes:**
- `author_position` is derived from the author ordering in the Semantic Scholar response.
- `is_corresponding` is extracted where available; defaults to NULL.

### 5.10 citations

Paper-to-paper citation graph. Stored as directed edges.

```sql
CREATE TABLE citations (
    citing_paper_id     UUID REFERENCES papers(id),
    cited_paper_id      UUID REFERENCES papers(id),
    PRIMARY KEY (citing_paper_id, cited_paper_id)
);
```

**Field notes:**
- Only edges where both papers are in the `papers` table are stored.
- Population is bounded: the pipeline does not attempt to store the full citation graph of all papers. Only citations where the citing or cited paper has an author in `pis` are included.

### 5.11 topics

Hierarchical topic taxonomy. Topics are seeded manually and extended by LLM during extraction.

```sql
CREATE TABLE topics (
    id                  UUID PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    parent_id           UUID REFERENCES topics(id),
    description         TEXT,
    canonical_paper_ids TEXT
);
```

**Field notes:**
- `parent_id` supports a two-level hierarchy (e.g., parent: "Geometric Deep Learning", child: "Equivariant Neural Networks").
- `canonical_paper_ids` is a JSON-encoded list of paper IDs that define or exemplify the topic. Used for semantic search seeding.
- Topics are seeded manually in `seeds/` and are not dynamically generated by the build pipeline. New topics can be added via PR.

### 5.12 pi_topics

Association between PIs and research topics, with confidence scoring.

```sql
CREATE TABLE pi_topics (
    pi_id               UUID REFERENCES pis(id),
    topic_id            UUID REFERENCES topics(id),
    confidence_score    FLOAT,
    evidence_paper_ids  TEXT,
    PRIMARY KEY (pi_id, topic_id)
);
```

**Field notes:**
- `confidence_score` is a 0.0–1.0 float generated by the LLM during extraction, reflecting how strongly the PI's body of work is associated with the topic.
- `evidence_paper_ids` is a JSON-encoded list of up to 5 paper IDs that most strongly support the topic assignment.

### 5.13 paper_topics

Association between papers and research topics.

```sql
CREATE TABLE paper_topics (
    paper_id            UUID REFERENCES papers(id),
    topic_id            UUID REFERENCES topics(id),
    confidence_score    FLOAT,
    PRIMARY KEY (paper_id, topic_id)
);
```

### 5.14 programs

Masters program records. One record per degree program.

```sql
CREATE TABLE programs (
    id                          UUID PRIMARY KEY,
    name                        TEXT NOT NULL,
    institution_id              UUID REFERENCES institutions(id),
    department_id               UUID REFERENCES departments(id),
    degree_type                 TEXT CHECK (degree_type IN ('MSc', 'MS', 'MPhil', 'MEng', 'MRes', 'MA')),
    url                         TEXT,
    application_deadline        TEXT,
    gre_required                TEXT CHECK (gre_required IN ('yes', 'no', 'optional')),
    toefl_minimum               INTEGER,
    ielts_minimum               FLOAT,
    letters_of_rec_count        INTEGER,
    sop_required                BOOLEAN,
    gpa_minimum                 FLOAT,
    duration_months             INTEGER,
    full_time_only              BOOLEAN,
    thesis_option               BOOLEAN,
    tuition_total               INTEGER,
    tuition_currency            TEXT,
    scholarships_available      BOOLEAN,
    percent_funded              FLOAT,
    average_funding_amount      INTEGER,
    ta_available                BOOLEAN,
    ra_available                BOOLEAN,
    international_funded        BOOLEAN,
    percent_to_phd              FLOAT,
    notable_phd_placements      TEXT,
    industry_placements         TEXT,
    theory_intensity            FLOAT,
    last_verified               DATE,
    scraped_at                  TIMESTAMP,
    content_hash                TEXT,
    source_url                  TEXT
);
```

**Field notes:**
- `tuition_total` is stored in the currency specified by `tuition_currency` (ISO 4217 code). No automatic conversion is performed.
- `percent_funded` is a 0.0–1.0 float (e.g., 0.30 = 30% of students receive funding).
- `theory_intensity` is a 0.0–1.0 float extracted by LLM from the program description and course list. 1.0 = highly theoretical program.
- `notable_phd_placements` and `industry_placements` are freeform text extracted from the program page.
- `last_verified` is manually set when a human verifies the data; `scraped_at` is automatically set by the pipeline.

### 5.15 program_courses

Individual course records within a Masters program.

```sql
CREATE TABLE program_courses (
    id                  UUID PRIMARY KEY,
    program_id          UUID REFERENCES programs(id),
    course_name         TEXT NOT NULL,
    course_description  TEXT,
    is_required         BOOLEAN,
    topic_tags          TEXT
);
```

**Field notes:**
- `topic_tags` is a JSON-encoded list of topic names from the `topics` table, assigned by the LLM during extraction.
- `is_required` indicates whether the course is required for the degree (vs. elective).

### 5.16 program_admissions_profile

Admissions statistics for Masters programs.

```sql
CREATE TABLE program_admissions_profile (
    id                              UUID PRIMARY KEY,
    program_id                      UUID REFERENCES programs(id),
    typical_gpa_low                 FLOAT,
    typical_gpa_high                FLOAT,
    publications_expected           BOOLEAN,
    research_experience_required    BOOLEAN,
    avg_gre_quant                   INTEGER,
    avg_gre_verbal                  INTEGER,
    international_admission_rate    FLOAT,
    notes                           TEXT
);
```

**Field notes:**
- `typical_gpa_low` and `typical_gpa_high` represent the middle 50% GPA range of admitted students, when available.
- `publications_expected` and `research_experience_required` are extracted from admissions pages and FAQs.
- `notes` is freeform text capturing any admissions nuances not captured by structured fields.

### 5.17 workshops

Academic workshop records used as PI discovery sources.

```sql
CREATE TABLE workshops (
    id                  UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    parent_conference   TEXT,
    year                INTEGER,
    url                 TEXT,
    topic_focus         TEXT,
    scraped_at          TIMESTAMP
);
```

### 5.18 pi_workshops

Junction table linking PIs to workshops they participated in.

```sql
CREATE TABLE pi_workshops (
    pi_id           UUID REFERENCES pis(id),
    workshop_id     UUID REFERENCES workshops(id),
    role            TEXT CHECK (role IN ('speaker', 'organizer', 'panelist')),
    PRIMARY KEY (pi_id, workshop_id)
);
```

### 5.19 research_groups

Records formal research groups or centers that span multiple PIs.

```sql
CREATE TABLE research_groups (
    id                  UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    institution_id      UUID REFERENCES institutions(id),
    member_pi_ids       TEXT,
    lab_url             TEXT,
    research_focus      TEXT,
    funding_source      TEXT
);
```

**Field notes:**
- `member_pi_ids` is a JSON-encoded list of PI UUIDs.

### 5.20 department_culture

Captures qualitative and quantitative signals about departmental research culture.

```sql
CREATE TABLE department_culture (
    id                              UUID PRIMARY KEY,
    department_id                   UUID REFERENCES departments(id),
    theory_score                    FLOAT,
    empirical_score                 FLOAT,
    math_faculty_ratio              FLOAT,
    top_theory_venue_papers         INTEGER,
    cross_dept_connections          TEXT,
    seminar_series                  TEXT,
    visiting_researcher_program     BOOLEAN,
    notes                           TEXT
);
```

**Field notes:**
- `theory_score` and `empirical_score` are computed from the aggregate `theory_category` distribution of PIs in the department (proportion of PIs labeled `theory` vs `applied`).
- `math_faculty_ratio` is the fraction of department faculty with primary appointment in Math or Statistics.
- `top_theory_venue_papers` is a count of papers published at venues like STOC, COLT, ALT, FOCS by department faculty.
- `cross_dept_connections` is a JSON-encoded list of department names at the same institution with which this department has documented collaboration.

### 5.21 co_advising_relationships

Records documented co-advising arrangements between two PIs.

```sql
CREATE TABLE co_advising_relationships (
    pi_id_1         UUID REFERENCES pis(id),
    pi_id_2         UUID REFERENCES pis(id),
    student_name    TEXT,
    year            INTEGER,
    PRIMARY KEY (pi_id_1, pi_id_2, student_name)
);
```

### 5.22 possible_duplicates

Logs near-match records that may be duplicates but fall below the automatic merge threshold. Surfaced in `gradradar db stats` for human review.

```sql
CREATE TABLE possible_duplicates (
    id              UUID PRIMARY KEY,
    record_type     TEXT NOT NULL,
    record_id_1     UUID NOT NULL,
    record_id_2     UUID NOT NULL,
    name_1          TEXT,
    name_2          TEXT,
    institution_1   TEXT,
    institution_2   TEXT,
    similarity_score FLOAT,
    detection_method TEXT CHECK (detection_method IN ('name_match', 'api_id_conflict', 'co_author_overlap')),
    status          TEXT CHECK (status IN ('pending', 'merged', 'distinct', 'ignored')) DEFAULT 'pending',
    reviewed_at     TIMESTAMP,
    UNIQUE (record_id_1, record_id_2)
);
```

**Field notes:**
- Records with Jaro-Winkler similarity between 0.75 and 0.95 are logged here automatically during build and discover phases.
- `detection_method` records how the potential duplicate was found: `name_match` (name similarity), `api_id_conflict` (different records resolved to the same Semantic Scholar or OpenAlex ID), or `co_author_overlap` (two PI records share >80% of co-authors).
- `status='merged'` indicates the records were confirmed as duplicates and merged. `status='distinct'` means they were confirmed as different people. Both prevent re-flagging.
- Deduplication uses Semantic Scholar and OpenAlex author IDs as the primary dedup key when available. Name-based matching is a fallback only for PIs discovered via scraping without API-sourced IDs. Name matching uses a composite key: name + institution + research area overlap.

### 5.24 scrape_log

Audit log of all build, update, discover, and publish pipeline runs.

```sql
CREATE TABLE scrape_log (
    id              UUID PRIMARY KEY,
    run_id          TEXT,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    records_added   INTEGER,
    records_updated INTEGER,
    records_failed  INTEGER,
    phase           TEXT,   -- 'build_phase_1' through 'build_phase_7', 'update', 'discover', 'publish'
    command         TEXT,   -- 'build', 'update', 'discover', or 'publish'
    notes           TEXT
);
```

**`phase` field values by command:**
- `gradradar build --full`: phases written as `build_phase_1` through `build_phase_7`, plus a final `build_complete` entry.
- `gradradar build --phase N`: a single entry with `phase='build_phase_N'`.
- `gradradar update`: a single entry with `phase='update'`.
- `gradradar discover`: a single entry with `phase='discover'`, plus sub-entries for each discovery method run (e.g., `phase='discover_workshops'`, `phase='discover_citations'`).
- `gradradar db publish`: a single entry with `phase='publish'`.

This allows users to run `gradradar db stats` and see a full chronological history of what was run and when.

### 5.25 web_searches

Logs all web searches triggered during search sessions — queries constructed, results found, and any records queued for database ingestion.

```sql
CREATE TABLE web_searches (
    id                  UUID PRIMARY KEY,
    session_id          TEXT,
    triggered_at        TIMESTAMP,
    user_query          TEXT,
    trigger_reason      TEXT CHECK (trigger_reason IN (
                            'named_pi_query', 'taking_students_query',
                            'recent_paper_query', 'thin_results_fallback',
                            'explicit_user_request')),
    constructed_queries TEXT,   -- JSON array of search query strings sent to the web
    results_found       INTEGER,
    new_pis_queued      INTEGER,
    new_programs_queued INTEGER,
    raw_results         TEXT    -- JSON array of top results (title, url, snippet), truncated to 10 results
);
```

**Field notes:**
- `constructed_queries` is a JSON-encoded array of the 2–4 targeted search strings constructed by the LLM from the user's original query.
- `new_pis_queued` and `new_programs_queued` count the records that were written to `update_queue` as a result of this web search session.
- `raw_results` stores the raw search results for auditability, truncated to 10 results per query.

### 5.26 update_queue

Tracks records that need to be refreshed, flagged for manual review, or prioritized for update.

```sql
CREATE TABLE update_queue (
    id              UUID PRIMARY KEY,
    record_type     TEXT,
    record_id       UUID,
    source_url      TEXT,
    priority        INTEGER,
    reason          TEXT,
    queued_at       TIMESTAMP,
    processed_at    TIMESTAMP,
    status          TEXT CHECK (status IN ('pending', 'pending_verification', 'completed', 'failed', 'manual_review'))
);
```

**Field notes:**
- `record_type` is the table name of the record to update (e.g., 'pis', 'programs').
- `priority` is an integer from 1 (highest) to 5 (lowest). Records that fail LLM extraction get priority 1.
- `status` of `manual_review` indicates that automated extraction failed after 3 retries and a human should inspect the source URL.

### 5.27 Full-Text Search Indexes

DuckDB's built-in `fts` extension provides BM25-ranked full-text search. Three FTS indexes are created during the build pipeline (Phase 7):

```sql
INSTALL fts;
LOAD fts;

-- Papers: search by title and abstract
PRAGMA create_fts_index('papers', 'id', 'title', 'abstract', overwrite=1);

-- PIs: search by name, research description, and concatenated top paper titles
-- A materialized view provides the search document:
CREATE OR REPLACE VIEW pi_search_docs AS
SELECT
    p.id,
    p.name,
    p.research_description,
    STRING_AGG(pa.title, ' ') AS top_paper_titles
FROM pis p
LEFT JOIN author_paper ap ON ap.author_id = p.id
LEFT JOIN papers pa ON pa.id = ap.paper_id
GROUP BY p.id, p.name, p.research_description;

PRAGMA create_fts_index('pi_search_docs', 'id', 'name', 'research_description', 'top_paper_titles', overwrite=1);

-- Programs: search by name, course names, course descriptions, and placement text
CREATE OR REPLACE VIEW program_search_docs AS
SELECT
    pr.id,
    pr.name,
    pr.notable_phd_placements,
    pr.industry_placements,
    STRING_AGG(pc.course_name || ' ' || COALESCE(pc.course_description, ''), ' ') AS course_text
FROM programs pr
LEFT JOIN program_courses pc ON pc.program_id = pr.id
GROUP BY pr.id, pr.name, pr.notable_phd_placements, pr.industry_placements;

PRAGMA create_fts_index('program_search_docs', 'id', 'name', 'course_text', 'notable_phd_placements', 'industry_placements', overwrite=1);
```

**FTS query example:**
```sql
-- Find PIs whose research matches "topological analysis neural networks"
SELECT id, name, research_description, fts_main_pi_search_docs.match_bm25(id, 'topological analysis neural networks') AS score
FROM pi_search_docs
WHERE score IS NOT NULL
ORDER BY score DESC
LIMIT 100;
```

FTS indexes are rebuilt during Phase 7 of the build pipeline (takes <1 minute for the full database). They add negligible size to the DuckDB file.

---

## 6. Build Pipeline Specification

### 6.1 Overview

The build pipeline is implemented in `gradradar/build/pipeline.py` and is orchestrated as a series of sequential phases. Each phase is independently re-runnable via `gradradar build --phase N`. The pipeline writes to DuckDB via `db/writer.py`.

The full cold build takes approximately 14–18 hours. After the initial build, differential updates via `gradradar update` refresh only stale records and take a fraction of the time.

#### Within-Phase Checkpointing

Each phase writes a checkpoint file after every 500 records to `~/.gradradar/cache/checkpoint.json`:

```json
{
  "run_id": "uuid",
  "phase": 1,
  "last_item_id": "paper_id_xyz",
  "processed_count": 4200,
  "total_estimated": 50000,
  "updated_at": "2026-04-06T12:30:00Z"
}
```

When `--resume` is used, the pipeline reads the checkpoint and seeks to the last successfully processed item within the current phase, rather than only resuming at the phase level. This prevents losing hours of progress if Phase 1 fails at hour 7.

#### Development Modes

- **`--sample FLOAT`**: Processes only a fraction of seeds, anchor PIs, and institutions (e.g., `--sample 0.1` processes 10%). Useful for validating the pipeline end-to-end at ~10% of the full cost (~$9 instead of ~$90).
- **`--dry-extract`**: Fetches and caches all HTML but skips LLM extraction entirely. This allows iterating on extraction prompts against cached HTML without re-fetching or incurring API costs.

#### LLM Response Caching

All LLM extraction responses are cached locally keyed by `(prompt_hash, model, content_hash)`. If a page is re-extracted with the same prompt and the same content, the cached response is returned without an API call. This makes re-runs during development near-free. The cache is stored at `~/.gradradar/cache/llm_responses/` and can be cleared with `gradradar cache clear`.

### 6.2 Seed Files

All pipeline runs begin by reading from the `seeds/` directory:

**`seeds/institutions.json`**
Array of institution objects. Each includes:
```json
{
  "name": "MIT",
  "country": "US",
  "region": "US",
  "city": "Cambridge",
  "type": "university",
  "url": "https://mit.edu",
  "departments": [
    {
      "name": "EECS",
      "field": "CS",
      "faculty_url": "https://www.eecs.mit.edu/people/faculty-advisors/",
      "phd_url": "https://www.eecs.mit.edu/academics/graduate-programs/",
      "prestige_tier": 1
    }
  ]
}
```

**`seeds/programs.json`**
Array of Masters program seed objects:
```json
{
  "name": "MSc Machine Learning",
  "institution": "UCL",
  "degree_type": "MSc",
  "url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/machine-learning-msc"
}
```

**`seeds/anchor_pis.json`**
Array of anchor PI objects used for citation graph and co-author expansion:
```json
[
  {"name": "Michael Bronstein", "semantic_scholar_id": "..."},
  {"name": "Stefanie Jegelka", "semantic_scholar_id": "..."},
  {"name": "Neel Nanda", "semantic_scholar_id": "..."},
  {"name": "Chris Olah", "semantic_scholar_id": "..."},
  {"name": "Taco Cohen", "semantic_scholar_id": "..."},
  {"name": "Gunnar Carlsson", "semantic_scholar_id": "..."},
  {"name": "Sayan Mukherjee", "semantic_scholar_id": "..."},
  {"name": "Smita Krishnaswamy", "semantic_scholar_id": "..."},
  {"name": "Max Welling", "semantic_scholar_id": "..."},
  {"name": "Petar Velickovic", "semantic_scholar_id": "..."},
  {"name": "David Bau", "semantic_scholar_id": "..."},
  {"name": "Phillip Isola", "semantic_scholar_id": "..."},
  {"name": "Thomas Gebhart", "semantic_scholar_id": "..."},
  {"name": "Frederic Chazal", "semantic_scholar_id": "..."},
  {"name": "Ulrike von Luxburg", "semantic_scholar_id": "..."}
]
```

**`seeds/seed_papers.json`**
Array of seed paper objects for citation traversal:
```json
[
  {
    "title": "Geometric Deep Learning: Grids, Groups, Graphs, Geodesics, and Gauges",
    "semantic_scholar_id": "..."
  },
  {
    "title": "Towards Monosemanticity: Decomposing Language Models With Dictionary Learning",
    "semantic_scholar_id": "..."
  },
  {
    "title": "In-context Learning and Induction Heads",
    "semantic_scholar_id": "..."
  },
  {
    "title": "A Topological Perspective on Singular Points of Piecewise-Linear Networks",
    "semantic_scholar_id": "..."
  },
  {
    "title": "Topology and Geometry of Half-Rectified Network Optimization",
    "semantic_scholar_id": "..."
  },
  {
    "title": "Representation Topology Divergence",
    "semantic_scholar_id": "..."
  },
  {
    "title": "Persistent Homology of Neural Networks",
    "semantic_scholar_id": "..."
  }
]
```

**`seeds/workshops.json`**
Array of workshop seed objects:
```json
[
  {
    "name": "TAG-ML: Topology, Algebra, and Geometry in Machine Learning",
    "parent_conference": "NeurIPS",
    "years": [2022, 2023, 2024],
    "urls": ["https://...", "https://...", "https://..."],
    "topic_focus": "Geometric Deep Learning, Topological Data Analysis"
  },
  {
    "name": "Geometry and Topology in Machine Learning",
    "parent_conference": "ICML",
    "years": [2023, 2024],
    "urls": ["https://...", "https://..."],
    "topic_focus": "Geometric Deep Learning, Differential Geometry"
  },
  {
    "name": "Mechanistic Interpretability Workshop",
    "parent_conference": "ICLR",
    "years": [2024, 2025],
    "urls": ["https://...", "https://..."],
    "topic_focus": "Mechanistic Interpretability, Circuit Analysis"
  },
  {
    "name": "Mechanistic Interpretability Workshop",
    "parent_conference": "NeurIPS",
    "years": [2024],
    "urls": ["https://..."],
    "topic_focus": "Mechanistic Interpretability"
  },
  {
    "name": "Theory of Deep Learning Workshop",
    "parent_conference": "NeurIPS",
    "years": [2023, 2024],
    "urls": ["https://...", "https://..."],
    "topic_focus": "Theoretical ML, Optimization, Generalization"
  },
  {
    "name": "Updatable Machine Learning",
    "parent_conference": "NeurIPS",
    "years": [2023],
    "urls": ["https://..."],
    "topic_focus": "Machine Unlearning, Continual Learning"
  }
]
```

### 6.3 Fetching Infrastructure

All HTTP fetching is handled by `gradradar/build/sources/scraper.py`.

**Primary fetch (httpx):**
```python
async def fetch_html(url: str, session: httpx.AsyncClient) -> str:
    """
    Fetch URL with httpx. Returns raw HTML string.
    Raises FetchError on non-200, timeout, or connection error.
    """
```

**Fallback fetch (playwright):**
If the returned HTML is empty or contains fewer than 500 characters of visible text (as measured by stripping HTML tags and whitespace), the page is assumed to be JS-rendered and is re-fetched via playwright headless Chromium:
```python
async def fetch_html_js(url: str) -> str:
    """
    Fetch URL using playwright. Waits for network idle before returning HTML.
    """
```

**Rate limiting:**
A per-domain rate limiter enforces a minimum of 3 seconds between requests to the same domain. Rate limits are implemented as an `asyncio.Lock` per domain stored in a shared dictionary. Domain is extracted from the URL using `urllib.parse.urlparse`.

**robots.txt compliance:**
Before fetching any page on a domain for the first time, `scraper.py` fetches and parses `robots.txt` using Python's `urllib.robotparser.RobotFileParser`. Pages disallowed for `*` or `gradradar` user-agent are skipped and logged to `scrape_log` with a note of `robots_disallowed`.

**Content caching:**
All fetched HTML is saved to `~/.gradradar/cache/raw_html/[sha256_of_url].html`. On subsequent fetches of the same URL, the cached content is returned without a network request if it is less than 24 hours old (configurable). The content hash is computed from the HTML body, not the URL.

### 6.4 LLM Extraction

All structured data extraction from HTML is handled by `gradradar/build/extractors/llm_extractor.py` using the `instructor` library.

**HTML Preprocessing:**
Before any HTML is passed to the LLM, it is preprocessed to reduce noise and token count:
1. Raw HTML is cleaned using `readability-lxml` or `trafilatura` to extract the main content body, stripping navigation, footers, sidebars, scripts, and styles.
2. The cleaned text is truncated to the per-schema character limit (see Phase specifications below).
3. Only the preprocessed text is sent to the LLM — never raw HTML with full markup.

**Extraction approach:**
1. Preprocessed text is passed to the LLM with a system prompt describing the target Pydantic schema.
2. `instructor` wraps the LLM call with Pydantic validation and automatic retry.
3. Up to 3 retries are attempted on validation failure, with the validation error message appended to the retry prompt.
4. If extraction fails after 3 retries, the record is written to `update_queue` with `status='manual_review'` and `priority=1`.

**Extraction confidence check:**
After each successful extraction, the pipeline checks how many required fields returned as `None`. If >50% of non-optional fields are `None`, the page is assumed to be unsuitable (e.g., not a faculty page, or a generic department landing page) and the record is skipped rather than written as a garbage entry. A warning is logged to `scrape_log`.

**Extraction regression test suite:**
The repository includes `tests/extraction_fixtures/` containing ~20 representative HTML pages covering diverse page types: React SPA, WordPress, static HTML, Gatsby, and multilingual pages. `test_extraction.py` runs the LLM extractor against each fixture and validates that key fields are correctly extracted. This suite runs before any build to catch extraction regressions.

**LLM provider:**
Configured via environment variable. The pipeline uses `litellm` as a unified API layer, supporting OpenAI (`OPENAI_API_KEY`) and Anthropic (`ANTHROPIC_API_KEY`). The default model is `claude-3-5-haiku-latest` for extraction (fast, cheap) and `claude-3-5-sonnet-latest` for complex multi-step extractions.

**Key Pydantic schemas for extraction:**

`PIProfile` (extracted from PI personal/lab pages):
```python
class PIProfile(BaseModel):
    name: str
    lab_name: Optional[str]
    research_description: Optional[str]
    is_taking_students: Literal["yes", "no", "unknown"] = "unknown"
    taking_students_confidence: float = Field(ge=0.0, le=1.0)
    taking_students_evidence: Optional[str]  # quote from page supporting the classification
    current_student_count: Optional[int]
    google_scholar_url: Optional[str]
    email: Optional[str]
    funding_sources: Optional[str]
    funding_expiry: Optional[str]
    theory_category: Literal["theory", "applied", "mixed", "unknown"] = "unknown"
    students: List[StudentRecord]
    industry_connections: List[IndustryConnection]
```

`ProgramProfile` (extracted from Masters program pages):
```python
class ProgramProfile(BaseModel):
    name: str
    degree_type: Literal["MSc", "MS", "MPhil", "MEng", "MRes", "MA"]
    duration_months: Optional[int]
    thesis_option: Optional[bool]
    tuition_total: Optional[int]
    tuition_currency: Optional[str]
    scholarships_available: Optional[bool]
    percent_funded: Optional[float]
    gre_required: Literal["yes", "no", "optional"]
    gpa_minimum: Optional[float]
    toefl_minimum: Optional[int]
    ielts_minimum: Optional[float]
    theory_intensity: float = Field(ge=0.0, le=1.0)
    courses: List[CourseRecord]
    admissions_profile: Optional[AdmissionsProfile]
```

`FacultyListResult` (extracted from department faculty pages):
```python
class FacultyListResult(BaseModel):
    faculty: List[FacultyStub]

class FacultyStub(BaseModel):
    name: str
    title: Optional[str]
    profile_url: Optional[str]
    research_areas: Optional[List[str]]
```

### 6.5 Phase 1 — Semantic Scholar API Ingestion

**Duration:** 6–8 hours
**Implementation:** `gradradar/build/sources/semantic_scholar.py`
**Rate limit:** 10 requests/second with free API key (1 req/sec without key; key required for build)

**Steps:**

1. **Seed paper fetch:** For each paper in `seeds/seed_papers.json`, fetch full paper metadata from:
   `GET /paper/{paper_id}?fields=title,abstract,year,venue,citationCount,fieldsOfStudy,authors,externalIds`

2. **Anchor PI paper fetch:** For each PI in `seeds/anchor_pis.json`, fetch all papers:
   `GET /author/{author_id}/papers?fields=title,abstract,year,venue,citationCount,externalIds&limit=1000`

3. **Citation traversal — forward (papers that cite seed papers):**
   `GET /paper/{paper_id}/citations?fields=title,abstract,year,venue,citationCount,authors,externalIds&limit=500`
   Traverse 2 hops using **best-first search**: at each hop, score candidate papers by how many seed-adjacent authors they share, and traverse highest-scoring papers first. This prioritizes relevance over breadth. Include a paper if: any author is at a target institution OR if citation_count >= 5 OR if year >= 2023.
   
   **Traversal budget:** A hard cap of `max_papers_per_hop = 5000` limits the total papers collected at each hop. A running counter is printed to the console and recorded in `scrape_log`: "Phase 1: 12,400 / 50,000 max papers traversed". This prevents combinatorial explosion from highly-cited seed papers.

4. **Citation traversal — backward (papers cited by seed papers):**
   `GET /paper/{paper_id}/references?fields=title,abstract,year,venue,citationCount,authors,externalIds&limit=500`
   Traverse 2 hops with the same inclusion criteria and traversal budget.

5. **Author extraction:** For every author encountered across all fetched papers, fetch author details:
   `GET /author/{author_id}?fields=name,affiliations,hIndex,citationCount,paperCount,homepage,externalIds`

   Filter: include an author in the `pis` table if they have an affiliation matching a target institution OR if they appear in ≥ 3 seed-adjacent papers.

6. **Co-author expansion for anchor PIs:** For each anchor PI, fetch their co-authors:
   `GET /author/{author_id}/papers?fields=authors`
   Extract all co-authors. For any co-author affiliated with a target institution, add to the PI discovery queue.

7. **Write all data** to DuckDB (papers, pis, author_paper, citations tables) as records are fetched.

**Deduplication:** Before writing, check for existing records by `semantic_scholar_id`. If a record exists, compare fields and update only if changed.

### 6.6 Phase 2 — OpenAlex API Ingestion

**Duration:** 1–2 hours
**Implementation:** `gradradar/build/sources/openalex.py`
**Rate limit:** No key required; observe polite rate (10 req/sec max)

**Steps:**

1. **Institution enrichment:** For each institution in the DuckDB `institutions` table, fetch from:
   `GET https://api.openalex.org/institutions?search={institution_name}&per-page=1`
   Extract: `display_name`, `country_code`, `geo.city`, `ror` (ROR ID for deduplication).

2. **Author enrichment:** For each PI in the DuckDB `pis` table with `openalex_id=NULL`, search by name + institution:
   `GET https://api.openalex.org/authors?search={name}&filter=last_known_institution.display_name.search:{institution}`

   Match by name similarity (fuzzy match threshold: 0.85 Jaro-Winkler). Populate `openalex_id`, `h_index` (if missing), `total_citations` (if missing).

3. **Grant/funding extraction:** For matched authors, fetch works with grant information:
   `GET https://api.openalex.org/works?filter=author.id:{openalex_id}&select=grants&per-page=200`
   Aggregate grant funders and years. Write to `pis.funding_sources` if not already populated.

4. **Research trajectory:** For each PI, fetch papers grouped by year using OpenAlex concepts:
   `GET https://api.openalex.org/works?filter=author.id:{openalex_id}&group-by=publication_year,concepts.id`
   Map concepts to topic names in the `topics` table. Write to `pi_research_trajectory`.

### 6.7 Phase 3 — Department Page Scraping

**Duration:** ~30 minutes
**Implementation:** `gradradar/build/sources/scraper.py` + `gradradar/build/extractors/llm_extractor.py`

**Steps:**

For each department in `seeds/institutions.json` that has a `faculty_url`:

1. Check robots.txt for the domain.
2. Fetch the faculty listing page (httpx → playwright fallback).
3. Cache raw HTML.
4. Compare content hash against stored hash. If unchanged, skip extraction and update `scraped_at` only.
5. Pass HTML + `FacultyListResult` schema to LLM via instructor.
6. For each extracted `FacultyStub`:
   a. Check if a PI with this name + institution already exists in DuckDB.
   b. If not, create a new PI record with `status='needs_enrichment'` and add to PI discovery queue.
   c. If yes, update `personal_url` if newly discovered.
7. Write department record to DuckDB with updated `scraped_at` and `content_hash`.

### 6.8 Phase 4 — PI Page Scraping

**Duration:** 3–4 hours
**Implementation:** `gradradar/build/sources/scraper.py` + `gradradar/build/extractors/llm_extractor.py`

**Steps:**

For each PI in the DuckDB `pis` table that has a `personal_url` or `lab_url`:

1. Check robots.txt.
2. Fetch the PI's personal page (httpx → playwright fallback).
3. If `lab_url` differs from `personal_url`, also fetch the lab page.
4. Cache raw HTML for each page.
5. Compare content hash. If unchanged, skip.
6. Pass combined HTML (personal + lab page, truncated to 20,000 characters total) + `PIProfile` schema to LLM.
7. Retry up to 3 times on validation failure.
8. On persistent failure, write to `update_queue` with `status='manual_review'`.
9. Write enriched PI record to DuckDB. Write pi_students and pi_industry_connections records.
10. If the PI page links to a Google Scholar profile that hasn't been fetched, add to Phase 1 follow-up queue.

**PI discovery from student pages:**
For each current or alumni student in `pi_students`, check if the student now has their own faculty page (i.e., appears in `pis` table with a `personal_url`). If so, add their own advisor record.

### 6.9 Phase 5 — Program Page Scraping

**Duration:** ~20 minutes
**Implementation:** `gradradar/build/sources/scraper.py` + `gradradar/build/extractors/llm_extractor.py`

**Steps:**

For each program in `seeds/programs.json`:

1. Fetch the program landing page.
2. Check if the page links to a separate curriculum/courses page. If so, fetch that as well.
3. Check if the page links to a separate admissions/requirements page. If so, fetch that as well.
4. Cache all raw HTML.
5. Concatenate all fetched HTML (truncated to 30,000 characters) and pass to LLM with `ProgramProfile` schema.
6. Write `programs`, `program_courses`, and `program_admissions_profile` records to DuckDB.
7. For programs without a matching `institution_id` in DuckDB, create a placeholder institution record.

### 6.10 Phase 6 — Workshop Page Scraping

**Duration:** ~10 minutes
**Implementation:** `gradradar/build/sources/workshops.py`

**Steps:**

For each workshop in `seeds/workshops.json`:

1. Fetch the workshop page.
2. If the URL is a PDF (detected by Content-Type header or `.pdf` extension):
   a. Download the PDF.
   b. Extract text using `pdfplumber`.
   c. Pass extracted text to LLM for speaker name extraction.
3. If the URL is HTML, pass to LLM for speaker extraction using the schema:
   ```python
   class WorkshopSpeakers(BaseModel):
       speakers: List[SpeakerRecord]

   class SpeakerRecord(BaseModel):
       name: str
       affiliation: Optional[str]
       role: Literal["speaker", "organizer", "panelist"]
   ```
4. For each extracted speaker:
   a. Check if a PI with this name already exists in DuckDB.
   b. If not, create a new PI record (partial) and add to Phase 1 follow-up queue for Semantic Scholar lookup.
   c. If yes, update `pi_workshops` junction table.
5. Write `workshops` and `pi_workshops` records to DuckDB.

### 6.11 Phase 7 — Full-Text Search Index Creation

**Duration:** <1 minute
**Implementation:** `gradradar/db/schema.py`

**Steps:**

1. Install and load the DuckDB `fts` extension.
2. Create the `pi_search_docs` and `program_search_docs` materialized views that concatenate the text fields used for full-text search (see Section 5.27).
3. Create FTS indexes on `papers`, `pi_search_docs`, and `program_search_docs` using `PRAGMA create_fts_index`.
4. Verify index creation by running a test query against each index.

FTS index creation is fast and deterministic — it does not call any external APIs. Indexes can be rebuilt at any time by re-running `gradradar build --phase 7` with no cost.

**Note:** Phase 7 is retained as a separate phase for consistency with the pipeline numbering and to allow independent re-indexing after data updates. In practice it adds negligible time to the build.

### 6.12 PI Discovery Methodology

The pipeline uses five overlapping discovery methods to maximize coverage:

**Method 1 — Top-down from departments:**
Scrape faculty listing pages of all target departments at all institutions in `seeds/institutions.json`. Guaranteed to find any PI with a faculty page at a target institution.

**Method 2 — Citation graph traversal:**
From seed papers in `seeds/seed_papers.json`, traverse citations 2 hops forward and backward. Finds PIs who publish in the target research space even if their institution is not in the seed list.

**Method 3 — Anchor PI co-author expansion:**
For each anchor PI in `seeds/anchor_pis.json`, pull their full co-author list and add any co-authors at target institutions or with ≥ 50 citations to the discovery queue.

**Method 4 — Workshop speaker seeding:**
Scrape speaker and organizer lists from all workshops in `seeds/workshops.json`. Finds community members who may not be highly cited yet but are active in the research space.

**Method 5 — PhD student placement tracing:**
For each anchor PI, scrape their alumni list and trace where former students are now. Former students who started their own labs and are now PIs are high-signal targets with known research lineage.

**Citation floor for inclusion:**
The default minimum citation count for including a paper in citation traversal is 10. For papers published in 2023–2025, the floor is lowered to 5 to capture emerging work.

### 6.13 Citation Velocity Computation

Citation velocity is computed at both the paper level and the PI level. **Self-citations are excluded** from all velocity calculations: if any author on the citing paper overlaps with the cited paper's authors, that citation is not counted.

**Paper-level:**
```
citation_velocity = non_self_citation_count_last_2_years / max(year_age, 1)
```
where `year_age = current_year - publication_year`.

**PI-level:**
```
citation_velocity = (non_self_citations_last_5_years / total_non_self_citations) * (1 / max(years_active, 1))
```
where `years_active = current_year - phd_year + 1`.

**Velocity source classification:**
After computing velocity, the pipeline checks whether a single paper accounts for >60% of the PI's recent non-self-citations:
- If yes: `citation_velocity_source = 'depth'` — velocity is driven by one viral or review paper.
- If no single paper exceeds 60% but the top 3 papers account for >80%: `citation_velocity_source = 'mixed'`.
- Otherwise: `citation_velocity_source = 'breadth'` — velocity is distributed across many papers.

This classification is displayed in search results so users can distinguish genuine broad momentum from single-paper spikes.

---

## 7. Search Architecture

### 7.1 Overview

The search system is implemented in `gradradar/search/` and supports three modes: structured SQL search, full-text search (BM25), and hybrid search (the default). All modes accept natural language input and translate it to structured queries via an LLM.

### 7.2 LLM Query Translation

**Implementation:** `gradradar/search/llm_query.py`

The query translation step receives the user's natural language query, the full schema documentation (formatted as a concise reference), and the user's local profile from `~/.gradradar/profile.json`. It asks the LLM to produce a structured query plan JSON:

```json
{
  "mode": "hybrid",
  "search_terms": "topological analysis neural network representations manifold geometry",
  "fts_tables": ["pi_search_docs", "papers"],
  "sql_filters": {
    "table": "pis",
    "region": "UK",
    "is_taking_students": "yes",
    "career_stage": ["assistant_professor", "associate_professor"]
  },
  "output_format": "phd_pi",
  "explanation_focus": [
    "connection between query topics and PI's paper topics",
    "lab size and mentorship signals"
  ],
  "top_k": 10
}
```

**Query plan schema (Pydantic):**
```python
class QueryPlan(BaseModel):
    mode: Literal["sql", "fts", "hybrid"]
    search_terms: Optional[str]  # extracted keywords/phrases for FTS BM25 search
    fts_tables: List[Literal["pi_search_docs", "papers", "program_search_docs"]]
    sql_filters: Optional[Dict[str, Any]]
    output_format: Literal["phd_pi", "masters_program", "mixed"]
    explanation_focus: List[str]
    top_k: int = Field(default=10, ge=1, le=50)
```

The LLM system prompt for query translation includes:
- A compact reference of all filterable fields and their allowed values
- The user's profile.json contents (if available)
- Instructions to extract effective search keywords from the natural language query (expanding synonyms and related terms)
- Instructions to prefer hybrid mode for most queries
- Instructions to set `output_format="mixed"` only if the user explicitly asks for both PhD and Masters results

**Model used:** `claude-3-5-sonnet-latest` or `gpt-4o` for query translation (higher reasoning quality required here vs. extraction).

### 7.3 Full-Text Search (BM25)

**Implementation:** `gradradar/search/fts_search.py`

```python
def fts_search(
    search_terms: str,
    tables: List[str],
    n_results: int = 100,
) -> List[SearchResult]:
    """
    Runs BM25 full-text search against DuckDB FTS indexes.
    Queries each specified FTS-indexed table/view.
    Returns merged, deduplicated results sorted by BM25 score.
    """
```

**Steps:**
1. For each table in `fts_tables`, run a BM25 match query using the `search_terms` from the query plan.
2. Merge results across tables (deduplication by record ID).
3. Sort by BM25 score (descending = more relevant).
4. Return top `n_results` as `SearchResult` objects containing the record ID, table, BM25 score, and key fields.

**Keyword expansion:** The LLM query translator is responsible for expanding the user's natural language query into effective search terms. For example, "labs doing work like Towards Monosemanticity" becomes search terms like `"mechanistic interpretability sparse autoencoders superposition monosemantic features dictionary learning"`. This expansion step is critical for FTS quality — the LLM generates synonyms, related terms, and key concepts that the BM25 index can match against.

### 7.4 Structured SQL Search

**Implementation:** `gradradar/search/sql_search.py`

```python
def sql_search(
    table: str,
    filters: Dict[str, Any],
    candidate_ids: Optional[List[str]] = None,
    order_by: Optional[str] = None,
    limit: int = 50
) -> List[Dict]:
    """
    Executes a parameterized SQL query against DuckDB.
    If candidate_ids is provided, adds WHERE id IN (...) clause.
    """
```

**Filter translation rules:**
- String filters → `column = ?`
- List filters → `column IN (?)`
- Dict filters with `$gte`/`$lte` → `column >= ?` / `column <= ?`
- NULL checks → `column IS NULL` / `column IS NOT NULL`

All queries are parameterized to prevent injection. The `sql_search` function never constructs SQL by string concatenation.

### 7.5 Hybrid Search

**Implementation:** `gradradar/search/engine.py`

Hybrid search is the default mode for all queries. The algorithm:

1. **FTS pass:** Call `fts_search` with `search_terms` from the query plan and `n_results=100` to generate a candidate set of record IDs ranked by BM25 score.
2. **SQL pass:** Call `sql_search` with `candidate_ids=<from step 1>` and SQL filters from the query plan. This narrows the candidate set.
3. **LLM re-ranking:** Pass the top 20 filtered candidates (with their full records fetched from DuckDB) to the LLM with `temperature=0`. Ask it to re-rank them based on semantic relevance to the query and generate per-result match explanations. Re-ranking results are cached keyed by `(query_plan_hash, candidate_ids_hash)` with a 24-hour TTL to ensure ranking stability across repeated queries.
4. **Return** the top `top_k` results with explanations, formatted by the output formatter.

**Query plan visibility:** Before executing, the engine always prints a one-line plan summary:
```
Searching pis + papers | filters: region=UK, is_taking_students=yes | hybrid mode
```
Users can pass `--explain` to print the full `QueryPlan` JSON, or `--explain-only` to print the plan and exit without executing the search. This makes the LLM's query translation transparent and debuggable.

**Fallback:** If FTS returns fewer than 10 results (e.g., search terms are very specific and no BM25 matches exist), the engine falls back to SQL-only search with a broadened filter set and notifies the user.

### 7.6 Web Search Layer

**Implementation:** `gradradar/search/web_search.py`

The web search layer supplements database results with live web searches under specific conditions. It is not triggered on every query — generic web searches produce noisy results. Instead, the engine evaluates trigger conditions before each query and fires targeted, LLM-constructed search strings when warranted.

#### Trigger Conditions

**Always trigger web search:**
- Query references a specific named PI — "tell me about Chris Olah" or "is Jane Smith taking students" should check the PI's current lab page and any recent news.
- Query explicitly asks about taking students or current openings — this field changes frequently and the database may be stale.
- Query references a paper published after the database build date (detected by checking whether the paper's `arxiv_id` or title exists in the local `papers` table; if not, assume it may be recent).
- User explicitly uses `--web` flag or says "search the web for...".

**Optionally trigger web search (fallback):**
- Database returns fewer than 5 results for the query — web search is used to fill out thin result sets.

**Never trigger web search:**
- Pure filtering queries with no semantic component ("show me all US programs with no GRE requirement") — the database handles these completely.
- Broad exploratory queries where the database is sufficient and web results would be noisy ("what are the main research areas in geometric deep learning?").
- User uses `--no-web` flag.

#### Query Construction

The LLM constructs 2–4 targeted search query strings from the user's original question. It does not pass the raw user query to the search engine. Query templates by trigger type:

**For named PI queries:**
```
"[PI name] lab taking PhD students 2026"
"[PI name] [institution] research group"
"[PI name] recent papers 2024 2025"
```

**For program queries:**
```
"[program name] [institution] application deadline 2027"
"[program name] funding fellowship 2026"
```

**For discovery queries (paper similarity / topic-based):**
```
"[key terms from query] lab [region] PhD students"
"[author names from related papers] collaborators [institution type]"
```

The LLM outputs these as a `WebSearchPlan`:

```python
class WebSearchPlan(BaseModel):
    should_search: bool
    trigger_reason: Optional[Literal[
        'named_pi_query', 'taking_students_query',
        'recent_paper_query', 'thin_results_fallback',
        'explicit_user_request'
    ]]
    queries: List[str] = Field(max_items=4)
```

#### Result Merging

After both the database search and (optionally) web search complete:

1. Web results are parsed by the LLM into structured `WebResult` objects:
   ```python
   class WebResult(BaseModel):
       title: str
       url: str
       snippet: str
       result_type: Literal["pi", "program", "other"]
       extracted_name: Optional[str]
       extracted_institution: Optional[str]
   ```
2. Results are deduplicated against the database result set by name + institution (fuzzy match, threshold 0.85).
3. Web results not already in the database are tagged `source='web'` in the output.
4. Database results are tagged `source='db'`.
5. The combined set is re-ranked by the LLM for relevance to the original query.

#### Quality Gate — Web Search Results

Web results are never written directly to the main database tables. All web-discovered records go through a quality gate before being queued:

1. **Minimum quality criteria:** A web result must include a name, an institution, and a URL that resolves to a real page (HTTP 200). Results missing any of these are discarded.
2. **Dedup against queue:** Results are checked against existing `update_queue` entries (not just main tables) to prevent the same URL from being queued repeatedly across search sessions.
3. **Rate limit:** A maximum of 10 new `update_queue` entries are created per search session. If the web search finds more than 10 new entities, the highest-relevance results are queued and the rest are discarded with a log entry.

Records that pass the quality gate are written to `update_queue` with `status='pending_verification'`:
```sql
INSERT INTO update_queue (
    record_type, source_url, priority, reason, status, queued_at
) VALUES (
    'pis',          -- or 'programs'
    '[url]',
    3,              -- medium priority
    'discovered_via_web_search',
    'pending_verification',
    now()
);
```

The `web_searches` table is also updated with the session ID, trigger reason, constructed queries, and count of new records queued.

The next time `gradradar discover` runs, it processes the `update_queue` and enriches these web-discovered stubs into full records. This means the database improves over time with each search session without any explicit user action.

#### Source Attribution in Output

Each result card in the terminal output includes a source badge:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Prof. Jane Smith — MIT EECS                    [source: db]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Dr. Alex Chen — Cambridge (found via web)      [source: web]
  ⚠ Data from live web search — not yet verified in database
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Web-sourced results display a warning noting that the data is from a live web search and has not yet been verified against the database. The user is advised to verify details directly.

### 7.7 Output Formats

#### phd_pi Format

Displayed for PhD advisor queries. Each result card contains:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Prof. Jane Smith — MIT EECS
  Assistant Professor | Taking Students: YES (as of 2026-03-15) | Theory: theory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  RESEARCH
  [research_description, 3-4 sentences]

  WHY THIS MATCHES
  [LLM-generated explanation tying specific papers or courses
   to the query topics, grounded in evidence_paper_ids]

  TOP RELEVANT PAPERS
  1. "Paper Title" (NeurIPS 2023) — 142 citations
     [abstract, 2 sentences]
  2. ...

  STATS
  Career stage:         Assistant Professor
  PhD from:             Stanford (2019)
  h-index:              18
  Citations (5yr):      1,240
  Citation velocity:    0.73 (breadth — distributed across papers)
  Theory category:      theory (venue-derived)
  Current students:     4
  Taking students:      YES — ⚠ Verify directly (checked 2026-03-15)
  Lab:                  Smith Geometry & Learning Lab
  Funding:              NSF CAREER 2022, DARPA
  Industry connections: Google DeepMind (joint papers, 2023)
  Admission type:       Direct
  Dept avg stipend:     $40,000/yr
  GRE required:         No
  Application deadline: December 15
  Personal URL:         https://...
  Lab URL:              https://...
```

#### masters_program Format

Displayed for Masters program queries. Each result card contains:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  MSc Machine Learning — UCL
  1 year | MRes option available | Funded: 25%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  WHY THIS MATCHES
  [LLM-generated explanation tying specific courses to query
   interests, grounded in course names and descriptions]

  CURRICULUM HIGHLIGHTS
  Required: Statistical Machine Learning, Probabilistic Inference,
            Graphical Models
  Relevant electives: Topological Data Analysis, Advanced
                      Optimisation, Geometric Deep Learning

  STATS
  Degree:               MSc
  Duration:             12 months
  Theory intensity:     0.71
  GRE required:         No
  Min GPA:              3.3
  TOEFL minimum:        95
  Thesis option:        Yes (MRes track)
  Tuition:              £14,000
  Scholarships:         Yes (25% of students funded)
  International funded: Yes
  TA/RA available:      RA (for MRes students)
  % continuing to PhD:  35%
  Notable PhD plac.:    Cambridge, Oxford, ETH Zurich
  Application deadline: January 15
  URL:                  https://...
```

### 7.7 Profile Integration

At query time, the user's `profile.json` is loaded and injected into the LLM context for query translation and match explanation generation. Specifically:

- `research_interests` fields are used by the LLM to expand the FTS search terms with relevant keywords from the user's areas of interest.
- `research_interests.research_style` (e.g., "theoretical, math-heavy") is used to filter by `theory_category` in the SQL WHERE clause.
- `constraints.gre_can_take` is used to add `gre_required` filters when relevant.
- `constraints.funding_required` is used to filter departments with `phd_funding_guarantee=true` or programs with `scholarships_available=true`.
- `constraints.international_student` is used to filter for `international_funded=true` when relevant.

The profile is never sent to any remote server outside of the local LLM API call. If the user does not have a profile, search works normally but match explanations are generic rather than personalized.

---

## 8. CLI Specification

The CLI is implemented in `gradradar/cli.py` using `click` and `rich` for terminal formatting. The package is installed as a system command via `pyproject.toml` entry_points.

### 8.1 Setup Commands

#### `gradradar init`

Downloads the database from Cloudflare R2 and initializes `~/.gradradar/`.

```bash
gradradar init
```

**Behavior:**
1. Creates `~/.gradradar/db/`, `~/.gradradar/cache/raw_html/`, `~/.gradradar/db/snapshots/` if they do not exist.
2. Reads `GRADRADAR_R2_PUBLIC_URL` from environment (or prompts if not set) to know the base URL of the R2 bucket.
3. Fetches `[R2_PUBLIC_URL]/latest/manifest.json` to determine the latest version.
4. Checks if a local database already exists and compares schema versions. If schema version is incompatible (MAJOR mismatch), warns the user and asks for confirmation before overwriting.
5. Downloads `gradradar.duckdb` from `[R2_PUBLIC_URL]/[version]/` using streaming HTTPS GET (no auth required). Shows a progress bar.
6. Verifies SHA-256 checksum against `manifest.json`. Retries up to 3 times on checksum failure.
8. Writes the downloaded `manifest.json` to `~/.gradradar/db/manifest.json`.
9. Prints a summary: record counts, build date, version downloaded, and disk usage.
10. Suggests running `gradradar profile setup` as an optional next step for personalized results. Search works immediately without a profile.

**Options:**
- `--force` — overwrite existing database without prompting.
- `--version TEXT` — download a specific version instead of latest (e.g., `--version v1.0`).
- `--pull` — download only files that have changed since the locally installed version (partial upgrade).
- `--offline` — skip the remote manifest check; use only local database.

#### `gradradar profile setup`

Optional but recommended profile setup. The profile personalizes match explanations at query time. **Search works fully without a profile** — results are simply generic rather than personalized.

The profile is intentionally minimal (5 fields) to minimize setup friction. An extended profile is available via `gradradar profile extend` for users who want deeper personalization.

```bash
gradradar profile setup            # 5-field quick setup
gradradar profile extend           # optional deeper questionnaire (background, coursework, etc.)
```

**Behavior:** Launches a `rich` interactive prompt sequence that populates `~/.gradradar/profile.json`. The user can skip any field (press Enter with no input). Existing profile values are shown as defaults.

**Core profile fields (5 fields):**

| # | Field | Example | Usage |
|---|---|---|---|
| 1 | Degree preference | `["PhD", "Masters"]` | Determines default `output_format` in query plan |
| 2 | Primary research interests | "topological analysis of neural network representations, mechanistic interpretability, geometric deep learning" | Appended to semantic query; used in match explanations |
| 3 | Geography priority | `["US", "UK", "Europe"]` | Applied as SQL region filter |
| 4 | International student | `true` / `false` / `null` | Filters for `international_funded=true` when relevant |
| 5 | Funding requirement | `"required"` / `"strongly_preferred"` / `"nice_to_have"` | Filters for funding fields in departments and programs |

#### `gradradar profile extend`

Optional deeper questionnaire that unlocks richer match explanations. Fields are organized in three sections: Academic Background, Detailed Research Interests, and Application Constraints.

```bash
gradradar profile extend                        # run all sections
gradradar profile extend --section background   # run one section
gradradar profile extend --section research
gradradar profile extend --section constraints
```

**Extended fields (all optional):**

**Academic Background:**
- Undergraduate GPA and grading scale
- Undergraduate major(s)
- Relevant coursework (freeform multi-line)
- Research experience (freeform multi-line)
- Publications and preprints

**Detailed Research Interests:**
- Research style preference (e.g., "highly theoretical, math-heavy")
- Specific seed papers that represent your interests
- Specific researchers you admire
- Masters curriculum priorities

**Application Constraints:**
- Target intake year
- GRE availability (yes / no / prefer not to)
- English proficiency test scores
- Minimum acceptable PhD stipend (USD)
- Hard exclude list (institutions, countries, or program types)

**Complete `profile.json` schema:**

```json
{
  "degree_preference": ["PhD", "Masters"],
  "research_interests": "",
  "geography_priority": ["US", "UK", "Europe"],
  "international_student": null,
  "funding_requirement": "required",

  "extended": {
    "background": {
      "gpa": "",
      "gpa_scale": "",
      "undergraduate_major": "",
      "relevant_coursework": "",
      "research_experience": "",
      "publications": ""
    },
    "research": {
      "research_style": "",
      "seed_papers": [],
      "admired_researchers": [],
      "masters_curriculum_priorities": ""
    },
    "constraints": {
      "target_intake_year": 2027,
      "gre": "prefer_not",
      "english_proficiency_test": "",
      "minimum_phd_stipend_usd": null,
      "hard_excludes": []
    }
  }
}
```

**Profile usage at query time:**

The core profile fields are always injected into the LLM system prompt for query translation and match explanation generation. If extended fields are populated, they are also included — enabling richer, more personalized explanations (e.g., "Given your coursework in Algebraic Topology and your interest in the mathematical structure of representations, Prof. Smith's work on persistent homology of activation spaces is a direct fit…"). Fields in `constraints` (core and extended) are applied as hard SQL filters unless the user explicitly overrides them with CLI flags.

If no profile exists at all, search works normally with generic match explanations. The user is not prompted or warned about missing profile — it is purely additive.

#### `gradradar profile show`

Displays the current profile in a formatted table.

```bash
gradradar profile show
```

### 8.2 Search Commands

#### `gradradar search`

Primary search command. Runs hybrid search by default.

```bash
gradradar search "query text"
gradradar search "query text" --type phd
gradradar search "query text" --type masters
gradradar search "query text" --region US
gradradar search "query text" --region UK
gradradar search "query text" --region Europe
gradradar search "query text" --top 20
gradradar search "query text" --type phd --region UK --top 5
gradradar search "query text" --mode sql
gradradar search "query text" --mode fts
gradradar search "query text" --mode hybrid
gradradar search "query text" --no-profile
gradradar search "query text" --json
gradradar search "query text" --web          # force web search on for this query
gradradar search "query text" --no-web       # force web search off for this query
gradradar search "query text" --explain       # print full QueryPlan JSON before executing
gradradar search "query text" --explain-only  # print QueryPlan JSON and exit without searching
gradradar search "query text" --clarify       # opt in to clarifying questions before search
```

**Options:**
- `--type TEXT` — constrain output type: `phd`, `masters`, or `both` (default: determined by LLM from query)
- `--region TEXT` — filter by region: `US`, `UK`, `Europe`
- `--top INTEGER` — number of results to return (default: 10)
- `--mode TEXT` — override search mode: `sql`, `fts`, `hybrid` (default: `hybrid`)
- `--no-profile` — ignore user profile for this query
- `--json` — output raw JSON instead of formatted cards
- `--web` — force web search on regardless of trigger conditions
- `--no-web` — force web search off regardless of trigger conditions (default behavior for pure filtering queries)
- `--explain` — print the full `QueryPlan` JSON before executing the search. Useful for understanding why results look the way they do
- `--explain-only` — print the `QueryPlan` JSON and exit without executing the search. Useful for debugging query translation
- `--clarify` — opt in to the clarifying question session before search (default: no questions asked; profile + query used directly)

**Behavior:**
1. Load user profile (unless `--no-profile`).
2. If `--clarify` is set, run the clarifying question session (see Section 9).
3. Call `llm_query.py` to translate query (+ session context if clarify was used) to a `QueryPlan`.
4. Print one-line plan summary. If `--explain` or `--explain-only`, print full QueryPlan JSON. If `--explain-only`, exit.
5. Apply any CLI flag overrides to the query plan (e.g., `--region` overrides any region in the plan).
6. Call `engine.py` with the query plan.
7. Format and print results using `rich`.

**Example outputs:**

```bash
$ gradradar search "topological ML with focus on neural network representations" --type phd --region UK

Searching... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:03

Found 7 matching PhD labs in UK

[Result cards displayed as described in Section 7.6]
```

### 8.3 Database Management Commands

#### `gradradar update`

Refreshes only existing records that are stale based on their TTL. Does **not** discover new PIs or programs. Run monthly. Estimated time: 2–3 hours after 30 days, 5–6 hours after 90 days.

```bash
gradradar update
gradradar update --type pis
gradradar update --type programs
gradradar update --type papers
gradradar update --dry-run
```

**Options:**
- `--type TEXT` — restrict update to a specific record type
- `--dry-run` — show what would be updated without making changes

**Behavior:**
1. Creates a snapshot of the current DuckDB file to `~/.gradradar/db/snapshots/gradradar_YYYY-MM-DD.duckdb`.
2. Queries the `update_queue` for pending records with `status='pending'`.
3. Also queries for stale records by TTL:
   - `is_taking_students` stale if `scraped_at < now() - interval '30 days'`
   - `total_citations`, `h_index` stale if `scraped_at < now() - interval '90 days'`
   - Program fields stale if `scraped_at < now() - interval '180 days'`
   - Paper metadata stale if `scraped_at < now() - interval '365 days'`
4. Merges update_queue records with stale records (deduped by `source_url`).
5. For each stale record: re-fetches `source_url`, computes content hash.
   - If hash is **unchanged**: updates `scraped_at` timestamp only. No LLM extraction needed.
   - If hash has **changed**: re-extracts all fields via LLM, writes updated record to DuckDB. FTS indexes are rebuilt at the end of the update run.
6. Records this run to `scrape_log` with `phase='update'`.
7. Prints a summary: records checked, content-unchanged (timestamp only), re-extracted, failed.

**Important:** `gradradar update` never runs discovery logic. It will not add new PIs, new programs, or traverse citation graphs. It only re-processes records that already exist in the database.

#### `gradradar discover`

Finds entirely new PIs, programs, and labs not yet in the database. Does **not** re-process or re-scrape existing records. Run every 6 months or after a major conference cycle (NeurIPS in December, ICML in July, ICLR in May). Estimated time: 4–6 hours.

```bash
gradradar discover
gradradar discover --method workshops
gradradar discover --method citations
gradradar discover --method coauthors
gradradar discover --method placements
gradradar discover --method departments
gradradar discover --dry-run
```

**Options:**
- `--method TEXT` — run only a specific discovery method (see below); default runs all methods
- `--dry-run` — show how many new records would be discovered without writing them

**Discovery methods (matching Section 6.12):**
- `workshops` — re-scrape workshop speaker lists from `seeds/workshops.json` and any new workshops added since last run; identify speakers not yet in the `pis` table
- `citations` — traverse citation graphs from papers added to the database since the last discover run; apply the same 2-hop forward/backward strategy as Phase 1
- `coauthors` — pull updated co-author lists for all anchor PIs; find co-authors at target institutions not yet in the `pis` table
- `placements` — re-scrape alumni pages for anchor PIs; identify former students who now have their own faculty positions
- `departments` — re-scrape faculty listing pages for all departments in `seeds/institutions.json`; identify faculty listed who are not yet in the `pis` table

**Behavior:**
1. Creates a snapshot of the current DuckDB file.
2. For each enabled discovery method, runs the discovery logic and generates a list of candidate new records (names + source URLs).
3. Deduplicates candidates against existing `pis` and `programs` records (name + institution fuzzy match, threshold 0.85 Jaro-Winkler).
4. For each genuinely new candidate: creates a stub record in DuckDB and queues for enrichment via `update_queue` with `priority=2` and `reason='discovered_by_[method]'`.
5. Optionally triggers immediate enrichment of the newly discovered stubs (equivalent to running `gradradar update` on just the new records).
6. Records this run to `scrape_log` with `phase='discover'`.
7. Prints a summary: candidates found, deduped against existing, new stubs created, methods run.

**Important:** `gradradar discover` never re-scrapes records that already exist in the database. If a PI is already in the `pis` table, discovering them again via a co-author list is a no-op.

#### `gradradar build`

Runs the full cold build pipeline or a specific phase.

```bash
gradradar build --full
gradradar build --phase 1
gradradar build --phase 2
gradradar build --phase 3
gradradar build --phase 4
gradradar build --phase 5
gradradar build --phase 6
gradradar build --phase 7
gradradar build --resume
gradradar build --full --sample 0.1
gradradar build --full --dry-extract
```

**Options:**
- `--full` — run all 7 phases in sequence (14–18 hours)
- `--phase INTEGER` — run a specific phase only (1–7)
- `--resume` — resume from the last checkpoint within the current phase, not just from the last completed phase (see Section 6.1 for checkpoint details)
- `--sample FLOAT` — process only a fraction of seeds, anchor PIs, and institutions (e.g., `0.1` = 10%). Useful for pipeline validation at ~10% of full cost
- `--dry-extract` — fetch and cache all HTML but skip LLM extraction. Allows iterating on extraction prompts against cached HTML without API costs

**Behavior for `--full`:**
1. Reads `SEMANTIC_SCHOLAR_KEY`, `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` from environment.
2. Creates a new `run_id` (UUID) and writes to `scrape_log` with `phase='init'`.
3. Runs phases 1–7 in sequence. Each phase writes to `scrape_log` on start and completion.
4. On completion, prints a final summary: total records by table, failed records, total time elapsed.

#### `gradradar db stats`

Displays database statistics.

```bash
gradradar db stats
```

**Output:**
```
gradradar database stats
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  institutions:         312
  departments:          489
  pis:                3,841
  papers:            42,103
  programs:             178
  program_courses:    2,341
  pi_students:        8,220
  workshops:             24

  Last build:         2026-03-15 09:41 UTC
  Schema version:     1.0
  Database size:      1.2 GB (single DuckDB file with FTS indexes)
  Stale records:      142 pis (is_taking_students > 30 days)
                       58 programs (deadline > 180 days)
  Manual review queue: 7 records
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### `gradradar db publish`

Pushes the local database to Cloudflare R2.

```bash
gradradar db publish
gradradar db publish --version 1.1
gradradar db publish --message "Updated is_taking_students for 140 PIs"
```

**Options:**
- `--version TEXT` — override the auto-computed version string
- `--message TEXT` — add a changelog note to manifest.json

**Behavior:**
1. Reads R2 credentials from environment: `CLOUDFLARE_R2_ACCOUNT_ID`, `CLOUDFLARE_R2_ACCESS_KEY_ID`, `CLOUDFLARE_R2_SECRET_ACCESS_KEY`, `CLOUDFLARE_R2_BUCKET_NAME`. Fails with a clear error if any are missing.

#### `gradradar db validate`

Runs a comprehensive data integrity check on the local database.

```bash
gradradar db validate
```

**Checks performed:**
- No orphaned foreign keys (e.g., `pi.department_id` points to a real department)
- No records with all-NULL non-key fields (garbage extraction artifacts)
- FTS indexes exist and return results for test queries
- No duplicate records by Semantic Scholar ID or OpenAlex ID
- `possible_duplicates` table summary: N pending, N merged, N distinct
- `update_queue` health: N pending, N failed, N manual_review
- Prints a pass/fail summary with actionable suggestions for each failure

#### `gradradar coverage`

Displays the topic distribution of the database, highlighting coverage gaps.

```bash
gradradar coverage
gradradar coverage --min 10    # only show topics with fewer than N PIs
```

**Output:**
```
gradradar topic coverage
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Geometric Deep Learning:         142 PIs
  Mechanistic Interpretability:     89 PIs
  Topological Data Analysis:        67 PIs
  Theoretical ML:                  234 PIs
  Reinforcement Learning:           23 PIs  ⚠ thin coverage
  NLP / Language Models:            18 PIs  ⚠ thin coverage
  Computer Vision:                  31 PIs  ⚠ thin coverage
  ...

  Topics with < 10 PIs:
  - Causal Inference (8)
  - Quantum ML (3)
  - Neurosymbolic AI (5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### `gradradar cache clear`

Clears local caches.

```bash
gradradar cache clear              # clear all caches
gradradar cache clear --html       # clear only raw HTML cache
gradradar cache clear --llm        # clear only LLM response cache
```

**Behavior:**
1. Deletes all files under the specified cache directory (`~/.gradradar/cache/raw_html/` for `--html`, `~/.gradradar/cache/llm_responses/` for `--llm`, or both for no flag).
2. Prints the number of files deleted and disk space reclaimed.

---

## 9. Session Workflow and Clarifying-Question System

### 9.1 Overview

The clarifying-question system is an **opt-in** feature activated by the `--clarify` flag on `gradradar search`. By default, searches run immediately using the query text + user profile with no interactive questions. This eliminates friction for users who know what they want, while preserving the option for deeper guided search when needed.

When activated, the session asks **at most 2 targeted questions** chosen dynamically based on the biggest ambiguity in the query. The LLM inspects the query and profile to determine which dimensions would most change the search results, and asks only about those.

Sessions are distinct from the profile. The profile captures long-lived facts about the user (background, interests, constraints). A session captures the specific intent of a single search run — it can override or narrow profile-level defaults without changing them.

Session state is ephemeral by default. It is not persisted between invocations.

### 9.2 Session Launch Flow

**Default (no `--clarify` flag):**
```
User: gradradar search "labs doing topological analysis of neural network representations in the UK"

gradradar
───────────────────────────────────────────────────────────────
  Searching pis + papers | filters: region=UK | hybrid mode
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:04
  Found 9 matching PhD labs in UK
───────────────────────────────────────────────────────────────
```

**With `--clarify` flag (opt-in guided search):**
```
User: gradradar search "labs doing topological analysis of neural network representations in the UK" --clarify

gradradar
───────────────────────────────────────────────────────────────
  Starting PhD search session.
  Profile loaded: PhD preferred | UK/US/Europe
  Press Enter with no input to remain general on any question.
───────────────────────────────────────────────────────────────

[Q1] Do you need the lab to be actively taking students for 2027?
     (yes / no / include unknowns)
  > yes

[Q2] How strongly do you want to filter for theoretical/math-heavy
     labs? (strictly theoretical / lean theoretical / no filter)
  > lean theoretical

───────────────────────────────────────────────────────────────
  Searching pis + papers | filters: region=UK, is_taking_students=yes, theory_category IN (theory, mixed) | hybrid mode
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:04
  Found 7 matching PhD labs in UK
───────────────────────────────────────────────────────────────
```

### 9.3 PhD Session Questions

When `--clarify` is used, the LLM selects **at most 2 questions** from the candidate pool below, choosing the questions whose answers would most change the search results given the query and profile. Questions are never asked if the query or profile already answers them.

**Candidate question pool:**

| Intent | Example question text | Signal if blank |
|---|---|---|
| Taking students | "Should results be restricted to PIs confirmed as taking students for 2027?" | `is_taking_students IN ('yes', 'unknown')` |
| Theory vs. empirical | "How strongly do you want to filter for theoretical/math-heavy labs? (strictly theoretical / lean theoretical / no filter)" | `theory_category` filter from profile.research_style, or no filter |
| Sub-topic focus | "Should I focus on mechanistic interp, geometric/topological DL, theoretical ML, or a combination?" | All sub-topics equally weighted |
| Career stage | "Career stage preference: assistant professor (building lab), senior established, or no preference?" | No SQL filter on career_stage |
| Publication recency | "Weight recent citation velocity heavily, or is an established body of work sufficient?" | No explicit citation_velocity ordering |
| Institution exclusions | "Any specific institutions to include or exclude?" | No institution filter |
| Industry connections | "Should I surface labs with strong industry connections?" | No industry_connections filter |

**Question selection logic:**
The LLM receives the query, the profile, and the candidate pool. It returns the 2 questions (or fewer) that would cause the largest change in the result set. For example, if the query is broad ("ML labs in UK") with no profile, the LLM typically picks "taking students?" and "theory vs. applied?" as the two highest-impact disambiguators.

**Blank answer handling:**
- Taking students blank: `is_taking_students IN ('yes', 'unknown')` — unknowns are included, not excluded.
- All other blanks: the corresponding SQL filter or ordering is omitted; the profile default applies.

### 9.4 Masters Session Questions

Same max-2 dynamic selection as PhD sessions. Candidate pool:

| Intent | Example question text | Signal if blank |
|---|---|---|
| Funding requirement | "Funding requirement: fully funded only, partial OK, or no filter?" | From profile.funding_requirement |
| Thesis vs. coursework | "Thesis track required, preferred, or no preference?" | No thesis_option filter |
| PhD pipeline intent | "Is a strong PhD placement rate important (i.e., using this Masters as a PhD springboard)?" | No percent_to_phd ordering |
| Topic focus | "Which topic area matters most: ML theory, applied ML, mathematics/stats, or a mix?" | All topics from profile.research_interests |
| Duration | "Preferred duration: 1 year, 2 years, or no preference?" | No duration filter |
| International funding | "Do you need the program to fund international students specifically?" | From profile.international_student |

### 9.5 Session Flags

```bash
gradradar search "query"                    # default: no questions, runs immediately
gradradar search "query" --clarify          # opt in to up to 2 clarifying questions
gradradar search "query" --clarify-all      # ask all candidate questions, not just top 2
gradradar search "query" --session-file /path/to/session.json  # load pre-answered session from file
gradradar session save last                 # save the answers from the last session to a JSON file
```

**Default (no flag):** No questions asked. Profile + query used directly. This is the standard behavior for most searches.

**`--session-file`** allows the user to pre-answer the clarifying questions in a JSON file and pass them in directly, bypassing the interactive prompt. Useful for repeating a search with minor variations. The session file format:

```json
{
  "type": "phd",
  "answers": {
    "q1_subtopic": "mechanistic interpretability, theoretical side",
    "q2_career_stage": null,
    "q3_taking_students": "yes",
    "q4_institutions": null,
    "q5_recency": "weight recent momentum",
    "q6_theory": "strictly theoretical",
    "q7_industry": null
  }
}
```

`null` values are treated identically to a blank Enter at the interactive prompt.

### 9.6 Session Context Injection

After the clarifying questions are answered, the session context is compiled into a structured object and merged with the profile before being passed to `llm_query.py`:

```python
class SessionContext(BaseModel):
    query_type: Literal["phd", "masters", "mixed"]
    raw_query: str
    clarifying_answers: Dict[str, Optional[str]]
    profile_snapshot: Dict        # full profile.json at time of session
    effective_constraints: Dict   # merged result of profile + session answers
```

The `effective_constraints` dict is what actually drives SQL filter generation. It is the profile's `constraints` section with any session-level overrides applied on top. For example:
- Extended profile says `gre: "prefer_not"` → SQL filter `gre_required IN ('no', 'optional')`
- Session says `"strictly theoretical"` → overrides profile default to `theory_category = 'theory'`
- Session says `"yes"` for taking students → overrides profile default to `is_taking_students = 'yes'` (excludes 'unknown')

This compiled context is written to `~/.gradradar/cache/last_session.json` so the user can inspect it or load it with `--session-file` on a subsequent search.

---

## 10. Cloudflare R2 Publishing and Versioning

### 10.1 Why R2

Cloudflare R2 is chosen over alternatives (HuggingFace Datasets, AWS S3, Google Cloud Storage) for the following reasons:

- **No egress fees.** Downloading the ~1.2 GB database costs nothing in transfer. S3 and GCS charge per GB downloaded; HuggingFace has rate limits on large dataset downloads.
- **S3-compatible API.** `boto3` works out of the box with a single `endpoint_url` override. No specialised SDK required.
- **Generous free tier.** 10 GB storage free, 1 million Class A operations/month (writes), 10 million Class B operations/month (reads). The gradradar database (~1.2 GB per version) fits comfortably within the free tier.
- **Simple public access.** R2 buckets can be made publicly accessible via a custom domain or the `*.r2.dev` subdomain with a single checkbox. No token required for downloads.
- **Fast globally.** R2 is served via Cloudflare's edge network, so downloads are fast regardless of user location.

The only trade-off vs. HuggingFace is the loss of community discoverability and the dataset card UI — neither of which matters for a personal tool.

### 10.2 Bucket Structure

The database is published to a single R2 bucket (name configurable via `CLOUDFLARE_R2_BUCKET_NAME`). The bucket is made **publicly readable** (no auth required for GET). Writes require R2 API credentials.

```
[bucket-name]/
├── latest/
│   └── manifest.json          # always points to the latest published version
├── v1.0/
│   ├── gradradar.duckdb       # ~1.2 GB (includes FTS indexes)
│   ├── manifest.json          # version-specific manifest
│   └── migrations/            # incremental schema migration SQL files
├── v1.1/
│   ├── gradradar.duckdb
│   ├── manifest.json
│   └── migrations/
└── ...
```

`latest/manifest.json` contains only the `latest_version` pointer and a checksum of the version-specific manifest:

```json
{
  "latest_version": "v1.1",
  "manifest_url": "https://[public-url]/v1.1/manifest.json",
  "published_at": "2026-03-15T09:41:00Z"
}
```

Old versions are retained in the bucket indefinitely. The user can pin a specific version with `gradradar init --version v1.0`.

### 10.3 Manifest Schema

Each version directory contains a `manifest.json` with the following fields:

```json
{
  "schema_version": "1.0",
  "tool_version": "0.1.4",
  "build_date": "2026-03-15T09:41:00Z",
  "build_duration_hours": 16.2,
  "record_counts": {
    "institutions": 312,
    "departments": 489,
    "pis": 3841,
    "papers": 42103,
    "programs": 178,
    "program_courses": 2341,
    "topics": 94,
    "workshops": 24,
    "pi_students": 8220
  },
  "ttl_days": 90,
  "search_engine": "duckdb_fts",
  "changelog": "",
  "files": {
    "gradradar.duckdb": {
      "size_bytes": 1288490188,
      "sha256": "abc123..."
    }
  }
}
```

### 10.4 Version Compatibility and Schema Migrations

**Schema version** is a `MAJOR.MINOR` string:
- `MAJOR` increments on breaking schema changes (columns removed, column types changed, tables restructured). Users must re-run `gradradar init --force` to upgrade.
- `MINOR` increments on non-breaking additions (new optional columns, new tables that do not affect existing queries). These are handled via **incremental migrations**.

**Incremental migrations:**
Each minor version bump includes numbered SQL migration files stored in the R2 bucket alongside the database:
```
[bucket]/v1.1/migrations/
├── 001_add_taking_students_confidence.sql
├── 002_add_possible_duplicates_table.sql
└── 003_add_citation_velocity_source.sql
```

A `schema_migrations` table in DuckDB tracks which migrations have been applied:
```sql
CREATE TABLE schema_migrations (
    migration_id    TEXT PRIMARY KEY,
    applied_at      TIMESTAMP DEFAULT current_timestamp
);
```

When `gradradar init --pull` detects a minor version bump, it downloads and applies only the migration files between the local schema version and the remote version, rather than re-downloading the entire 2 GB database. For DuckDB, non-breaking migrations are typically `ALTER TABLE ADD COLUMN` statements that execute in milliseconds.

**Startup check:**
On startup, `gradradar` fetches `latest/manifest.json` from R2 (a single lightweight HEAD/GET, ~500 bytes) and compares it to the local `~/.gradradar/db/manifest.json`:
- If `schema_version` MAJOR differs from the local schema: prints an error and exits, instructing the user to run `gradradar init --force`.
- If the local `build_date` is older than `ttl_days`: prints a warning and suggests running `gradradar update`.
- If the remote `latest_version` is newer than the local version: prints a notice and suggests running `gradradar init --pull` to upgrade.

The startup check can be suppressed with `--offline` flag.

### 10.5 Download Behavior (`gradradar init`)

`gradradar init` downloads the database files using `httpx` with direct HTTPS GET against the public R2 bucket URL. No authentication is required for downloads.

```
Public base URL: https://[CLOUDFLARE_R2_PUBLIC_URL]/
Files downloaded:
  GET /[version]/manifest.json       (~2 KB)
  GET /[version]/gradradar.duckdb    (~1.2 GB, includes FTS indexes)
```

**Download implementation:**
- The database is a single file download (~1.2 GB) — no separate vector database to manage.
- File is downloaded in streaming mode (chunked) with a progress bar via `rich`.
- Downloads resume automatically if interrupted: `httpx` sends a `Range` header on retry, and R2 honours it natively.
- SHA-256 checksum from `manifest.json` is verified after download completes. On checksum failure, the file is deleted and re-downloaded (up to 3 retries).
- On completion, `manifest.json` is written to `~/.gradradar/db/manifest.json`.

**Partial upgrade (`gradradar init --pull`):**
If only a minor version bump is detected and the DuckDB schema is compatible, `gradradar init --pull` downloads only the files whose SHA-256 has changed since the locally installed version, skipping unchanged files.

### 10.6 Upload Behavior (`gradradar db publish`)

Publishing requires R2 write credentials (not needed for search-only use). The `gradradar db publish` command uses `boto3` with the Cloudflare R2 S3-compatible endpoint:

```python
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=CLOUDFLARE_R2_ACCESS_KEY_ID,
    aws_secret_access_key=CLOUDFLARE_R2_SECRET_ACCESS_KEY,
)
```

**Upload steps:**
1. Compute SHA-256 of `gradradar.duckdb`.
2. Determine the next version string (auto-increment MINOR, or use `--version` override).
3. Write `manifest.json` with the new version metadata.
4. Upload `gradradar.duckdb` and `manifest.json` to `[bucket]/[version]/` using multipart upload (chunk size: 64 MB).
5. If there are schema migrations since the last published version, upload the migration SQL files to `[bucket]/[version]/migrations/`.
6. Update `[bucket]/latest/manifest.json` to point to the new version.
7. Print the public URL: `https://[CLOUDFLARE_R2_PUBLIC_URL]/[version]/manifest.json`.

---

## 11. Update and Refresh Mechanism

### 11.0 Command Overview

Three commands manage the lifecycle of the database after the initial build. They are independent and serve distinct purposes:

| Command | Frequency | What it does |
|---|---|---|
| `gradradar update` | Monthly | Refreshes stale existing records using TTL rules + content hash comparison |
| `gradradar discover` | Every 6 months | Finds new PIs and programs not yet in the database |
| `gradradar build --full` | Once (initial) | Cold rebuild of the entire database from scratch |

`gradradar update` never runs discovery logic. `gradradar discover` never re-scrapes existing records. Both commands are safe to run independently and in any order.

### 11.1 TTL-Based Staleness

Every record in DuckDB has a `scraped_at` TIMESTAMP. Records are considered stale based on the following TTLs:

| Field / Record Type                     | TTL       |
|-----------------------------------------|-----------|
| `pis.is_taking_students`                | 30 days   |
| `pis.h_index`, `pis.total_citations`   | 90 days   |
| `pis.citation_velocity`                | 90 days   |
| `programs.*` (all program fields)      | 180 days  |
| `departments.phd_funding_guarantee`    | 180 days  |
| `departments.application_deadline`    | 180 days  |
| `papers.*` (all paper fields)          | 365 days  |
| `institutions.*`                       | 365 days  |

The `gradradar update` command queries for records where `scraped_at < now() - interval '[TTL]'` and adds them to the update queue.

### 11.2 Content Hash Deduplication

Every record stores a `content_hash` computed as the SHA-256 of the raw HTML body of its `source_url`. When the update pipeline re-fetches a stale URL:
- If the content hash is unchanged: update `scraped_at` to now, no extraction needed.
- If the content hash changed: re-extract all fields and update the record in DuckDB. FTS indexes are rebuilt at the end of the update run.

This means the update pipeline does network requests for all stale records but only performs expensive LLM extraction for records where content actually changed.

### 11.3 Snapshot-Before-Update

Before any update run, `gradradar` creates a snapshot:
```
~/.gradradar/db/snapshots/gradradar_YYYY-MM-DD.duckdb
```

Snapshots are retained for 30 days and then automatically deleted. If an update run fails or corrupts data, the user can manually restore by copying a snapshot back to `~/.gradradar/db/gradradar.duckdb`. Since the entire database (including FTS indexes) is a single file, snapshots are a complete point-in-time recovery mechanism.

### 11.4 Web Search Feedback Loop

When `web_search.py` finds a PI or program not in the database during a search session, it writes a stub record to `update_queue` with `reason='discovered_via_web_search'` and `priority=3`. The `web_searches` table also logs the session, trigger reason, and count of records queued.

The next time `gradradar discover` runs, it checks `update_queue` for pending records (in addition to its active discovery methods) and enriches any web-discovered stubs into full records using the standard scraping + LLM extraction pipeline.

This creates a passive improvement loop: users doing searches inadvertently expand the database over time without taking any explicit action. The database gets more complete with each search session.

Users can inspect the queue at any time with `gradradar db stats`, which shows a count of web-discovered records pending enrichment.

### 11.5 Manual Review Queue

Records that fail LLM extraction after 3 retries are written to `update_queue` with `status='manual_review'`. The user can view these with:
```bash
gradradar db stats
```
And inspect them manually or re-queue them for re-processing after fixing the source URL.

---

## 12. Dependencies and Setup Instructions

### 11.1 Python Dependencies

All dependencies are declared in `pyproject.toml`:

```toml
[project]
name = "gradradar"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "duckdb>=0.10.0",               # relational DB + FTS extension (built-in)
    "httpx>=0.27.0",
    "playwright>=1.44.0",
    "pdfplumber>=0.11.0",
    "instructor>=1.3.0",
    "litellm>=1.40.0",
    "beautifulsoup4>=4.12.0",
    "readability-lxml>=0.8.0",      # HTML content extraction / preprocessing
    "trafilatura>=1.8.0",           # fallback HTML content extraction
    "pydantic>=2.7.0",
    "boto3>=1.34.0",  # S3-compatible client for Cloudflare R2
    "click>=8.1.0",
    "rich>=13.7.0",
    "duckduckgo-search>=6.0.0",   # web search provider (no API key required)
]

[project.scripts]
gradradar = "gradradar.cli:main"
```

### 11.2 Installation

**Standard install (search only, no build):**
```bash
pip install gradradar
playwright install chromium   # required for JS-rendered page fallback
gradradar init                # downloads database from Cloudflare R2 (~1.2 GB, single file)
gradradar search "your query" # works immediately — no profile required

# Optional: personalize results
gradradar profile setup       # 5-field quick setup for personalized match explanations
```

**Developer install (with build capability):**
```bash
git clone https://github.com/[username]/gradradar
cd gradradar
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
# Fill in .env with your API keys
```

### 12.3 Contribution and Bus Factor Mitigation

The build and publish process is documented end-to-end in `CONTRIBUTING.md` so that any contributor can run the pipeline and publish an updated database. This ensures the project does not depend on a single maintainer.

**CI validation:**
A GitHub Action runs `gradradar build --full --sample 0.1` on every PR that modifies pipeline code (files under `gradradar/build/`, `seeds/`, or `gradradar/db/`). This validates that pipeline changes don't break the build without incurring full build costs (~$9 per CI run).

**Community seed contributions:**
The `seeds/` directory accepts PRs. Each seed file includes a JSON schema that is validated in CI. Adding a new institution, workshop, or anchor PI requires only a JSON edit — no Python code changes. The `CONTRIBUTING.md` documents what makes a good seed entry:
- Institutions: must have a discoverable faculty listing page
- Workshops: must have a publicly accessible speaker/organizer list
- Anchor PIs: must have a Semantic Scholar profile with ≥10 papers

**Data validation before publish:**
`gradradar db validate` (see Section 8.3) must pass before `gradradar db publish` will proceed. This prevents publishing a corrupted or incomplete database.

### 11.3 API Keys

All API keys are read from the environment. The recommended approach is to create a `.env` file at the project root (never committed to git) and load it with `python-dotenv` or a shell `source` command.

```bash
# .env.example
SEMANTIC_SCHOLAR_KEY=           # Free at https://www.semanticscholar.org/product/api
                                 # Required for build; not required for search
ANTHROPIC_API_KEY=              # Required for LLM extraction (build) and query translation (search)
                                 # Alternatively: OPENAI_API_KEY

# Cloudflare R2 — required only for gradradar db publish (not needed for search or init)
CLOUDFLARE_R2_ACCOUNT_ID=       # Found at dash.cloudflare.com → R2 → Overview
CLOUDFLARE_R2_ACCESS_KEY_ID=    # R2 API token → "R2 Token" → Access Key ID
CLOUDFLARE_R2_SECRET_ACCESS_KEY=# R2 API token → Secret Access Key
CLOUDFLARE_R2_BUCKET_NAME=      # Name of your R2 bucket (e.g., "gradradar-db")
CLOUDFLARE_R2_PUBLIC_URL=       # Public URL of bucket (e.g., https://gradradar.example.com
                                 # or https://pub-xxxx.r2.dev if using r2.dev subdomain)
```

**Key acquisition:**
- **Semantic Scholar API key:** Register at `https://www.semanticscholar.org/product/api`. The free tier provides 10 req/sec.
- **Anthropic API key:** Register at `https://console.anthropic.com`. The build pipeline costs approximately $31–$40 at current pricing.
- **OpenAI API key (alternative):** Register at `https://platform.openai.com`. Costs are comparable.
- **Cloudflare R2:** Create a free Cloudflare account at `https://dash.cloudflare.com`, navigate to R2, create a bucket, and generate an API token with "Object Read & Write" permissions. Enable public access on the bucket (either via custom domain or the free `*.r2.dev` subdomain). R2 write credentials are required only for `gradradar db publish`; `gradradar init` uses only the public URL and needs no auth.

### 11.4 System Requirements

- **Python:** 3.11 or higher
- **OS:** Linux, macOS, or Windows (WSL recommended on Windows for playwright compatibility)
- **Disk space:** ~1.2 GB for the database (`gradradar.duckdb`, single file with FTS indexes)
- **RAM:** Minimum 4 GB available for search; 8 GB recommended for build pipeline
- **Build-only network:** Requires access to `api.semanticscholar.org`, `api.openalex.org`, and target institution domains. Does not require VPN.

### 11.5 Environment Variables Reference

| Variable | Required For | Default |
|---|---|---|
| `SEMANTIC_SCHOLAR_KEY` | Build (Phase 1) | None (falls back to 1 req/sec) |
| `ANTHROPIC_API_KEY` | Build + Search | None |
| `OPENAI_API_KEY` | Build + Search (alternative) | None |
| `CLOUDFLARE_R2_ACCOUNT_ID` | `gradradar db publish` | None |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | `gradradar db publish` | None |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | `gradradar db publish` | None |
| `CLOUDFLARE_R2_BUCKET_NAME` | `gradradar db publish` | None |
| `CLOUDFLARE_R2_PUBLIC_URL` | `gradradar init` + Publish | None |
| `GRADRADAR_DB_PATH` | All | `~/.gradradar/db/` |
| `GRADRADAR_LLM_MODEL` | Build + Search | `claude-3-5-sonnet-latest` |
| `GRADRADAR_WEB_SEARCH` | Search | `true` (set to `false` to disable globally) |

---

## 13. Estimated Costs and Build Time

### 12.1 Build Time by Phase

| Phase | Description | Estimated Duration |
|---|---|---|
| Phase 1 | Semantic Scholar API ingestion | 6–8 hours |
| Phase 2 | OpenAlex API ingestion | 1–2 hours |
| Phase 3 | Department page scraping | ~30 minutes |
| Phase 4 | PI page scraping | 3–4 hours |
| Phase 5 | Program page scraping | ~20 minutes |
| Phase 6 | Workshop page scraping | ~10 minutes |
| Phase 7 | FTS index creation | <1 minute |
| **Total cold build** | | **11–15 hours** |

Phase durations assume:
- Semantic Scholar API key (10 req/sec)
- A machine with stable broadband internet connection
- Anthropic claude-3-5-haiku as the extraction model

### 12.2 API Cost Estimates (Cold Build)

| Cost Component | Estimate |
|---|---|
| LLM extraction — PI pages (~4,000 pages × ~5K tokens) | ~$20 |
| LLM extraction — program pages (~200 pages × ~8K tokens) | ~$4 |
| LLM extraction — dept faculty pages (~500 pages × ~3K tokens) | ~$6 |
| LLM extraction — workshop pages (~50 pages × ~3K tokens) | ~$1 |
| FTS index creation | $0 (built-in DuckDB) |
| Query translation (search-time, not build) | ~$0.01 per query |
| **Total cold build** | **~$31–$40** |

Cost estimates based on Anthropic claude-3-5-haiku pricing as of April 2026. OpenAI gpt-4o-mini is a comparable alternative at similar cost.

**Development build cost (`--sample 0.1`):** ~$3-4 (10% of seeds processed). Useful for pipeline validation before committing to a full build. LLM response caching further reduces costs on re-runs with unchanged content.

**Note:** Replacing ChromaDB embeddings with DuckDB full-text search eliminated ~$43 in embedding API costs per build (previously the single most expensive component at ~50% of total build cost).

### 12.3 Differential Update Costs

A typical monthly update refreshing stale `is_taking_students` fields (~600 PI pages), citation counts (~1,000 API calls), and program deadlines (~50 pages):
- Network: ~650 page fetches
- LLM extraction (content-changed pages only, ~30% of fetches): ~$3–$5
- FTS index rebuild: $0 (<1 minute, no API calls)
- **Total monthly update: ~$3–$5**

### 12.4 Search Cost

Each search query requires:
- 1 LLM call for query translation (including keyword expansion for FTS): ~$0.003 (Sonnet)
- DuckDB FTS query: $0 (local, <100ms)
- 1 LLM call for re-ranking and explanation generation (~5K tokens): ~$0.015
- **Total per search query: ~$0.018**

---

## 14. Known Limitations and Future Work

### 13.1 Known Limitations

**Coverage limitations:**
- **Seed data bias:** v1.0 has strongest coverage in geometric deep learning, topological data analysis, and mechanistic interpretability — the areas seeded by the anchor PIs and seed papers. Other areas (NLP, reinforcement learning, computer vision) have thinner coverage. Use `gradradar coverage` to see the current topic distribution and identify gaps. Community contributions to the `seeds/` directory are welcome to broaden coverage (see `CONTRIBUTING.md`).
- Faculty at institutions not in `seeds/institutions.json` are only discoverable via citation graph or workshop seeding. Researchers at smaller institutions may be missed.
- Faculty with non-English-language personal pages may not extract cleanly. LLM extraction quality degrades on non-English HTML.
- Research institutes and industry labs (e.g., INRIA, MPI, DeepMind) are included in the discovery pipeline but their "taking students" signal is less reliable since they do not always recruit PhD students directly.
- Very new PIs (first year on faculty) may not have personal pages with sufficient content for reliable LLM extraction.

**Data quality limitations:**
- `is_taking_students` is the most time-sensitive and frequently incorrect field. It now includes a confidence score and a "checked at" timestamp. Users should always verify directly with the PI — the output card always displays "Verify directly" regardless of confidence.
- `theory_category` is derived from venue distribution when ≥5 papers are available (deterministic and reproducible). For PIs with fewer papers, it falls back to LLM assignment which may be less consistent. The `theory_category_source` field indicates which method was used.
- `citation_velocity` excludes self-citations and flags single-paper-driven velocity as `depth`, but the underlying citation data from Semantic Scholar may have a lag of several weeks.
- Stipend data is scraped from department pages, which often publish ranges rather than exact figures, and may be 1–2 years out of date.
- Email addresses are extracted opportunistically from personal pages but are not always present. No email scraping from contact forms is performed.
- Name disambiguation uses API-sourced IDs (Semantic Scholar, OpenAlex) as the primary dedup key. Near-matches that fall between thresholds are logged in `possible_duplicates` for human review. Some false merges or missed duplicates are inevitable with common names.

**Search limitations:**
- The hybrid search returns ranked results with improved ordering stability via `temperature=0` and result caching (24h TTL). However, cache misses or changes to the candidate set will produce different rankings.
- SQL filters are translated by the LLM and may be imperfect for very complex multi-condition queries. Use `--explain` to inspect the generated query plan and `--mode sql` for direct control.
- Full-text search (BM25) matches on keywords, not meaning. Queries where no keywords overlap with the target text (e.g., "representation geometry" matching "manifold structure of activations") require the LLM re-ranker to bridge the gap. The LLM query translator mitigates this by expanding queries with synonyms and related terms, but some semantic misses are inevitable compared to embedding-based search. If FTS proves insufficient for specific query patterns in practice, embedding-based search can be added in a future version.
- Web search results pass through a quality gate (name + institution + resolvable URL required) but are still unverified and should be treated as leads rather than authoritative data. Maximum 10 web-discovered records are queued per session.
- The web search feedback loop is passive — records queued via web search are only enriched the next time `gradradar discover` is run. They do not automatically enrich in the background.

**Build pipeline limitations:**
- The build pipeline supports within-phase checkpointing (every 500 records) so `--resume` can continue from mid-phase. However, some edge cases around partial writes may still result in duplicate records requiring dedup.
- robots.txt compliance means some department faculty pages that disallow crawling will be skipped. Their faculty will only be discovered via citation graph or workshop seeding.
- The 11–15 hour build time is not easily parallelizable without significant architectural changes, as Semantic Scholar rate limits bottleneck Phase 1. Use `--sample 0.1` for faster iteration during development.
- LLM extraction from arbitrary HTML remains inherently fragile despite preprocessing with `readability-lxml`/`trafilatura`. The extraction confidence check (>50% null fields → skip) mitigates garbage writes, but some low-quality records will still be created.

### 13.2 Future Work

The following items are out of scope for v1.0 but are planned for future versions:

**v1.1:**
- Add a `gradradar export` command that generates a structured CSV or JSON export of search results, useful for building application tracking spreadsheets.
- Add `pi_media` population: scrape known PI blog pages, YouTube talks, and Twitter/X threads to populate the `pi_media` table and surface application advice.
- Add explicit lab alumni placement summaries per PI to the phd_pi output card.

**v1.2:**
- Web interface: a simple local Flask/FastAPI server that serves the search UI in a browser, enabling richer result visualization (institution map, topic clustering).
- Cowork plugin: expose gradradar search as a Cowork tool so users can query from within a Cowork session without the CLI.
- Add `department_culture` population from aggregated PI theory scores and venue data.

**v2.0:**
- Real-time integration: instead of a static snapshot database, maintain a live-updating version by running the differential update pipeline on a nightly schedule and keeping the Cloudflare R2 bucket current.
- Embedding-based search: if FTS proves insufficient for specific query patterns (e.g., purely conceptual queries with no keyword overlap), add optional embedding support using DuckDB array columns with exact nearest-neighbor search. This would complement FTS rather than replace it, and would be stored in the same DuckDB file.
- Multi-modal search: support uploading a PDF paper and extracting its key concepts as FTS search terms ("find labs doing work similar to this paper I'm attaching").
- Advisor recommendation scoring: generate a composite compatibility score between the user's profile and each PI, weighted by research fit, career stage preference, location, and funding situation.
- Statement of purpose preparation: given a set of target PIs selected by the user, generate a personalized summary of each PI's research that can be used as input to SOP drafting.

---

*End of GRADRADAR Product Requirements Document v1.0*

*This document is sufficient to implement gradradar end-to-end. All design decisions are specified. Ambiguous implementation details (e.g., exact LLM prompts) should be implemented with engineering judgment consistent with the constraints described.*
