#!/usr/bin/env python3
"""
Pull the current PRISM results mirror from Supabase and write it into the
repo as a snapshot GitHub Pages / the app's "compare without downloading a
model" mode can read.

Run from CI (see .github/workflows/sync-results.yml) with:
    SUPABASE_URL=...        (same project URL as the desktop app)
    SUPABASE_SERVICE_KEY=... (service_role key -- CI secret ONLY, never the
                               anon key used by the desktop app, and never
                               committed anywhere)

Writes:
    results/cloud/runs.json
    results/cloud/model_dataset_summary.csv   (flattened, one row per
                                                 model x dataset, latest run)
    models/<model_tag>/summary.json           (one file per model, matching
                                                 the public repo layout the
                                                 README describes so the
                                                 website/app can read a
                                                 single model's result
                                                 without downloading anything
                                                 else)

This script only ever reads from Supabase and writes files into the current
checkout - it never pushes. Committing/pushing to the public results repo
is done by the CI workflow that calls this script
(.github/workflows/sync-results.yml), using a token scoped to that repo and
held only in CI secrets, never in this codebase.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "results" / "cloud"

_RESULT_METRIC_COLUMNS = (
    "n_questions",
    "prompt_response_accuracy",
    "conditional_accuracy",
    "answer_recovery_rate",
    "instruction_compliance_rate",
    "question_majority_accuracy",
    "mean_agreement",
    "mean_prompt_sensitivity",
    "answer_unanimous_rate",
    "prompt_invariant_incorrect_rate",
)


def _get(url: str, key: str, path: str, params: dict) -> list[dict]:
    resp = requests.get(
        f"{url}/rest/v1/{path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.", file=sys.stderr)
        return 1

    runs = _get(url, key, "runs", {"select": "*", "status": "eq.completed",
                                    "order": "created_utc.desc"})
    results = _get(url, key, "run_results", {"select": "*"})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    (OUT_DIR / "run_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Flatten to "latest completed run per (model, dataset)" for a simple CSV
    # a static site or the desktop app's optional cloud-browse view can read
    # without needing to know about the runs/run_results join.
    runs_by_id = {r["benchmark_run_id"]: r for r in runs}
    latest: dict[tuple[str, str], dict] = {}
    for res in results:
        run = runs_by_id.get(res["benchmark_run_id"])
        if run is None:
            continue
        model = run["model"]
        dataset = res["dataset"]
        key_tuple = (model, dataset)
        existing = latest.get(key_tuple)
        if existing is None or run["created_utc"] > existing["_created_utc"]:
            row = {"model": model, "dataset": dataset}
            for col in _RESULT_METRIC_COLUMNS:
                row[col] = res.get(col)
            row["_created_utc"] = run["created_utc"]
            latest[key_tuple] = row

    csv_path = OUT_DIR / "model_dataset_summary.csv"
    fieldnames = ["model", "dataset", *_RESULT_METRIC_COLUMNS]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(latest.values(), key=lambda r: (r["model"], r["dataset"])):
            writer.writerow(row)

    # Per-model snapshot files, matching the public repo's /models/<name>/
    # layout described in the project README - lets the website or a fresh
    # app install fetch just one model's validated result.
    models_dir = REPO_ROOT / "models"
    by_model: dict[str, list[dict]] = {}
    for row in latest.values():
        by_model.setdefault(row["model"], []).append(row)
    for model_tag, rows in by_model.items():
        safe_name = model_tag.replace(":", "_").replace("/", "_")
        model_dir = models_dir / safe_name
        model_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": model_tag,
            "datasets": sorted(
                ({k: v for k, v in r.items() if not k.startswith("_")} for r in rows),
                key=lambda r: r["dataset"],
            ),
        }
        (model_dir / "summary.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    print(f"Wrote {len(runs)} runs, {len(results)} result rows, "
          f"{len(latest)} flattened model x dataset rows, "
          f"{len(by_model)} per-model snapshot files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())