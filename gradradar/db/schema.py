"""DuckDB schema definitions, FTS indexes, and migrations."""

import duckdb
from pathlib import Path


# All CREATE TABLE statements in dependency order
SCHEMA_SQL = """
-- 1. institutions
CREATE TABLE IF NOT EXISTS institutions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 2. departments (depends on institutions)
CREATE TABLE IF NOT EXISTS departments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 3. pis (depends on departments, institutions, self-referential)
CREATE TABLE IF NOT EXISTS pis (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 4. pi_students
CREATE TABLE IF NOT EXISTS pi_students (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 5. pi_industry_connections
CREATE TABLE IF NOT EXISTS pi_industry_connections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pi_id               UUID REFERENCES pis(id),
    organization        TEXT,
    connection_type     TEXT CHECK (connection_type IN (
                            'joint_paper', 'grant',
                            'internship_pipeline', 'advisory')),
    details             TEXT,
    year                INTEGER
);

-- 6. pi_media
CREATE TABLE IF NOT EXISTS pi_media (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 7. pi_research_trajectory
CREATE TABLE IF NOT EXISTS pi_research_trajectory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pi_id           UUID REFERENCES pis(id),
    year_bucket     INTEGER,
    topic           TEXT,
    paper_count     INTEGER,
    citation_count  INTEGER
);

-- 8. papers
CREATE TABLE IF NOT EXISTS papers (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title                       TEXT NOT NULL,
    abstract                    TEXT,
    year                        INTEGER,
    venue                       TEXT,
    citation_count              INTEGER,
    citation_count_last_2_years INTEGER,
    citation_velocity           FLOAT,
    doi                         TEXT,
    arxiv_id                    TEXT,
    openalex_id                 TEXT,
    semantic_scholar_id         TEXT,
    fields_of_study             TEXT,
    url                         TEXT
);

-- 9. author_paper
CREATE TABLE IF NOT EXISTS author_paper (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id           UUID REFERENCES pis(id),
    paper_id            UUID REFERENCES papers(id),
    author_position     TEXT CHECK (author_position IN ('first', 'last', 'middle')),
    is_corresponding    BOOLEAN
);

-- 10. citations
CREATE TABLE IF NOT EXISTS citations (
    citing_paper_id     UUID REFERENCES papers(id),
    cited_paper_id      UUID REFERENCES papers(id),
    PRIMARY KEY (citing_paper_id, cited_paper_id)
);

-- 11. topics
CREATE TABLE IF NOT EXISTS topics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL UNIQUE,
    parent_id           UUID REFERENCES topics(id),
    description         TEXT,
    canonical_paper_ids TEXT
);

-- 12. pi_topics
CREATE TABLE IF NOT EXISTS pi_topics (
    pi_id               UUID REFERENCES pis(id),
    topic_id            UUID REFERENCES topics(id),
    confidence_score    FLOAT,
    evidence_paper_ids  TEXT,
    PRIMARY KEY (pi_id, topic_id)
);

-- 13. paper_topics
CREATE TABLE IF NOT EXISTS paper_topics (
    paper_id            UUID REFERENCES papers(id),
    topic_id            UUID REFERENCES topics(id),
    confidence_score    FLOAT,
    PRIMARY KEY (paper_id, topic_id)
);

-- 14. programs
CREATE TABLE IF NOT EXISTS programs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 15. program_courses
CREATE TABLE IF NOT EXISTS program_courses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id          UUID REFERENCES programs(id),
    course_name         TEXT NOT NULL,
    course_description  TEXT,
    is_required         BOOLEAN,
    topic_tags          TEXT
);

-- 16. program_admissions_profile
CREATE TABLE IF NOT EXISTS program_admissions_profile (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 17. workshops
CREATE TABLE IF NOT EXISTS workshops (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    parent_conference   TEXT,
    year                INTEGER,
    url                 TEXT,
    topic_focus         TEXT,
    scraped_at          TIMESTAMP
);

-- 18. pi_workshops
CREATE TABLE IF NOT EXISTS pi_workshops (
    pi_id           UUID REFERENCES pis(id),
    workshop_id     UUID REFERENCES workshops(id),
    role            TEXT CHECK (role IN ('speaker', 'organizer', 'panelist')),
    PRIMARY KEY (pi_id, workshop_id)
);

-- 19. research_groups
CREATE TABLE IF NOT EXISTS research_groups (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    institution_id      UUID REFERENCES institutions(id),
    member_pi_ids       TEXT,
    lab_url             TEXT,
    research_focus      TEXT,
    funding_source      TEXT
);

-- 20. department_culture
CREATE TABLE IF NOT EXISTS department_culture (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 21. co_advising_relationships
CREATE TABLE IF NOT EXISTS co_advising_relationships (
    pi_id_1         UUID REFERENCES pis(id),
    pi_id_2         UUID REFERENCES pis(id),
    student_name    TEXT,
    year            INTEGER,
    PRIMARY KEY (pi_id_1, pi_id_2, student_name)
);

-- 22. possible_duplicates
CREATE TABLE IF NOT EXISTS possible_duplicates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 23. scrape_log
CREATE TABLE IF NOT EXISTS scrape_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    records_added   INTEGER,
    records_updated INTEGER,
    records_failed  INTEGER,
    phase           TEXT,
    command         TEXT,
    notes           TEXT
);

-- 24. web_searches
CREATE TABLE IF NOT EXISTS web_searches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          TEXT,
    triggered_at        TIMESTAMP,
    user_query          TEXT,
    trigger_reason      TEXT CHECK (trigger_reason IN (
                            'named_pi_query', 'taking_students_query',
                            'recent_paper_query', 'thin_results_fallback',
                            'explicit_user_request')),
    constructed_queries TEXT,
    results_found       INTEGER,
    new_pis_queued      INTEGER,
    new_programs_queued INTEGER,
    raw_results         TEXT
);

-- 25. update_queue
CREATE TABLE IF NOT EXISTS update_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_type     TEXT,
    record_id       UUID,
    source_url      TEXT,
    priority        INTEGER,
    reason          TEXT,
    queued_at       TIMESTAMP,
    processed_at    TIMESTAMP,
    status          TEXT CHECK (status IN ('pending', 'pending_verification', 'completed', 'failed', 'manual_review'))
);

-- 26. schema_migrations
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id    TEXT PRIMARY KEY,
    applied_at      TIMESTAMP DEFAULT current_timestamp
);
"""

# Expected table names for validation
ALL_TABLES = [
    "institutions", "departments", "pis", "pi_students",
    "pi_industry_connections", "pi_media", "pi_research_trajectory",
    "papers", "author_paper", "citations", "topics", "pi_topics",
    "paper_topics", "programs", "program_courses", "program_admissions_profile",
    "workshops", "pi_workshops", "research_groups", "department_culture",
    "co_advising_relationships", "possible_duplicates", "scrape_log",
    "web_searches", "update_queue", "schema_migrations",
]

# Expected column counts per table (for validation)
TABLE_COLUMN_COUNTS = {
    "institutions": 14,
    "departments": 17,
    "pis": 35,
    "pi_students": 11,
    "pi_industry_connections": 6,
    "pi_media": 9,
    "pi_research_trajectory": 6,
    "papers": 14,
    "author_paper": 5,
    "citations": 2,
    "topics": 5,
    "pi_topics": 4,
    "paper_topics": 3,
    "programs": 32,
    "program_courses": 6,
    "program_admissions_profile": 10,
    "workshops": 7,
    "pi_workshops": 3,
    "research_groups": 7,
    "department_culture": 10,
    "co_advising_relationships": 4,
    "possible_duplicates": 12,
    "scrape_log": 10,
    "web_searches": 10,
    "update_queue": 9,
    "schema_migrations": 2,
}


def create_schema(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Create all tables in DuckDB. Returns the connection."""
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA_SQL)
    # Record the initial schema creation as a migration
    con.execute("""
        INSERT INTO schema_migrations (migration_id)
        SELECT 'v1_initial_schema'
        WHERE NOT EXISTS (
            SELECT 1 FROM schema_migrations WHERE migration_id = 'v1_initial_schema'
        )
    """)
    return con


def create_fts_indexes(con: duckdb.DuckDBPyConnection):
    """Install FTS extension and create full-text search indexes.

    Requires data in the tables to be useful, but safe to call on empty tables.
    """
    con.execute("INSTALL fts;")
    con.execute("LOAD fts;")

    # PI search documents view
    con.execute("""
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
    """)

    # Program search documents view
    con.execute("""
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
    """)

    # Create FTS indexes on papers
    con.execute("PRAGMA create_fts_index('papers', 'id', 'title', 'abstract', overwrite=1);")

    # FTS on PI search docs — requires materializing the view first
    # DuckDB FTS works on tables, not views, so we create temp tables
    con.execute("CREATE OR REPLACE TABLE pi_search_docs_fts AS SELECT * FROM pi_search_docs;")
    con.execute(
        "PRAGMA create_fts_index('pi_search_docs_fts', 'id', 'name', "
        "'research_description', 'top_paper_titles', overwrite=1);"
    )

    # FTS on program search docs
    con.execute("CREATE OR REPLACE TABLE program_search_docs_fts AS SELECT * FROM program_search_docs;")
    con.execute(
        "PRAGMA create_fts_index('program_search_docs_fts', 'id', 'name', "
        "'course_text', 'notable_phd_placements', 'industry_placements', overwrite=1);"
    )


def get_table_names(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Return list of user table names in the database."""
    rows = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
    return [r[0] for r in rows]


def get_column_count(con: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Return number of columns in a table."""
    rows = con.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = 'main' AND table_name = ?",
        [table_name],
    ).fetchone()
    return rows[0]


def get_row_count(con: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Return number of rows in a table."""
    return con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]


def validate_schema(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Run integrity checks on the schema. Returns list of error messages (empty = all good)."""
    errors = []
    existing_tables = get_table_names(con)

    # Check all expected tables exist
    for table in ALL_TABLES:
        if table not in existing_tables:
            errors.append(f"Missing table: {table}")

    # Check column counts
    for table, expected_count in TABLE_COLUMN_COUNTS.items():
        if table in existing_tables:
            actual = get_column_count(con, table)
            if actual != expected_count:
                errors.append(f"Table {table}: expected {expected_count} columns, got {actual}")

    # Check for orphaned foreign keys (non-null FK pointing to non-existent parent)
    fk_checks = [
        ("departments", "institution_id", "institutions", "id"),
        ("pis", "department_id", "departments", "id"),
        ("pis", "institution_id", "institutions", "id"),
        ("pi_students", "pi_id", "pis", "id"),
        ("pi_industry_connections", "pi_id", "pis", "id"),
        ("pi_media", "pi_id", "pis", "id"),
        ("pi_research_trajectory", "pi_id", "pis", "id"),
        ("author_paper", "author_id", "pis", "id"),
        ("author_paper", "paper_id", "papers", "id"),
        ("programs", "institution_id", "institutions", "id"),
        ("programs", "department_id", "departments", "id"),
        ("program_courses", "program_id", "programs", "id"),
        ("program_admissions_profile", "program_id", "programs", "id"),
        ("pi_workshops", "pi_id", "pis", "id"),
        ("pi_workshops", "workshop_id", "workshops", "id"),
        ("research_groups", "institution_id", "institutions", "id"),
        ("department_culture", "department_id", "departments", "id"),
    ]
    for child_table, fk_col, parent_table, parent_pk in fk_checks:
        if child_table in existing_tables and parent_table in existing_tables:
            count = con.execute(f"""
                SELECT COUNT(*) FROM "{child_table}" c
                WHERE c."{fk_col}" IS NOT NULL
                AND c."{fk_col}" NOT IN (SELECT "{parent_pk}" FROM "{parent_table}")
            """).fetchone()[0]
            if count > 0:
                errors.append(f"Orphaned FK: {child_table}.{fk_col} has {count} rows pointing to non-existent {parent_table}")

    # Check for duplicate IDs in primary key tables
    for table in ALL_TABLES:
        if table in existing_tables and table not in ("citations", "pi_topics", "paper_topics", "pi_workshops", "co_advising_relationships", "schema_migrations"):
            dup_count = con.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT id, COUNT(*) as cnt FROM "{table}" GROUP BY id HAVING cnt > 1
                )
            """).fetchone()[0]
            if dup_count > 0:
                errors.append(f"Duplicate IDs in {table}: {dup_count} duplicates")

    return errors
