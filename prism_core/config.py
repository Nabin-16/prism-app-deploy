"""PRISM core configuration - the single typed source of truth.

Ported from the research ``config.py``. The **methodology constants** (seed,
sample size, prompt conditions, temperature, num_predict, protocol/template/
experiment identifiers, dataset registry) are preserved exactly so the ported
parser/scorer/report/prompt code behaves identically to the validated research
pipeline.

Two deliberate changes from the research config:

1. The fixed filesystem ``RESULTS_*`` directories are **not** global constants
   here. In the product each benchmark run writes under its own
   ``runs/<benchmark_run_id>/`` directory (see :mod:`prism_core.paths`), so run
   outputs are never coupled to a single global location.
2. Bundled read-only data (templates, frozen samples, prompts) is resolved via
   :mod:`prism_core.resources` rather than a project-relative ``data/`` dir, so
   it works in a wheel and under PyInstaller.

New: ``DATASET_VERSION`` (the research had no explicit dataset version) feeds
the reproducibility fingerprint, and the Ollama base URL is a configurable
field with endpoint paths derived from it.
"""
from __future__ import annotations

import os
from typing import Optional

try:  # optional dependency - only needed to read a local .env in dev/packaging
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# --- Reproducibility / sampling -------------------------------------------
RANDOM_SEED: int = 2026
SAMPLE_SIZE_PER_DATASET: int = 200

# Version of the frozen benchmark samples (seed 2026, 200 questions/dataset,
# deterministic SciQ option shuffle). Bump when the frozen samples change.
DATASET_VERSION: str = "1.0"

# --- Dataset registry (HuggingFace source; used only by the dev refresh tool,
# never at product runtime - the app ships frozen samples) ------------------
DATASETS: dict[str, dict[str, Optional[str]]] = {
    "arc_challenge": {
        "huggingface_dataset": "allenai/ai2_arc",
        "config": "ARC-Challenge",
        "split": "test",
    },
    "sciq": {
        "huggingface_dataset": "allenai/sciq",
        "config": None,
        "split": "test",
    },
}

# --- Prompt conditions (order matters - used for deterministic sorting) ----
PROMPT_CONDITIONS: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4")

# --- Inference parameters --------------------------------------------------
TEMPERATURE: float = 0.0
NUM_PREDICT: int = 450
REQUEST_TIMEOUT: int = 180

# --- Ollama endpoint (base URL is configurable; paths derive from it) ------
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_GENERATE_PATH: str = "/api/generate"
OLLAMA_TAGS_PATH: str = "/api/tags"
OLLAMA_SHOW_PATH: str = "/api/show"
OLLAMA_PULL_PATH: str = "/api/pull"

# --- Validated models (highlighted in the UI; the app accepts any installed
# Ollama model, these four are the research-validated set) ------------------
# ``min_ram_gb`` is the RAM Ollama/the model runtime recommends to load and
# run that model comfortably (roughly 2x the parameter count in GB, rounded
# up to a common tier). It's advisory only - used to warn the user before a
# pull that's unlikely to run well on their machine, never to hard-block it.
MODELS: dict[str, dict[str, str | int]] = {
    "llama3.2:3b": {"label": "Llama-3.2 (3B)", "min_ram_gb": 8},
    "gemma3:4b": {"label": "Gemma-3 (4B)", "min_ram_gb": 8},
    "phi4-mini:latest": {"label": "Phi-4-mini (3.8B)", "min_ram_gb": 8},
    "mistral:7b": {"label": "Mistral-7B", "min_ram_gb": 16},
}

# --- Provenance identifiers ------------------------------------------------
EXPERIMENT_ID: str = "PRISM-EXP1-v1"
TEMPLATE_VERSION: str = "1.0"
PROTOCOL_VERSION: str = "1.0"

# --- Cloud sync (Supabase) --------------------------------------------------
# Runtime sync (app/services/supabase_sync.py) always uses the *anon* key - # safe to ship in a client build as long as supabase/schema.sql's RLS
# policies restrict the anon role to insert/upsert on runs + run_results.
# Ported from Karuna's env-var convention: PRISM_SUPABASE_URL /
# PRISM_SUPABASE_PUBLISHABLE_KEY (read from a local .env via python-dotenv, or
# from the real environment in a packaged build) overrides the values below,
# so a packaged executable doesn't need the project's keys baked into source.
# The literals here are the fallback used when no environment/​.env value is
# set (e.g. a source checkout with no .env configured yet).
# No real project credentials are baked in here - set PRISM_SUPABASE_URL and
# PRISM_SUPABASE_PUBLISHABLE_KEY as real environment variables (or in a local
# .env) before packaging/running. Empty defaults mean sync is simply disabled
# until configured, rather than silently pointing at someone else's project.
# (PRISM_SUPABASE_ANON_KEY is still read as a fallback for projects still on
# Supabase's legacy JWT-based keys.)
SUPABASE_URL: str = os.environ.get("PRISM_SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.environ.get(
    "PRISM_SUPABASE_PUBLISHABLE_KEY",
    os.environ.get("PRISM_SUPABASE_ANON_KEY", ""),  # legacy fallback
)

# Admin-side push (scripts/push_bundled_results_to_supabase.py only - never
# imported by the GUI). Mirrors Karuna's push_to_supabase.py: reads the
# secret key from the environment so it's never bundled into the packaged
# executable at all. (PRISM_SUPABASE_SERVICE_ROLE_KEY is still read as a
# fallback for projects still on Supabase's legacy JWT-based keys.)
SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get(
    "PRISM_SUPABASE_SECRET_KEY",
    os.environ.get("PRISM_SUPABASE_SERVICE_ROLE_KEY", ""),  # legacy fallback
)



def ollama_url(base_url: str | None, path: str) -> str:
    """Compose an Ollama endpoint URL from a base URL and a path.

    ``base_url=None`` falls back to :data:`OLLAMA_BASE_URL`. Trailing slashes on
    the base are trimmed so ``"http://host:11434/"`` and ``"http://host:11434"``
    behave identically.
    """
    base = (base_url or OLLAMA_BASE_URL).rstrip("/")
    return f"{base}{path}"