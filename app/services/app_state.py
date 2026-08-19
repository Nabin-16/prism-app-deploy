"""
Small persisted app-state file (selected model, theme) — separate from the
prism_core run index (SQLite) because it's UI state, not benchmark data.
Lives at ~/.prism/app_state.json next to the run index and run outputs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_DIR = Path.home() / ".prism"
STATE_PATH = APP_DIR / "app_state.json"

_DEFAULTS: dict[str, Any] = {
    "selected_model": None,
    "theme": "dusk",
}


def _read() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        merged = dict(_DEFAULTS)
        merged.update(data)
        return merged
    except Exception:
        return dict(_DEFAULTS)


def _write(state: dict[str, Any]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_selected_model() -> str | None:
    return _read().get("selected_model")


def set_selected_model(model_tag: str | None) -> None:
    state = _read()
    state["selected_model"] = model_tag
    _write(state)


def get_theme() -> str:
    return _read().get("theme", "dusk")


def set_theme(theme: str) -> None:
    state = _read()
    state["theme"] = theme
    _write(state)