-- PRISM cloud mirror schema.
-- Run this once in the Supabase SQL editor (or via `supabase db push`).
-- Mirrors prism_core/store.py's local SQLite schema; app/services/supabase_sync.py
-- upserts into these tables using the anon key over PostgREST.

create table if not exists public.runs (
    benchmark_run_id  text primary key,
    created_utc       text not null,
    finished_utc      text,
    status            text not null,
    model             text not null,
    model_digest      text,
    datasets          jsonb not null default '[]'::jsonb,
    question_count    integer,
    app_version       text,
    protocol_version  text,
    run_dir           text not null,
    device_id         text,
    synced_at         timestamptz not null default now()
);

create table if not exists public.run_results (
    id                               bigint generated always as identity primary key,
    benchmark_run_id                 text not null references public.runs(benchmark_run_id) on delete cascade,
    dataset                          text not null,
    config_fingerprint               text not null,
    n_questions                      integer,
    prompt_response_accuracy         double precision,
    conditional_accuracy             double precision,
    answer_recovery_rate             double precision,
    instruction_compliance_rate      double precision,
    question_majority_accuracy       double precision,
    mean_agreement                   double precision,
    mean_prompt_sensitivity          double precision,
    answer_unanimous_rate            double precision,
    prompt_invariant_incorrect_rate  double precision,
    device_id                        text,
    synced_at                        timestamptz not null default now(),
    unique (benchmark_run_id, dataset)
);

create index if not exists idx_run_results_run on public.run_results(benchmark_run_id);
create index if not exists idx_run_results_model on public.runs(model);

-- "Other models" added from the startup screen's Manage Models panel. Any
-- model tag a user pulls that isn't one of prism_core.config.MODELS' four
-- validated models is upserted here, so it shows up in the picker on every
-- device/run of the app instead of being forgotten after the session ends.
create table if not exists public.custom_models (
    model_tag   text primary key,
    label       text,
    device_id   text,
    added_at    timestamptz not null default now()
);

alter table public.runs enable row level security;
alter table public.run_results enable row level security;
alter table public.custom_models enable row level security;

-- The desktop app only ever uses the anon key. Lock it to insert/upsert only
-- (no delete, no arbitrary reads of other people's rows if you're worried
-- about that) — reads for the GitHub Actions snapshot job should go through
-- a service_role key held only in CI secrets, never in the client.

create policy "anon can insert runs"
    on public.runs for insert
    to anon
    with check (true);

create policy "anon can update own runs (upsert)"
    on public.runs for update
    to anon
    using (true)
    with check (true);

create policy "anon can insert run_results"
    on public.run_results for insert
    to anon
    with check (true);

create policy "anon can update own run_results (upsert)"
    on public.run_results for update
    to anon
    using (true)
    with check (true);

-- Optional: allow anon SELECT too if you want the desktop app itself (not
-- just CI) to read back cloud data, e.g. to show "N other devices have
-- benchmarked this model". Omit this if you'd rather reads only happen from
-- CI with the service_role key.
-- create policy "anon can read runs" on public.runs for select to anon using (true);
-- create policy "anon can read run_results" on public.run_results for select to anon using (true);

-- custom_models needs anon SELECT (unlike runs/run_results above) because
-- the desktop app itself reads this list back on the startup screen to
-- populate the "Other models on this project" section.
create policy "anon can read custom models"
    on public.custom_models for select
    to anon
    using (true);

create policy "anon can insert custom models"
    on public.custom_models for insert
    to anon
    with check (true);

create policy "anon can update custom models (upsert)"
    on public.custom_models for update
    to anon
    using (true)
    with check (true);