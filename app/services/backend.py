"""
PRISM backend adapter.

This is the *only* place the GUI touches prism_core. It wraps the Qt-free
engine (prism_core.ollama / prism_core.benchmark / prism_core.store) with:

  - a fixed on-disk location for the local run index + run outputs
    (~/.prism/index.db, ~/.prism/runs/<run_id>/...) — the same SQLite file
    and JSON/CSV run artifacts can be committed to a repo, synced, or served
    by a companion website; nothing here is GUI-specific.
  - read helpers scoped to a single model (dataset-level metrics from the
    SQLite index, per-prompt-condition + per-question detail read from the
    latest completed run's own summary files on disk).
  - Qt worker threads (PullWorker, BenchmarkWorker) so the engine's plain
    callback-based progress reporting becomes Qt signals for the GUI.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal

from prism_core import config, ollama, store
from prism_core import benchmark as core_benchmark
from prism_core.benchmark import BenchmarkStage
from app.services import supabase_sync

APP_DIR = Path.home() / ".prism"
DB_PATH = APP_DIR / "index.db"
RUNS_ROOT = APP_DIR / "runs"


# --------------------------------------------------------------------------
# Catalog / Ollama status
# --------------------------------------------------------------------------

def models_catalog() -> dict[str, dict[str, str]]:
    return config.MODELS


def datasets_catalog() -> dict[str, dict[str, Any]]:
    return config.DATASETS


def ollama_available() -> bool:
    return ollama.is_available()


def installed_model_tags() -> set[str]:
    try:
        names = {m.name for m in ollama.list_models()}
    except ollama.OllamaError:
        return set()
    # tolerate an implicit ":latest"
    expanded = set(names)
    for n in names:
        expanded.add(n.split(":")[0])
    return expanded


def is_installed(model_tag: str) -> bool:
    installed = installed_model_tags()
    return model_tag in installed or model_tag.split(":")[0] in installed


def model_label(model_tag: str) -> str:
    meta = config.MODELS.get(model_tag)
    if meta:
        return meta["label"]
    return model_tag


# --------------------------------------------------------------------------
# Local run index (SQLite)
# --------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    return store.connect(DB_PATH)


def _latest_completed_run(conn: sqlite3.Connection, model_tag: str) -> Optional[sqlite3.Row]:
    for row in store.list_runs(conn):  # newest first
        if row["model"] == model_tag and row["status"] == "completed":
            return row
    return None


def has_data(conn: sqlite3.Connection, model_tag: str) -> bool:
    return _latest_completed_run(conn, model_tag) is not None


def models_with_data(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Every model with at least one completed run -> its most recent run row."""
    out: dict[str, sqlite3.Row] = {}
    for row in store.list_runs(conn):
        if row["status"] == "completed" and row["model"] not in out:
            out[row["model"]] = row
    return out


def model_dataset_rows(conn: sqlite3.Connection, model_tag: str) -> list[dict[str, Any]]:
    """Dataset-level aggregate metrics for a model's latest completed run."""
    run = _latest_completed_run(conn, model_tag)
    if run is None:
        return []
    rows = store.get_run_results(conn, run["benchmark_run_id"])
    out = []
    for r in rows:
        d = dict(r)
        d["model"] = model_tag
        out.append(d)
    return out


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def model_prompt_rows(conn: sqlite3.Connection, model_tag: str) -> list[dict[str, Any]]:
    """Per-prompt-condition (P0..P4) breakdown for a model's latest run."""
    run = _latest_completed_run(conn, model_tag)
    if run is None:
        return []
    return _read_csv(Path(run["run_dir"]) / "summary" / "model_prompt_summary.csv")


def model_question_metrics(conn: sqlite3.Connection, model_tag: str) -> list[dict[str, Any]]:
    run = _latest_completed_run(conn, model_tag)
    if run is None:
        return []
    summary_dir = Path(run["run_dir"]) / "summary"
    if not summary_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for f in sorted(summary_dir.glob("*_question_metrics.jsonl")):
        records.extend(_read_jsonl(f))
    return records


def run_info(conn: sqlite3.Connection, model_tag: str) -> Optional[dict[str, Any]]:
    run = _latest_completed_run(conn, model_tag)
    return dict(run) if run is not None else None


# --------------------------------------------------------------------------
# Multi-model comparison (all models with local data at once)
# --------------------------------------------------------------------------

def all_models_dataset_rows(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """{model_tag: [dataset-level rows]} for every model that has a completed
    local run. Powers the all-model comparison tab/PDF, as opposed to the
    single vs. single overlay used elsewhere on the dashboard."""
    out: dict[str, list[dict[str, Any]]] = {}
    for tag in models_with_data(conn):
        out[tag] = model_dataset_rows(conn, tag)
    return out


def all_models_prompt_rows(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for tag in models_with_data(conn):
        out[tag] = model_prompt_rows(conn, tag)
    return out


# --------------------------------------------------------------------------
# Qt worker threads
# --------------------------------------------------------------------------

class PullWorker(QThread):
    """Downloads a model through Ollama, streaming progress."""

    progress = Signal(str, int, int)   # status text, completed_bytes, total_bytes
    finished_ok = Signal(bool, str)     # success, message

    def __init__(self, model_tag: str, parent=None) -> None:
        super().__init__(parent)
        self.model_tag = model_tag
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        def on_progress(p) -> None:
            if self._cancel.is_set():
                return
            self.progress.emit(p.status, int(p.completed or 0), int(p.total or 0))

        try:
            ollama.pull(self.model_tag, progress_callback=on_progress)
            self.finished_ok.emit(True, "")
        except ollama.OllamaError as exc:
            self.finished_ok.emit(False, str(exc))


class SyncWorker(QThread):
    """Pushes local run data to Supabase on a worker thread.

    mode="all"       -> sync_all_completed (Settings screen "Sync now")
    mode="single"    -> sync just `benchmark_run_id` (auto-sync after a run)
    """

    finished_ok = Signal(bool, str)  # ok, message

    def __init__(self, mode: str = "all", benchmark_run_id: Optional[str] = None, parent=None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.benchmark_run_id = benchmark_run_id

    def run(self) -> None:
        conn = store.connect(DB_PATH)
        try:
            if self.mode == "single" and self.benchmark_run_id:
                result = supabase_sync.sync_run(conn, self.benchmark_run_id)
            else:
                result = supabase_sync.sync_all_completed(conn)
            self.finished_ok.emit(result.ok, result.message)
        except Exception as exc:  # noqa: BLE001
            self.finished_ok.emit(False, str(exc))
        finally:
            conn.close()


class BenchmarkWorker(QThread):
    """Runs prism_core.benchmark.run_benchmark for one model on a worker thread."""

    stage = Signal(str, str, object, int, int)      # stage, message, dataset, index, count
    request_progress = Signal(str, str, int, int, float, float, object)
    # dataset, status, request_number, total, percent, avg_latency_seconds, eta_seconds
    finished_ok = Signal(bool, str, object)         # success, message, BenchmarkResult|None

    def __init__(
        self,
        model_tag: str,
        datasets: list[str],
        max_questions: Optional[int] = None,
        overwrite: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.model_tag = model_tag
        self.datasets = datasets
        self.max_questions = max_questions
        self.overwrite = overwrite
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        # sqlite3 connections can't cross threads — open our own here.
        conn = store.connect(DB_PATH)

        def on_stage(s: BenchmarkStage) -> None:
            self.stage.emit(s.stage, s.message, s.dataset, s.dataset_index, s.dataset_count)

        def on_progress(p) -> None:
            self.request_progress.emit(
                p.dataset, p.status, p.request_number, p.total,
                p.percent, p.avg_latency_seconds or 0.0, p.eta_seconds,
            )

        try:
            result = core_benchmark.run_benchmark(
                model_name=self.model_tag,
                datasets=self.datasets,
                runs_root=RUNS_ROOT,
                conn=conn,
                max_questions=self.max_questions,
                overwrite=self.overwrite,
                stage_callback=on_stage,
                progress_callback=on_progress,
                cancel_event=self.cancel_event,
            )
            if result.cancelled:
                self.finished_ok.emit(False, "Cancelled.", result)
            else:
                self.finished_ok.emit(True, "", result)
        except Exception as exc:  # noqa: BLE001 - surface any engine error to the GUI
            self.finished_ok.emit(False, str(exc), None)
        finally:
            conn.close()