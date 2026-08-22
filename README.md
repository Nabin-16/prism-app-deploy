# PRISM — merged desktop app

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
  key; a separate, maintainer-only GitHub Actions workflow
  (`.github/workflows/sync-results.yml`) reads with the service_role key
  and publishes moderated results into `models/<tag>/summary.json` in
  this repo.

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

- `PRISM_SUPABASE_URL` / `PRISM_SUPABASE_ANON_KEY` — used by the desktop
  app's background sync. Safe to ship in a built executable as long as
  Supabase Row Level Security restricts the anon role to insert/upsert
  (see `supabase/schema.sql`).
- `PRISM_SUPABASE_SERVICE_ROLE_KEY` — maintainer-only. Never used by the
  GUI. Used locally by `scripts/push_bundled_results_to_supabase.py`, and
  in CI (as `SUPABASE_SERVICE_KEY`) by `scripts/fetch_supabase_results.py`
  via a GitHub Actions secret.

## Packaging

```bash
pyinstaller prism.spec
```

Produces an onedir build under `dist/PRISM/` with the bundled seed data
(templates, frozen samples, and precomputed results for all four
validated models) included, so a fresh install shows a populated
dashboard with no network access or inference run required.
