"""PRISM core configuration — the single typed source of truth.

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

from typing import Optional

# --- Reproducibility / sampling -------------------------------------------
RANDOM_SEED: int = 2026
SAMPLE_SIZE_PER_DATASET: int = 200

# Version of the frozen benchmark samples (seed 2026, 200 questions/dataset,
# deterministic SciQ option shuffle). Bump when the frozen samples change.
DATASET_VERSION: str = "1.0"

# --- Dataset registry (HuggingFace source; used only by the dev refresh tool,
# never at product runtime — the app ships frozen samples) ------------------
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

# --- Prompt conditions (order matters — used for deterministic sorting) ----
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
MODELS: dict[str, dict[str, str]] = {
    "llama3.2:3b": {"label": "Llama-3.2 (3B)"},
    "gemma3:4b": {"label": "Gemma-3 (4B)"},
    "phi4-mini:latest": {"label": "Phi-4-mini (3.8B)"},
    "mistral:7b": {"label": "Mistral-7B"},
}

# --- Provenance identifiers ------------------------------------------------
EXPERIMENT_ID: str = "PRISM-EXP1-v1"
TEMPLATE_VERSION: str = "1.0"
PROTOCOL_VERSION: str = "1.0"

# --- Cloud sync (Supabase) --------------------------------------------------
# Hardcoded so every install of the app syncs into the same project without
# any per-user setup. This MUST be the anon/public key only (Project
# Settings -> API -> "anon public") — never the service_role key, since the
# anon key is safe to ship in a client as long as supabase/schema.sql's RLS
# policies restrict it to insert/upsert on runs + run_results.
SUPABASE_URL: str = "https://memineeqsblrgyyjxtpa.supabase.co"   
SUPABASE_ANON_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lbWluZWVxc2Jscmd5eWp4dHBhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODcxMzQzMDYsImV4cCI6MjEwMjcxMDMwNn0.Fh2OCKC_hpJ3qEPaKA-Gbemh-R5M_1Ib2kjSGJek3Jo"



def ollama_url(base_url: str | None, path: str) -> str:
    """Compose an Ollama endpoint URL from a base URL and a path.

    ``base_url=None`` falls back to :data:`OLLAMA_BASE_URL`. Trailing slashes on
    the base are trimmed so ``"http://host:11434/"`` and ``"http://host:11434"``
    behave identically.
    """
    base = (base_url or OLLAMA_BASE_URL).rstrip("/")
    return f"{base}{path}"