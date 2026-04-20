-- Phase 2: field-level provenance log for community contributions.
-- Every contributed field is logged here before the winning value is written
-- to public.pis, so individual bad actors can be reverted surgically.

create table public.pi_field_contributions (
    id              uuid primary key default gen_random_uuid(),
    pi_id           uuid not null references public.pis(id),
    field_name      text not null,
    field_value     text,                   -- JSON-stringified value
    source_url      text,
    content_hash    text,
    model           text,                   -- e.g. 'anthropic/claude-haiku-4-5'
    extracted_at    timestamptz,
    contributor_id  uuid,                   -- anonymous, from ~/.gradradar/contributor_id
    ip              text,                   -- populated by Edge Function; used for rate limiting
    accepted        boolean not null default true,
    created_at      timestamptz not null default now()
);

create index pi_field_contributions_pi_field_idx
    on public.pi_field_contributions(pi_id, field_name, created_at desc);

create index pi_field_contributions_contributor_idx
    on public.pi_field_contributions(contributor_id);

-- For rate limiting: "how many contributions from this IP in the last hour?"
create index pi_field_contributions_ip_time_idx
    on public.pi_field_contributions(ip, created_at);

alter table public.pi_field_contributions enable row level security;

-- Anon can read the provenance log (useful for audit / "who edited this field?").
create policy "anon read contributions"
    on public.pi_field_contributions
    for select to anon using (true);

-- No direct inserts from anon; only the Edge Function (service_role) writes.
