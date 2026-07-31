"""Small disk cache for validated generation results.

Only structured model output and non-sensitive metadata are stored. Raw prompts
and source text never leave ``data/.rag-index`` through this cache.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from ..config import SETTINGS


CACHE_SCHEMA_VERSION = "generation-cache-v1"
CACHE_LIMIT = 256
CACHE_PATH = SETTINGS.repository_root / "data" / ".rag-index" / "generation_cache.json"
CACHE_LOCK = threading.Lock()


def _empty_cache() -> dict:
    return {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}


def _read_cache() -> dict:
    if not CACHE_PATH.is_file():
        return _empty_cache()
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_cache()
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != CACHE_SCHEMA_VERSION
        or not isinstance(payload.get("entries"), dict)
    ):
        return _empty_cache()
    return payload


def get_cached_generation(key: str) -> dict | None:
    with CACHE_LOCK:
        entry = _read_cache().get("entries", {}).get(key)
    if not isinstance(entry, dict) or not isinstance(entry.get("result"), dict):
        return None
    return dict(entry["result"])


def put_cached_generation(key: str, result: dict, *, model: str, task: str) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_LOCK:
        cache = _read_cache()
        entries = cache["entries"]
        entries[key] = {
            "created_at": datetime.now(UTC).isoformat(),
            "model": model,
            "task": task,
            "result": result,
        }
        if len(entries) > CACHE_LIMIT:
            ordered = sorted(
                entries.items(),
                key=lambda item: str(item[1].get("created_at", "")),
            )
            for stale_key, _ in ordered[: len(entries) - CACHE_LIMIT]:
                entries.pop(stale_key, None)

        temporary = CACHE_PATH.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(cache, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(CACHE_PATH)


__all__ = [
    "CACHE_PATH",
    "get_cached_generation",
    "put_cached_generation",
]
