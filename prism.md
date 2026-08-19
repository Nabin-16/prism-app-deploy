# PRISM
### Prompt Reliability through Intelligent Semantic Multiplexing

**A research-grade benchmark for evaluating how reliable Small Language Models (SLMs) are when the same question is asked in different but semantically equivalent ways.**

---

## 1. What PRISM Is

PRISM began as a university research project studying a simple but important question:

> If you ask a language model the same underlying question using several different (but semantically equivalent) prompt styles, does it keep giving the same — and correct — answer?

PRISM is therefore not primarily a "which model is smartest" leaderboard. It is a **reliability and stability benchmark**. It cares less about raw accuracy and more about whether a model's behavior changes just because the *wording* of the instruction changed.

The project is moving from a validated research pipeline into a real product: a desktop benchmark application plus a companion website, backed by a public, moderated results repository.

---

## 2. Research Foundations

### 2.1 Domain and datasets
Research is scoped to **education / science question-answering**, using:
- **ARC-Challenge**
- **SciQ**

A legal-domain dataset was deliberately dropped to keep the study within one consistent domain. SciQ required special handling since it doesn't ship with fixed A/B/C/D labels — the loader extracts the correct answer and distractors, deterministically shuffles them (seeded by project seed + question ID), assigns labels, and stores a stable question identifier. This determinism is what keeps the benchmark reproducible.

### 2.2 Models
Small Language Models runnable locally via **Ollama**:
- Llama 3.2 3B
- Gemma 3 4B
- Phi-4 Mini
- Mistral 7B

Inference is deliberately **local-only** (no cloud model APIs), and **temperature = 0**, since the research question is about prompt-condition variation, not sampling randomness.

### 2.3 Prompt conditions
Every question is asked five different but semantically equivalent ways:

```
Question
 ├── P0 — Minimal
 ├── P1 — Direct
 ├── P2 — Structured
 ├── P3 — Role
 └── P4 — Careful Analysis
```

This 5-way structure is the backbone of the consistency analysis — it's what lets PRISM measure whether *phrasing* changes the answer.

### 2.4 Experimental pipeline (research phase)

```
Dataset
  → Dataset loader (normalization)
  → Question selection
  → Prompt generation (P0–P4)
  → Ollama inference (temp = 0)
  → Raw responses (JSONL, full provenance)
  → Response parser (safe answer extraction)
  → Consistency scorer
  → Summary reports (CSV)
  → Research analysis / visualization
```

Raw inference records carry full experimental provenance (experiment id, protocol/template/prompt hashes, latency, timestamp, etc.) so results stay reproducible and auditable.

### 2.5 Response parsing
Model output is messy — `"B"`, `"B. slowly"`, `"The final answer is B."`, or an outright refusal. The parser does **safe extraction**, deliberately avoiding the trap of grabbing the first A/B/C/D it sees in the reasoning text (which could be a distractor being discussed, not the actual answer). It tracks parse status, instruction compliance, and unknown/ambiguous/refusal cases explicitly.

### 2.6 Metrics
PRISM intentionally keeps these **separate** rather than collapsing them into one arbitrary "reliability score":

| Metric | What it measures |
|---|---|
| **Answer Recovery Rate** | Fraction of responses that could be parsed into a usable answer |
| **Accuracy** | Recovered answer matches the expected answer |
| **Conditional Accuracy** | Accuracy computed only among successfully recovered answers |
| **Instruction Compliance Rate** | How often the model followed the required output format |
| **Unknown Rate** | Responses that couldn't be safely resolved (refusal, ambiguity, unparseable) |
| **Agreement** | How consistently the model answers the same across P0–P4 for one question |
| **Prompt Sensitivity** | How much the answer changes purely because of prompt phrasing |
| **Question Majority Accuracy** | Whether the majority answer across P0–P4 matches ground truth |
| **Answer Unanimous Rate** | Fraction of questions where all 5 prompt conditions agree |
| **Prompt-Invariant Incorrect Rate** | Questions where the model is *consistently* wrong across all prompt conditions |

The key research insight PRISM has already demonstrated: **consistency ≠ correctness**. A model can look highly stable while being reliably wrong — that's arguably the most important finding the benchmark surfaces, and any future "single score" dashboard must not bury it.

Aggregate outputs live in `model_dataset_summary.csv` (model×dataset level) and `model_prompt_summary.csv` (model×dataset×prompt-condition level), plus question-level records for deeper drill-down.

---

## 3. Product Direction

PRISM's product goal is to turn this validated methodology into something a non-researcher can run:

```
Select model
    ↓
PRISM prepares the environment (Ollama, model pull)
    ↓
Benchmark runs automatically
    ↓
Responses parsed → metrics calculated
    ↓
Results displayed on a dashboard
    ↓
(optional) Contribute results to the public PRISM dataset
```

The complexity of installing Ollama, pulling models, and running scripts manually should be hidden — the user just picks a model and PRISM handles the rest.

A core UX feature is **avoiding duplicate work**: if a model has already been benchmarked and published to the public repository, the user can either instantly view the existing validated result or choose to run it locally themselves (useful for validation or contributing new data).

### Architectural principle
The GUI must **not** contain benchmark logic directly. The existing research scripts (`inference.py`, `response_parser.py`, `consistency_scorer.py`, `summary_report.py`) should be refactored into clean, reusable services that the GUI calls into:

```
DatasetService
PromptService
OllamaService
InferenceService
ParserService
ScoringService
ReportService
BenchmarkService
```

This keeps the app testable and keeps "research code" (built for experimentation/debugging) cleanly separated from "product code" (built for usability, error handling, and maintainability).

### Reproducibility & data integrity
Every benchmark result must carry enough metadata to know exactly how it was produced (model + version, dataset + version, benchmark/prompt/template version, temperature, seed, question count, timestamp, platform, Ollama version). Identifiers (`benchmark_run_id`, `dataset`, `question_id`, `model`, `prompt_condition`) are treated as first-class data — duplicate or missing records must fail loudly, never silently.

---

## 4. System Architecture

```
┌───────────────────────────┐        ┌───────────────────────────┐
│   DESKTOP APP (PySide6)    │        │   WEBSITE (Next.js)        │
│  - Ollama detect / pull    │        │  - Download button         │
│  - Model selection         │        │  - Public results explorer │
│  - Run inference           │        │  - Methodology / docs       │
│  - Parse / Score / Summary │        │                              │
│  - Local results dashboard │        │                              │
└──────────────┬──────────────┘        └─────────────┬────────────────┘
               │ POST summary.json                    │ reads
               ▼                                       ▼
      ┌───────────────────────────────────────────────────────┐
      │        BACKEND API (FastAPI, no user auth)              │
      │        Hosted: Render / Railway / Fly.io                │
      └───────────────────────┬──────────────────────────────┘
                               ▼
      ┌───────────────────────────────────────────────────────┐
      │     SUPABASE (Postgres + Storage) — staging area         │
      │     submission status: pending / approved / rejected      │
      └───────────────────────┬──────────────────────────────┘
                               ▼ (maintainer reviews & approves)
      ┌───────────────────────────────────────────────────────┐
      │   Maintainer's GitHub token (server-side only)            │
      │   → commits/opens PR to GitHub repo: /models/<name>/       │
      └───────────────────────┬──────────────────────────────┘
                               ▼
      ┌───────────────────────────────────────────────────────┐
      │   GitHub repo (public) — source of truth                  │
      │   Website + new app installs both read from here           │
      └───────────────────────────────────────────────────────┘
```

**Division of responsibility:**

```
                  PRISM
                    │
        ┌───────────┴───────────┐
        │                       │
 Desktop Application         Website
        │                       │
 Local benchmarking        Documentation
 Local Ollama integration  Public benchmark results
 Local inference           Results explorer
 Local analysis            Research / methodology info
```

The website never replaces the desktop app — it documents PRISM, explains the metrics/methodology, and surfaces the public, moderated results. All actual benchmarking happens locally in the desktop app against the user's own Ollama installation.

---

## 5. Technology Stack

### 5.1 Desktop application

| Layer | Tool | Notes |
|---|---|---|
| App shell / UI | **PySide6** | Main application framework — native Qt widgets |
| Pipeline logic | Refactored Python services | `InferenceService`, `ParserService`, `ScoringService`, `ReportService`, called in-process |
| Optional local backend | **FastAPI** on `localhost` | Keeps pipeline logic decoupled from UI if needed; called via `requests`/`httpx` |
| Concurrency | `QThread` / `QRunnable` | Keeps inference and model pulls off the UI thread |
| Local Ollama integration | Ollama REST API (`localhost:11434`) | `/api/tags` to detect installed models, `/api/pull` (streamed) to download |
| Local data store | **SQLite** (stdlib `sqlite3`) | Tracks run metadata; raw JSON/JSONL still lives in `results/` as the research pipeline already produces |
| Bundled datasets | JSON/CSV shipped with the app | ARC-Challenge + SciQ samples — no external download needed at first run |
| Packaging | **PyInstaller** (or `pyside6-deploy`) | One executable per OS, built via GitHub Actions matrix (windows-latest / macos-latest / ubuntu-latest) |
| Submitting new results | `requests.post()` to backend API | Plain HTTP, no login/auth required from the user |

### 5.2 Backend API (submission + moderation)

| Layer | Tool |
|---|---|
| Framework | **FastAPI** (reuses the pipeline's Pydantic schemas) |
| Hosting | Render / Railway / Fly.io (low-cost tier) |
| Database + file storage | **Supabase** (Postgres + Storage, free tier, built-in admin dashboard) |
| GitHub write access | `PyGithub` or raw GitHub REST calls, using a **server-side personal access token** — never shipped inside the app |

**Endpoints:**

```
POST /api/submit-summary
  body: { model_name, domain, summary_json, app_version }
  - validates schema, size limit, basic per-IP rate limit
  - inserts row into Supabase with status = "pending"
  → 202 Accepted, no auth required

GET /api/models
  - returns approved models + metadata
  - alternative to the app hitting GitHub raw URLs directly

POST /api/admin/approve/{submission_id}   (maintainer-only)
  - fetches the pending JSON from Supabase Storage
  - commits (or opens a PR) to GitHub: /models/<model_name>/summary.json
  - updates row status = "approved"
```

**Moderation:** start manual (maintainer reviews Supabase dashboard, pushes approved results to GitHub by hand); a semi-automated, password-protected "Approve" admin page can be added later if the timeline allows.

### 5.3 Website

| Layer | Tool |
|---|---|
| Framework | **Next.js** — main website framework |
| Charts | Chart.js or Recharts |
| Data source | GitHub repo's `models/` directory (build-time or client-side from raw URLs), or `/api/models` |
| Hosting | Vercel, Netlify, or GitHub Pages |
| Docs | Built-in Next.js pages, or Docusaurus if documentation grows large |

**Pages:**
- **Home** — download links to GitHub Releases (per-OS PyInstaller builds)
- **Results / Dashboard** — accuracy, unknown rate, and prompt-invariant-incorrectness comparisons per model, pulled from `models/`
- **Docs** — PRISM methodology, terminology, metric definitions, how to contribute a new model result

### 5.4 GitHub repository (source of truth)

```
PRISM-Reliability/
├── models/
│   ├── llama-3.2-3b/summary.json
│   ├── gemma-3-4b/summary.json
│   ├── phi-4-mini/summary.json
│   ├── mistral-7b/summary.json
│   └── <new-community-model>/summary.json
├── src/            (refactored pipeline services)
├── data/           (datasets/templates)
└── results/        (raw + parsed + scored research output)
```

Each `summary.json` is the canonical artifact both the website and every new app install read — new users pull already-benchmarked models directly via public raw GitHub URLs, no API key needed.

---

## 6. Planned Desktop App Flow

```
1. Startup check        → ping localhost:11434; if not found, show install instructions
2. Model selection      → Llama 3.2 / Gemma 3 / Phi-4 Mini / Mistral 7B / custom model
                           (uninstalled model → /api/pull with a progress bar)
3. Dataset check        → ARC-Challenge / SciQ, bundled locally
4. Existing results?    → if a summary already exists (bundled or from GitHub raw),
                           offer "Use existing results" vs "Run my own inference"
5. Run inference        → Inference → Parser → Scorer → Report, each stage shown live
6. Dashboard            → raw / parsed / scored / summary per model, open/export
7. New result           → prompt "Share this result to help others?" → POST to backend
```

---

## 7. Development Philosophy

The team is proceeding incrementally rather than building every planned feature at once:

1. Preserve the already-validated research methodology
2. Fully understand the existing repository before changing it
3. Identify which research modules can be reused vs. refactored
4. Design the service-oriented application architecture
5. Build the PySide6 application incrementally
6. Integrate Ollama
7. Integrate the benchmark engine
8. Build result visualization
9. Build the public-results submission/moderation workflow
10. Build the website / documentation ecosystem

**Guiding rule:** the existing research pipeline is the source of truth for correct benchmark behavior. Any refactor into the product must preserve that validated methodology — the goal is packaging good research into a usable tool, not reinventing the science.

---

## 8. Quick Reference

- **Project:** PRISM — Prompt Reliability through Intelligent Semantic Multiplexing
- **Research goal:** measure model reliability/stability under semantically equivalent prompt variation, not just accuracy
- **Datasets:** ARC-Challenge, SciQ
- **Prompt conditions:** P0 (Minimal), P1 (Direct), P2 (Structured), P3 (Role), P4 (Careful Analysis)
- **Inference:** Ollama, local-only, temperature = 0
- **Models:** Llama 3.2 3B, Gemma 3 4B, Phi-4 Mini, Mistral 7B
- **Desktop framework:** PySide6
- **Website framework:** Next.js
- **Backend:** FastAPI + Supabase, GitHub repo as public source of truth
- **Core research finding:** consistency ≠ correctness — a model can be reliably wrong