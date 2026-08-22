"""Local run index (SQLite, stdlib only).

This is an **index, not a blob store** (plan §"Local store"): the heavy
artifacts stay as JSONL/CSV under ``runs/<id>/``. The DB records which runs
exist and - crucially - the per-(model, dataset) ``config_fingerprint`` so the
run-setup screen can answer *"is there already a local result equivalent to what
you're about to run?"* without re-reading every run's files.

Two tables:

* ``runs`` - one row per :func:`prism_core.fingerprint.new_benchmark_run_id`.
* ``run_results`` - one row per (run, dataset) with the fingerprint and the
  headline model/dataset-level metrics for fast listing.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

SCHEMA_VERSION = 1

# Metric columns mirrored from model_dataset_summary for fast listing without
# reopening the run's CSVs. Names match report.build_model_dataset_summary keys.
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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    benchmark_run_id  TEXT PRIMARY KEY,
    created_utc       TEXT NOT NULL,
    finished_utc      TEXT,
    status            TEXT NOT NULL,
    model             TEXT NOT NULL,
    model_digest      TEXT,
    datasets          TEXT NOT NULL,          -- JSON array of dataset names
    question_count    INTEGER,
    app_version       TEXT,
    protocol_version  TEXT,
    run_dir           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_results (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id            TEXT NOT NULL REFERENCES runs(benchmark_run_id) ON DELETE CASCADE,
    dataset                     TEXT NOT NULL,
    config_fingerprint          TEXT NOT NULL,
    n_questions                 INTEGER,
    prompt_response_accuracy    REAL,
    conditional_accuracy        REAL,
    answer_recovery_rate        REAL,
    instruction_compliance_rate REAL,
    question_majority_accuracy  REAL,
    mean_agreement              REAL,
    mean_prompt_sensitivity     REAL,
    answer_unanimous_rate       REAL,
    prompt_invariant_incorrect_rate REAL
);

CREATE INDEX IF NOT EXISTS idx_run_results_fingerprint ON run_results(config_fingerprint);
CREATE INDEX IF NOT EXISTS idx_run_results_run ON run_results(benchmark_run_id);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open (creating if needed) the run index and ensure the schema exists."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def insert_run(
    conn: sqlite3.Connection,
    *,
    benchmark_run_id: str,
    created_utc: str,
    status: str,
    model: str,
    datasets: Iterable[str],
    run_dir: str,
    model_digest: Optional[str] = None,
    question_count: Optional[int] = None,
    app_version: Optional[str] = None,
    protocol_version: Optional[str] = None,
    finished_utc: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO runs (
            benchmark_run_id, created_utc, finished_utc, status, model,
            model_digest, datasets, question_count, app_version,
            protocol_version, run_dir
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            benchmark_run_id,
            created_utc,
            finished_utc,
            status,
            model,
            model_digest,
            json.dumps(list(datasets)),
            question_count,
            app_version,
            protocol_version,
            run_dir,
        ),
    )
    conn.commit()


def set_run_status(
    conn: sqlite3.Connection,
    benchmark_run_id: str,
    status: str,
    *,
    finished_utc: Optional[str] = None,
) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, finished_utc = COALESCE(?, finished_utc) "
        "WHERE benchmark_run_id = ?",
        (status, finished_utc, benchmark_run_id),
    )
    conn.commit()


def insert_run_result(
    conn: sqlite3.Connection,
    *,
    benchmark_run_id: str,
    dataset: str,
    config_fingerprint: str,
    metrics: Mapping[str, Any],
) -> None:
    """Record one (run, dataset) result row, pulling known metric columns."""
    values = [metrics.get(column) for column in _RESULT_METRIC_COLUMNS]
    columns = ", ".join(_RESULT_METRIC_COLUMNS)
    placeholders = ", ".join("?" for _ in _RESULT_METRIC_COLUMNS)
    conn.execute(
        f"""
        INSERT INTO run_results (
            benchmark_run_id, dataset, config_fingerprint, {columns}
        ) VALUES (?, ?, ?, {placeholders})
        """,
        (benchmark_run_id, dataset, config_fingerprint, *values),
    )
    conn.commit()


def get_run(conn: sqlite3.Connection, benchmark_run_id: str) -> Optional[sqlite3.Row]:
    cursor = conn.execute(
        "SELECT * FROM runs WHERE benchmark_run_id = ?", (benchmark_run_id,)
    )
    return cursor.fetchone()


def list_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All runs, newest first."""
    cursor = conn.execute("SELECT * FROM runs ORDER BY created_utc DESC")
    return list(cursor.fetchall())


def get_run_results(conn: sqlite3.Connection, benchmark_run_id: str) -> list[sqlite3.Row]:
    cursor = conn.execute(
        "SELECT * FROM run_results WHERE benchmark_run_id = ? ORDER BY dataset",
        (benchmark_run_id,),
    )
    return list(cursor.fetchall())


def find_results_by_fingerprint(
    conn: sqlite3.Connection, config_fingerprint: str
) -> list[sqlite3.Row]:
    """Existing local results equivalent to a given fingerprint (joined to runs).

    Powers the "an equivalent local benchmark already exists" prompt on the
    run-setup screen. Only completed runs are considered.
    """
    cursor = conn.execute(
        """
        SELECT r.*, runs.model, runs.model_digest, runs.created_utc,
               runs.status, runs.run_dir
        FROM run_results AS r
        JOIN runs ON runs.benchmark_run_id = r.benchmark_run_id
        WHERE r.config_fingerprint = ? AND runs.status = 'completed'
        ORDER BY runs.created_utc DESC
        """,
        (config_fingerprint,),
    )
    return list(cursor.fetchall())


def delete_run(conn: sqlite3.Connection, benchmark_run_id: str) -> None:
    """Remove a run and its result rows (cascade)."""
    conn.execute("DELETE FROM runs WHERE benchmark_run_id = ?", (benchmark_run_id,))
    conn.commit()