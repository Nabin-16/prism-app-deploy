# PRISM — A desktop app

A single PySide6 desktop application merging three source projects into
one product:

- **prism_core** (engine) — ported from `PRISM_app/PRISM_BUILD`, the most
  complete implementation of the research pipeline (dataset loading,
  prompt generation, Ollama inference, response parsing, consistency
  scoring, reporting, a local SQLite run index, and bundled seed results
  for the four validated models).
- **Layout, sidebar-free app shell, and dashboard analytics** — from
  `PRISM-Reliability-test-` (prompt-reliability) and `PRISM_app/PRISM_BUILD`
  combined: native toolbar/menu/status-bar chrome, KPI tiles, charts, and
  a per-question drill-down table, with an added **comparison-model
  selector** so two models' metrics can be viewed side by side.
- **Model selection + Ollama status** — from `PRISM_app/PRISM_BUILD`'s
  startup screen: detects whether Ollama is running, shows each validated
  model as connected/not-installed, and can pull a model with live
  progress.
- **Supabase sync + GitHub publishing** — the anon-key sync pattern from
  `PRISM_app/PRISM_BUILD` combined with the CLI-script pattern from
  `Karuna`: the desktop app only ever writes to Supabase with the anon
  key. Publishing to the public repo is a separate, maintainer-only flow
  split across two repos (see "Two-repo publishing flow" below) so the
  public repo's git history never contains this repo's source code.

## Two-repo publishing flow

1. **This (private) repo** — app source. Every install syncs completed
   runs into Supabase automatically with the publishable key
   (`app/services/supabase_sync.py`). Rows land as `approved = false`.
2. **Maintainer review, from this repo** — run
   `scripts/approve_runs.py list` / `approve <run_id>` (needs
   `PRISM_SUPABASE_SECRET_KEY` as a local env var only, never
   committed) to review and approve individual runs.
3. **Public repo** — a separate repo containing only `results/`,
   `models/`, and its own `.github/workflows/sync-results.yml` +
   `scripts/fetch_supabase_results.py`. A maintainer manually triggers
   that repo's workflow (Actions → Run workflow); it reads only
   `approved = true` rows from Supabase and commits the snapshot there.
   Nothing from this private repo is ever checked out by that job.

`scripts/push_bundled_results_to_supabase.py` is a separate, optional
tool for the maintainer to push their own bundled/validated results
straight into Supabase (as pre-approved) using the secret key —
unrelated to the per-device publishable-key sync above.

## Visual style

A traditional, "research report" desktop look rather than a modern flat
one: serif headings, real 1px hairline borders instead of shadows, sharp
(0–4px) corners, and a muted paper/ink palette (with a dark "dusk" palette
also available) — see `app/gui/theme.py`.

## Crash-safe inference

`prism_core/inference.py` distinguishes two kinds of failure:

- An ordinary bad response (refusal, malformed output, one dropped HTTP
  call) is recorded as an `error` record and the run keeps going — this
  is expected and part of the methodology (the parser turns it into an
  observed `UNKNOWN`).
- A **fatal** condition — out-of-memory, the Ollama server crashing or
  becoming unreachable, or several consecutive failures in a row — halts
  the run in a controlled way. Everything gathered so far is saved to
  disk immediately. The app itself is never killed by this: the halt is
  reported up through a Qt signal (`BenchmarkWorker.fatal_halt`) to the
  Benchmark screen, which shows the reason and lets the person **Continue**
  (resume, keeping completed work), **Rerun from scratch**, or **Stop**.

An app-wide exception hook in `main.py` is a second, outer safety net for
anything else that might otherwise crash the GUI process.

## Running

```bash
pip install -r requirements.txt
python main.py
```

## Credentials

No real credentials are checked into this repo. Copy `.env.example` to
`.env` for local development, or set the same variables as real
environment variables when packaging:

- `PRISM_SUPABASE_URL` / `PRISM_SUPABASE_PUBLISHABLE_KEY` — used by the
  desktop app's background sync. Safe to ship in a built executable as
  long as Supabase Row Level Security restricts the anon role to
  insert/upsert (see `supabase/schema.sql`). (`PRISM_SUPABASE_ANON_KEY`
  is still read as a fallback if you're on Supabase's legacy JWT-based
  keys instead of the newer publishable/secret key pair.)
- `PRISM_SUPABASE_SECRET_KEY` — maintainer-only. **Never put this in
  `.env` and never let it near app packaging** — `.env` is loaded
  automatically every time the app runs, and `build.yml` only ever reads
  `PRISM_SUPABASE_PUBLISHABLE_KEY`, so this key has no reason to be
  anywhere the GUI or the build process can see it. Instead, export it
  manually in your shell only when running a maintainer script:

  ```bash
  export PRISM_SUPABASE_URL="https://xxxxxxxx.supabase.co"
  export PRISM_SUPABASE_SECRET_KEY="sk_..."
  python scripts/approve_runs.py list
  ```

  Used only by `scripts/push_bundled_results_to_supabase.py` and
  `scripts/approve_runs.py`. The public repo holds its own separate copy
  of this key as a CI secret (`SUPABASE_SECRET_KEY`) for its own
  `fetch_supabase_results.py`; this repo never sees or stores that CI
  secret. (`PRISM_SUPABASE_SERVICE_ROLE_KEY` is still read as a fallback
  for legacy JWT-based Supabase projects.)

**If a secret/service_role key is ever accidentally written to a file, committed,
or shared outside these two places, rotate it immediately** in Supabase →
Project Settings → API → Reset service_role key, then update both the
local env var here and the CI secret in the public repo.

## Packaging

```bash
pyinstaller prism.spec
```

Produces an onedir build under `dist/PRISM/` with the bundled seed data
(templates, frozen samples, and precomputed results for all four
validated models) included, so a fresh install shows a populated
dashboard with no network access or inference run required.