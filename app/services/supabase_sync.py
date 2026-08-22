"""
Supabase cloud sync.

PRISM's source of truth is always the local SQLite index (prism_core.store);
this module is a one-way, best-effort *mirror* of that index into a single,
hardcoded Supabase project (see prism_core.config.SUPABASE_URL /
SUPABASE_ANON_KEY) over its auto-generated PostgREST API, using plain
``requests`` calls (no supabase-py dependency needed).

There is no per-user configuration screen: every install of the app syncs
into the same project, which then feeds the single GitHub repo via
.github/workflows/sync-results.yml + scripts/fetch_supabase_results.py.

Design:
  - Uses the *anon* key only, sent as both apikey and Bearer token. This key
    is safe to ship hardcoded in a desktop app as long as Row Level Security
    policies on the `runs` / `run_results` tables restrict the anon role to
    INSERT/UPSERT (see supabase/schema.sql) - it must never be able to read
    other devices' data or perform destructive operations.
  - Upserts (`Prefer: resolution=merge-duplicates`) keyed on the same primary
    keys as the local schema, so re-running sync is idempotent and re-runs
    of a benchmark just overwrite the row.
  - Never raises into the GUI thread's normal flow - callers get a
    SyncResult with .ok / .message and decide what to show the user.
  - If SUPABASE_URL/SUPABASE_ANON_KEY are still the placeholder values in
    config.py, sync is a no-op everywhere (is_configured() is False) - the
    app works fully offline either way.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from prism_core import config, store

REQUEST_TIMEOUT = 15


@dataclass
class SyncResult:
    ok: bool
    message: str
    runs_synced: int = 0
    results_synced: int = 0
    errors: list[str] = field(default_factory=list)


def is_configured() -> bool:
    url, key = config.SUPABASE_URL, config.SUPABASE_ANON_KEY
    return bool(url and key and not url.startswith("https://YOUR-") and not key.startswith("YOUR-"))


def _headers(*, upsert: bool = False) -> dict[str, str]:
    headers = {
        "apikey": config.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    if upsert:
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    return headers


def test_connection() -> SyncResult:
    """Cheap round-trip: select against `runs` with limit 1 row."""
    if not is_configured():
        return SyncResult(False, "Supabase isn't configured (see prism_core/config.py).")
    try:
        resp = requests.get(
            f"{config.SUPABASE_URL}/rest/v1/runs",
            headers=_headers(),
            params={"select": "benchmark_run_id", "limit": "1"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return SyncResult(False, f"Could not reach Supabase: {exc}")
    if resp.status_code == 200:
        return SyncResult(True, "Connected.")
    if resp.status_code in (401, 403):
        return SyncResult(False, "Rejected - check the anon key and RLS policies.")
    if resp.status_code == 404:
        return SyncResult(False, "Reached Supabase, but the `runs` table doesn't exist yet "
                                  " - run supabase/schema.sql in the SQL editor first.")
    return SyncResult(False, f"Unexpected response: {resp.status_code} {resp.text[:200]}")


def _row_to_run_payload(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    # `datasets` is stored as a JSON string locally; Supabase column is jsonb,
    # PostgREST accepts either a JSON-encoded string or a native object here - # decode it so it lands as real jsonb rather than a quoted string.
    try:
        d["datasets"] = json.loads(d["datasets"])
    except (TypeError, ValueError, KeyError):
        pass
    d["device_id"] = _device_id()
    return d


def _row_to_result_payload(row: sqlite3.Row, device_id: str) -> dict[str, Any]:
    d = dict(row)
    d["device_id"] = device_id
    return d


_device_id_cache: str | None = None


def _device_id() -> str:
    """A stable-ish per-install identifier so multiple people's local PRISM
    installs can sync into the same Supabase project without colliding - purely informational, not a security boundary."""
    global _device_id_cache
    if _device_id_cache is not None:
        return _device_id_cache

    marker = Path.home() / ".prism" / "device_id"
    if marker.exists():
        _device_id_cache = marker.read_text(encoding="utf-8").strip()
    else:
        _device_id_cache = uuid.uuid4().hex
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(_device_id_cache, encoding="utf-8")
    return _device_id_cache


def sync_run(conn: sqlite3.Connection, benchmark_run_id: str) -> SyncResult:
    """Push one completed run + its per-dataset result rows to Supabase."""
    if not is_configured():
        return SyncResult(False, "Supabase isn't configured.")

    run = store.get_run(conn, benchmark_run_id)
    if run is None:
        return SyncResult(False, f"No local run {benchmark_run_id!r} to sync.")
    if run["status"] != "completed":
        return SyncResult(False, "Only completed runs are synced.")

    device_id = _device_id()
    errors: list[str] = []

    try:
        resp = requests.post(
            f"{config.SUPABASE_URL}/rest/v1/runs",
            headers=_headers(upsert=True),
            params={"on_conflict": "benchmark_run_id"},
            data=json.dumps(_row_to_run_payload(run)),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code not in (200, 201, 204):
            errors.append(f"runs upsert failed: {resp.status_code} {resp.text[:200]}")
    except requests.RequestException as exc:
        return SyncResult(False, f"Network error syncing run: {exc}")

    results = store.get_run_results(conn, benchmark_run_id)
    results_synced = 0
    if results and not errors:
        payload = [_row_to_result_payload(r, device_id) for r in results]
        try:
            resp = requests.post(
                f"{config.SUPABASE_URL}/rest/v1/run_results",
                headers=_headers(upsert=True),
                params={"on_conflict": "benchmark_run_id,dataset"},
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code in (200, 201, 204):
                results_synced = len(payload)
            else:
                errors.append(f"run_results upsert failed: {resp.status_code} {resp.text[:200]}")
        except requests.RequestException as exc:
            errors.append(f"Network error syncing results: {exc}")

    if errors:
        return SyncResult(False, "; ".join(errors), runs_synced=0,
                           results_synced=results_synced, errors=errors)
    return SyncResult(True, "Synced.", runs_synced=1, results_synced=results_synced)


def fetch_custom_models() -> list[dict[str, Any]]:
    """Return every "other model" any device has pulled and saved, newest
    first. Best-effort: on any error (not configured, offline, table missing
    because schema.sql hasn't been re-run yet) this just returns an empty
    list rather than raising, since the startup screen's local catalog
    always works without it.
    """
    if not is_configured():
        return []
    try:
        resp = requests.get(
            f"{config.SUPABASE_URL}/rest/v1/custom_models",
            headers=_headers(),
            params={"select": "model_tag,label,added_at", "order": "added_at.desc"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    try:
        return resp.json()
    except ValueError:
        return []


def save_custom_model(model_tag: str, label: str | None = None) -> SyncResult:
    """Upsert one "other model" tag so it's remembered next time the
    startup screen's Manage Models panel opens, on this device or any other
    device pointed at the same Supabase project."""
    if not is_configured():
        return SyncResult(False, "Supabase isn't configured.")
    payload = {
        "model_tag": model_tag,
        "label": label or model_tag,
        "device_id": _device_id(),
    }
    try:
        resp = requests.post(
            f"{config.SUPABASE_URL}/rest/v1/custom_models",
            headers=_headers(upsert=True),
            params={"on_conflict": "model_tag"},
            data=json.dumps(payload),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return SyncResult(False, f"Network error saving model: {exc}")
    if resp.status_code in (200, 201, 204):
        return SyncResult(True, "Saved.")
    return SyncResult(False, f"custom_models upsert failed: {resp.status_code} {resp.text[:200]}")


def sync_all_completed(conn: sqlite3.Connection) -> SyncResult:
    """Push every completed local run."""
    if not is_configured():
        return SyncResult(False, "Supabase isn't configured.")

    runs_synced = 0
    results_synced = 0
    errors: list[str] = []
    for row in store.list_runs(conn):
        if row["status"] != "completed":
            continue
        result = sync_run(conn, row["benchmark_run_id"])
        if result.ok:
            runs_synced += result.runs_synced
            results_synced += result.results_synced
        else:
            errors.append(f"{row['benchmark_run_id']}: {result.message}")

    if errors:
        return SyncResult(
            False, f"Synced {runs_synced} run(s), {len(errors)} failed.",
            runs_synced=runs_synced, results_synced=results_synced, errors=errors,
        )
    return SyncResult(
        True, f"Synced {runs_synced} run(s) / {results_synced} result row(s).",
        runs_synced=runs_synced, results_synced=results_synced,
    )