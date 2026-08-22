"""
push_bundled_results_to_supabase
=================================

Headless admin push, ported from Karuna's ``push_to_supabase.py``. Separate
from the GUI's own sync (``app/services/supabase_sync.py``, which every
install runs automatically using the *anon* key): this script is for
publishing the maintainer's own validated / bundled results using the
*service_role* key, which must never ship inside the packaged app.

Reads credentials from the environment only - never from a settings screen
the GUI could expose:

    PRISM_SUPABASE_URL
    PRISM_SUPABASE_SERVICE_ROLE_KEY   (Project Settings -> API -> service_role)

Usage (from the project root, same folder as config.py):

    export PRISM_SUPABASE_URL="https://xxxxxxxx.supabase.co"
    export PRISM_SUPABASE_SERVICE_ROLE_KEY="ey..."
    python scripts/push_bundled_results_to_supabase.py

Re-running is safe - every table is upserted against its natural key
(same on_conflict targets as app/services/supabase_sync.py), so this never
creates duplicate rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from prism_core import config, seed, store
from app.services import backend


def main() -> int:
    url = config.SUPABASE_URL
    service_key = config.SUPABASE_SERVICE_ROLE_KEY

    if not url or not service_key:
        print(
            "Missing credentials. Set PRISM_SUPABASE_URL and "
            "PRISM_SUPABASE_SERVICE_ROLE_KEY as environment variables first, e.g.\n\n"
            '  export PRISM_SUPABASE_URL="https://xxxxxxxx.supabase.co"\n'
            '  export PRISM_SUPABASE_SERVICE_ROLE_KEY="ey..."\n'
            "  python scripts/push_bundled_results_to_supabase.py",
            file=sys.stderr,
        )
        return 1

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    # Make sure the bundled seed is materialized locally, then push every
    # completed run currently in the index (bundled + any real local runs).
    backend.ensure_bundled_seed()
    conn = backend.get_conn()
    try:
        runs = [r for r in store.list_runs(conn) if r["status"] == "completed"]
        runs_pushed, results_pushed, errors = 0, 0, []

        for run in runs:
            run_payload = dict(run)
            run_payload["datasets"] = json.loads(run_payload["datasets"])
            try:
                resp = requests.post(
                    f"{url}/rest/v1/runs", headers=headers,
                    params={"on_conflict": "benchmark_run_id"},
                    data=json.dumps(run_payload), timeout=20,
                )
                if resp.status_code not in (200, 201, 204):
                    errors.append(f"{run['benchmark_run_id']}: runs {resp.status_code} {resp.text[:150]}")
                    continue
            except requests.RequestException as exc:
                errors.append(f"{run['benchmark_run_id']}: {exc}")
                continue

            results = [dict(r) for r in store.get_run_results(conn, run["benchmark_run_id"])]
            if results:
                try:
                    resp = requests.post(
                        f"{url}/rest/v1/run_results", headers=headers,
                        params={"on_conflict": "benchmark_run_id,dataset"},
                        data=json.dumps(results), timeout=20,
                    )
                    if resp.status_code in (200, 201, 204):
                        results_pushed += len(results)
                    else:
                        errors.append(f"{run['benchmark_run_id']}: run_results {resp.status_code} {resp.text[:150]}")
                except requests.RequestException as exc:
                    errors.append(f"{run['benchmark_run_id']}: {exc}")
            runs_pushed += 1
    finally:
        conn.close()

    print(f"Pushed {runs_pushed} run(s), {results_pushed} result row(s).")
    if errors:
        print(f"{len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
