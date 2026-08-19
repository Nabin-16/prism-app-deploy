"""OllamaService — the local inference layer.

Wraps the four Ollama HTTP endpoints the app needs, built on the configurable
base URL (:func:`prism_core.config.ollama_url`) rather than a single hard-coded
global:

* ``/api/tags``     — is Ollama up, and which models are installed (+ digests)?
* ``/api/show``     — details for one model.
* ``/api/generate`` — the single-item inference primitive (ported verbatim from
  the research ``generate_with_ollama``: ``stream=False``, ``temperature`` and
  ``num_predict`` options, ``raise_for_status``, and a hard failure if the reply
  is not JSON or lacks a ``response`` field).
* ``/api/pull``     — download a model, streaming NDJSON progress events.

Pure Python + ``requests``; no Qt. Callers that want progress pass a plain
callback — the GUI worker adapts it to Qt signals.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests

from prism_core import config


class OllamaError(RuntimeError):
    """Any failure talking to Ollama (transport, non-2xx, or malformed reply)."""


@dataclass(frozen=True)
class OllamaModel:
    """One installed model as reported by ``/api/tags``."""

    name: str
    digest: str
    size: Optional[int] = None
    modified_at: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PullProgress:
    """One streamed ``/api/pull`` progress event."""

    status: str
    digest: Optional[str] = None
    total: Optional[int] = None
    completed: Optional[int] = None

    @property
    def percent(self) -> Optional[float]:
        if self.total and self.completed is not None and self.total > 0:
            return 100.0 * self.completed / self.total
        return None


def _url(path: str, base_url: Optional[str]) -> str:
    return config.ollama_url(base_url, path)


def is_available(*, base_url: Optional[str] = None, timeout: float = 5.0) -> bool:
    """True if Ollama answers ``/api/tags`` (used to gate the run-setup UI)."""
    try:
        response = requests.get(_url(config.OLLAMA_TAGS_PATH, base_url), timeout=timeout)
    except requests.RequestException:
        return False
    return response.ok


def list_models(*, base_url: Optional[str] = None, timeout: float = 10.0) -> list[OllamaModel]:
    """Return every installed model with its digest."""
    try:
        response = requests.get(_url(config.OLLAMA_TAGS_PATH, base_url), timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise OllamaError(f"Could not list Ollama models: {exc}") from exc
    except ValueError as exc:
        raise OllamaError("Ollama /api/tags did not return valid JSON.") from exc

    models: list[OllamaModel] = []
    for entry in data.get("models", []):
        models.append(
            OllamaModel(
                name=str(entry.get("name") or entry.get("model") or ""),
                digest=str(entry.get("digest") or ""),
                size=entry.get("size"),
                modified_at=entry.get("modified_at"),
                details=entry.get("details") or {},
            )
        )
    return models


def find_model(
    model_name: str, *, base_url: Optional[str] = None, timeout: float = 10.0
) -> Optional[OllamaModel]:
    """Find an installed model by tag, tolerating an implicit ``:latest``."""
    by_name = {model.name: model for model in list_models(base_url=base_url, timeout=timeout)}
    if model_name in by_name:
        return by_name[model_name]
    if ":" not in model_name and f"{model_name}:latest" in by_name:
        return by_name[f"{model_name}:latest"]
    return None


def model_digest(
    model_name: str, *, base_url: Optional[str] = None, timeout: float = 10.0
) -> Optional[str]:
    """The content digest for an installed model, or None if not installed.

    The digest — not the mutable ``mistral:7b`` tag — is what makes "same model"
    precise in :func:`prism_core.fingerprint.config_fingerprint`.
    """
    model = find_model(model_name, base_url=base_url, timeout=timeout)
    return model.digest if model else None


def show(
    model_name: str, *, base_url: Optional[str] = None, timeout: float = 30.0
) -> dict[str, Any]:
    """Return ``/api/show`` details for a model."""
    try:
        response = requests.post(
            _url(config.OLLAMA_SHOW_PATH, base_url),
            json={"name": model_name},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise OllamaError(f"Could not show model {model_name!r}: {exc}") from exc
    except ValueError as exc:
        raise OllamaError("Ollama /api/show did not return valid JSON.") from exc


def generate(
    *,
    model_name: str,
    prompt_text: str,
    base_url: Optional[str] = None,
    temperature: float = config.TEMPERATURE,
    num_predict: int = config.NUM_PREDICT,
    timeout: float = config.REQUEST_TIMEOUT,
) -> tuple[str, float]:
    """Run one non-streaming generation. Returns ``(response_text, latency_s)``.

    Verbatim port of the research ``generate_with_ollama`` contract: the request
    body, the option keys, ``raise_for_status``, and the hard failures on a
    non-JSON body or a missing ``response`` field are all preserved so inference
    behaves identically to the validated pipeline.
    """
    payload = {
        "model": model_name,
        "prompt": prompt_text,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }

    started = time.perf_counter()
    response = requests.post(
        _url(config.OLLAMA_GENERATE_PATH, base_url),
        json=payload,
        timeout=timeout,
    )
    latency = time.perf_counter() - started
    response.raise_for_status()

    try:
        body = response.json()
    except ValueError as exc:
        raise OllamaError("Ollama /api/generate did not return valid JSON.") from exc

    raw = body.get("response")
    if raw is None:
        raise OllamaError(
            f"Ollama /api/generate response has no 'response' field: {body!r}"
        )
    return str(raw), latency


def pull(
    model_name: str,
    *,
    base_url: Optional[str] = None,
    progress_callback: Optional[Callable[[PullProgress], None]] = None,
    timeout: Optional[float] = None,
) -> None:
    """Download a model, invoking ``progress_callback`` for each NDJSON event.

    Raises :class:`OllamaError` if the stream reports an error. ``timeout`` is
    None by default because a pull can legitimately run for many minutes.
    """
    try:
        with requests.post(
            _url(config.OLLAMA_PULL_PATH, base_url),
            json={"name": model_name, "stream": True},
            stream=True,
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if "error" in event:
                    raise OllamaError(f"Pull failed for {model_name!r}: {event['error']}")
                if progress_callback is not None:
                    progress_callback(
                        PullProgress(
                            status=str(event.get("status", "")),
                            digest=event.get("digest"),
                            total=event.get("total"),
                            completed=event.get("completed"),
                        )
                    )
    except requests.RequestException as exc:
        raise OllamaError(f"Could not pull model {model_name!r}: {exc}") from exc
