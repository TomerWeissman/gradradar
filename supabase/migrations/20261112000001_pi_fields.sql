-- Research-field tags on PIs (e.g. 'finance'), so search can be restricted to one field.
-- Additive: existing rows get an empty array; the anon read policy already covers new columns.
alter table public.pis add column if not exists fields text[] not null default '{}';
create index if not exists pis_fields_idx on public.pis using gin (fields);
