-- gradradar cloud v0: core PI / institution / department tables.
-- Port of the 3-table seed from gradradar/db/schema.py. Papers / author_paper /
-- citations are deliberately deferred — see the plan at
-- ~/.claude/plans/majestic-herding-marshmallow.md

-- ---------------------------------------------------------------------------
-- 1. institutions
-- ---------------------------------------------------------------------------
create table public.institutions (
    id                  uuid primary key default gen_random_uuid(),
    name                text not null,
    country             text,
    region              text check (region in ('US', 'UK', 'Europe')),
    city                text,
    type                text check (type in ('university', 'research_institute', 'industry_lab')),
    qs_cs_ranking       integer,
    us_news_ranking     integer,
    shanghai_ranking    integer,
    prestige_tier       integer check (prestige_tier in (1, 2, 3)),
    url                 text,
    scraped_at          timestamptz,
    content_hash        text,
    source_url          text
);

-- ---------------------------------------------------------------------------
-- 2. departments
-- ---------------------------------------------------------------------------
create table public.departments (
    id                      uuid primary key default gen_random_uuid(),
    institution_id          uuid references public.institutions(id),
    name                    text not null,
    field                   text check (field in ('CS', 'Math', 'Statistics', 'ECE', 'CogSci', 'Physics', 'Other')),
    phd_cohort_size         integer,
    phd_acceptance_rate     double precision,
    phd_funding_guarantee   boolean,
    phd_funding_years       integer,
    phd_average_stipend     integer,
    admission_type          text check (admission_type in ('rotation', 'direct', 'both')),
    application_deadline    text,
    gre_required            text check (gre_required in ('yes', 'no', 'optional')),
    english_proficiency     text,
    url                     text,
    scraped_at              timestamptz,
    content_hash            text,
    source_url              text
);

create index departments_institution_idx on public.departments(institution_id);

-- ---------------------------------------------------------------------------
-- 3. pis
-- ---------------------------------------------------------------------------
create table public.pis (
    id                          uuid primary key default gen_random_uuid(),
    name                        text not null,
    department_id               uuid references public.departments(id),
    institution_id              uuid references public.institutions(id),
    personal_url                text,
    lab_url                     text,
    google_scholar_url          text,
    semantic_scholar_id         text,
    openalex_id                 text,
    email                       text,
    career_stage                text check (career_stage in (
                                    'assistant_professor', 'associate_professor',
                                    'full_professor', 'postdoc',
                                    'industry_researcher', 'research_scientist')),
    phd_year                    integer,
    phd_institution             text,
    advisor_id                  uuid references public.pis(id),
    year_started_position       integer,
    h_index                     integer,
    total_citations             integer,
    citations_last_5_years      integer,
    citation_velocity           double precision,
    citation_velocity_source    text check (citation_velocity_source in ('breadth', 'depth', 'mixed')),
    paper_count                 integer,
    paper_count_last_3_years    integer,
    is_taking_students          text check (is_taking_students in ('yes', 'no', 'unknown')) default 'unknown',
    taking_students_confidence  double precision check (taking_students_confidence between 0.0 and 1.0),
    taking_students_checked_at  timestamptz,
    current_student_count       integer,
    funding_sources             text,
    funding_expiry              text,
    lab_name                    text,
    short_bio                   text,
    department_name             text,
    research_description        text,
    theory_category             text check (theory_category in ('theory', 'applied', 'mixed', 'unknown')) default 'unknown',
    theory_category_source      text check (theory_category_source in ('venue_derived', 'llm_assigned')),
    scraped_at                  timestamptz,
    content_hash                text,
    source_url                  text,
    -- Full-text search vector, kept in sync by trigger below.
    -- Weighted: name (A) > research_description (B) > department_name + lab_name (C).
    search_vector               tsvector
);

create index pis_institution_idx on public.pis(institution_id);
create index pis_department_idx on public.pis(department_id);
create index pis_h_index_desc_idx on public.pis(h_index desc nulls last);
create index pis_search_vector_idx on public.pis using gin(search_vector);

create function public.pis_search_vector_update() returns trigger as $$
begin
    new.search_vector :=
        setweight(to_tsvector('english', coalesce(new.name, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(new.research_description, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(new.department_name, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(new.lab_name, '')), 'C');
    return new;
end
$$ language plpgsql;

create trigger pis_search_vector_trigger
    before insert or update of name, research_description, department_name, lab_name
    on public.pis
    for each row
    execute function public.pis_search_vector_update();

-- ---------------------------------------------------------------------------
-- RLS: anon can read everything; writes go through Edge Functions w/ service_role.
-- ---------------------------------------------------------------------------
alter table public.institutions enable row level security;
alter table public.departments  enable row level security;
alter table public.pis          enable row level security;

create policy "anon read institutions" on public.institutions for select to anon using (true);
create policy "anon read departments"  on public.departments  for select to anon using (true);
create policy "anon read pis"          on public.pis          for select to anon using (true);
