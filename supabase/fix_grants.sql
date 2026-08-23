-- =============================================================================
-- PRISM Supabase Permissions & RLS Policies Fix
-- Run this in Supabase Dashboard -> SQL Editor
-- Resolves 401 (USING expression violation) and 400 (foreign key constraint) errors
-- =============================================================================

-- 1. Schema Usage
grant usage on schema public to anon, authenticated, service_role;

-- 2. Table Permissions for Desktop Client (anon / authenticated)
grant select, insert, update on public.runs to anon, authenticated;
grant select, insert, update on public.run_results to anon, authenticated;
grant select, insert, update on public.custom_models to anon, authenticated;
grant usage, select on all sequences in schema public to anon, authenticated;

-- 3. Full Maintainer Permissions (service_role)
grant select, insert, update, delete on public.runs to service_role;
grant select, insert, update, delete on public.run_results to service_role;
grant select, insert, update, delete on public.custom_models to service_role;
grant usage, select on all sequences in schema public to service_role;

-- 4. Enable Row Level Security
alter table public.runs enable row level security;
alter table public.run_results enable row level security;
alter table public.custom_models enable row level security;

-- 5. Clean up old conflicting policies
drop policy if exists "Allow anon insert unapproved runs" on public.runs;
drop policy if exists "Allow anon update pending runs" on public.runs;
drop policy if exists "Allow anon select runs" on public.runs;
drop policy if exists "Allow insert runs" on public.runs;
drop policy if exists "Allow update runs" on public.runs;
drop policy if exists "Allow select runs" on public.runs;
drop policy if exists "anon can insert runs" on public.runs;
drop policy if exists "anon can update own runs (upsert)" on public.runs;

drop policy if exists "Allow anon insert run results" on public.run_results;
drop policy if exists "Allow anon update run results" on public.run_results;
drop policy if exists "Allow anon select run results" on public.run_results;
drop policy if exists "Allow insert run results" on public.run_results;
drop policy if exists "Allow update run results" on public.run_results;
drop policy if exists "Allow select run results" on public.run_results;
drop policy if exists "anon can insert run_results" on public.run_results;
drop policy if exists "anon can update own run_results (upsert)" on public.run_results;

drop policy if exists "Allow anon insert custom models" on public.custom_models;
drop policy if exists "Allow anon update custom models" on public.custom_models;
drop policy if exists "Allow anon select custom models" on public.custom_models;
drop policy if exists "Allow insert custom models" on public.custom_models;
drop policy if exists "Allow update custom models" on public.custom_models;
drop policy if exists "Allow select custom models" on public.custom_models;
drop policy if exists "anon can read custom models" on public.custom_models;
drop policy if exists "anon can insert custom models" on public.custom_models;
drop policy if exists "anon can update custom models (upsert)" on public.custom_models;

-- 6. Ingestion & Upsert Policies for public.runs
-- Note: PostgREST upserts require SELECT + INSERT + UPDATE permissions
create policy "Allow select runs"
    on public.runs for select
    to anon, authenticated
    using (true);

create policy "Allow insert runs"
    on public.runs for insert
    to anon, authenticated
    with check (true);

create policy "Allow update runs"
    on public.runs for update
    to anon, authenticated
    using (true)
    with check (approved = false);

-- 7. Ingestion & Upsert Policies for public.run_results
create policy "Allow select run results"
    on public.run_results for select
    to anon, authenticated
    using (true);

create policy "Allow insert run results"
    on public.run_results for insert
    to anon, authenticated
    with check (true);

create policy "Allow update run results"
    on public.run_results for update
    to anon, authenticated
    using (true)
    with check (true);

-- 8. Policies for public.custom_models
create policy "Allow select custom models"
    on public.custom_models for select
    to anon, authenticated
    using (true);

create policy "Allow insert custom models"
    on public.custom_models for insert
    to anon, authenticated
    with check (true);

create policy "Allow update custom models"
    on public.custom_models for update
    to anon, authenticated
    using (true)
    with check (true);
