"""Optional slide Vision enrichment with safe persistent cache metadata."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ..config import (
    SETTINGS,
    VISION_CACHE_FILE,
    VISION_PROMPT,
    VISION_PROMPT_HASH,
    VISION_SCHEMA,
)
from ..utils.text_utils import clean_extracted_text, extract_openai_text, sanitize_content

OPENAI_API_KEY = SETTINGS.openai_api_key
MODEL = SETTINGS.openai_model
RAG_INDEX_DIR = SETTINGS.rag_index_dir
DATA_ROOT = SETTINGS.data_root
RAG_VISION_ENABLED = SETTINGS.rag_vision_enabled
RAG_VISION_MODEL = SETTINGS.rag_vision_model
RAG_VISION_MAX_TEXT_CHARS = SETTINGS.rag_vision_max_text_chars
RAG_VISION_RENDER_SCALE = SETTINGS.rag_vision_render_scale
RAG_VISION_TIMEOUT_SECONDS = SETTINGS.rag_vision_timeout_seconds
VISION_CACHE_RUNTIME: dict | None = None
VISION_CACHE_CHANGED = False
VISION_RETRY_ERRORS = False
VISION_STATS = {"candidate_pages": 0, "vision_calls": 0, "cache_hits": 0, "errors": 0}


def is_openai_ready() -> bool:
    return bool(OPENAI_API_KEY)


def vision_cache_path() -> Path | None:
    expected_dir = (DATA_ROOT.parent / ".rag-index").resolve()
    if RAG_INDEX_DIR != expected_dir:
        return None
    return RAG_INDEX_DIR / VISION_CACHE_FILE


def load_vision_cache() -> dict:
    global VISION_CACHE_RUNTIME
    if VISION_CACHE_RUNTIME is not None:
        return VISION_CACHE_RUNTIME

    cache = {"schema_version": "slide-vision-cache-v1", "entries": {}}
    path = vision_cache_path()
    if path is not None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("entries"), dict):
                cache.update(
                    {
                        "schema_version": loaded.get("schema_version", "slide-vision-cache-v1"),
                        "entries": loaded["entries"],
                    }
                )
        except (OSError, ValueError, TypeError):
            pass
    VISION_CACHE_RUNTIME = cache
    return cache


def vision_cache_payload() -> dict:
    cache = load_vision_cache()
    # Do not persist the local configuration error produced when no API key is
    # available. It is not a Vision result and must not suppress a later build
    # after the user configures OPENAI_API_KEY.
    entries = {
        key: value
        for key, value in cache.get("entries", {}).items()
        if not (
            isinstance(value, dict)
            and value.get("status") == "error"
            and value.get("error_type") == "RuntimeError"
        )
    }
    return {
        "schema_version": "slide-vision-cache-v1",
        "model": RAG_VISION_MODEL,
        "prompt_hash": VISION_PROMPT_HASH,
        "entries": entries,
    }


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_visual_slide_candidate(text: str, image_count: int, drawing_count: int) -> bool:
    if len(clean_extracted_text(text)) > RAG_VISION_MAX_TEXT_CHARS:
        return False
    return image_count > 0 or drawing_count >= 8


def normalize_vision_result(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None

    def clean_string(item: object, max_chars: int) -> str:
        return sanitize_content(str(item or ""), max_chars=max_chars)

    def clean_list(item: object, max_items: int = 20) -> list[str]:
        if not isinstance(item, list):
            return []
        return [clean_string(entry, 220) for entry in item[:max_items] if str(entry or "").strip()]

    return {
        "title": clean_string(value.get("title"), 180),
        "visual_summary": clean_string(value.get("visual_summary"), 1000),
        "important_labels": clean_list(value.get("important_labels")),
        "relationships": clean_list(value.get("relationships")),
        "uncertain_details": clean_list(value.get("uncertain_details")),
    }


def call_openai_vision(image_bytes: bytes, prompt: str = VISION_PROMPT, timeout: int = RAG_VISION_TIMEOUT_SECONDS) -> dict:
    if not is_openai_ready():
        raise RuntimeError("openai_not_configured")

    image_data = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": RAG_VISION_MODEL,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_data}",
                        "detail": "high",
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "vlearn_slide_vision",
                "strict": True,
                "schema": VISION_SCHEMA,
            }
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    result = normalize_vision_result(json.loads(extract_openai_text(parsed)))
    if result is None:
        raise ValueError("invalid_vision_json")
    return result


def format_vision_context(vision: dict | None) -> str:
    if not vision:
        return ""
    parts = []
    if vision.get("title"):
        parts.append(f"Visual title: {vision['title']}")
    if vision.get("visual_summary"):
        parts.append(f"Visual summary: {vision['visual_summary']}")
    if vision.get("important_labels"):
        parts.append("Important visual labels: " + ", ".join(vision["important_labels"]))
    if vision.get("relationships"):
        parts.append("Visible relationships: " + "; ".join(vision["relationships"]))
    if vision.get("uncertain_details"):
        parts.append("Uncertain visual details: " + "; ".join(vision["uncertain_details"]))
    return "\n".join(parts)


def get_slide_vision(
    pdf: Path,
    page_number: int,
    pdf_hash: str,
    text: str,
    page,
    image_count: int,
    drawing_count: int,
) -> dict | None:
    global VISION_CACHE_CHANGED
    if not is_visual_slide_candidate(text, image_count, drawing_count):
        return None

    VISION_STATS["candidate_pages"] += 1
    cache = load_vision_cache()
    entries = cache.setdefault("entries", {})
    cache_key = f"slides/{pdf.name}#page={page_number}"
    entry = entries.get(cache_key)
    entry_matches = isinstance(entry, dict) and all(
        entry.get(key) == expected
        for key, expected in (
            ("pdf_sha256", pdf_hash),
            ("prompt_hash", VISION_PROMPT_HASH),
            ("model", RAG_VISION_MODEL),
        )
    )
    if entry_matches:
        if entry.get("status") == "ok":
            cached_result = normalize_vision_result(entry.get("result"))
            if cached_result:
                VISION_STATS["cache_hits"] += 1
                return cached_result
        if entry.get("status") == "error" and (
            not VISION_RETRY_ERRORS or not is_openai_ready()
        ):
            VISION_STATS["cache_hits"] += 1
            return None

    # A disabled/unavailable Vision provider cannot refresh a stale entry.
    # Keep the cache untouched so startup does not mark the whole RAG index as
    # changed and unnecessarily rebuild every persisted dense embedding.
    if not RAG_VISION_ENABLED or not is_openai_ready():
        return None

    if entry is not None:
        entries.pop(cache_key, None)
        VISION_CACHE_CHANGED = True

    try:
        import fitz

        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(RAG_VISION_RENDER_SCALE, RAG_VISION_RENDER_SCALE),
            alpha=False,
        )
        VISION_STATS["vision_calls"] += 1
        result = call_openai_vision(pixmap.tobytes("png"), prompt=VISION_PROMPT)
        entries[cache_key] = {
            "pdf_relative_path": f"slides/{pdf.name}",
            "page": page_number,
            "pdf_sha256": pdf_hash,
            "prompt_hash": VISION_PROMPT_HASH,
            "model": RAG_VISION_MODEL,
            "status": "ok",
            "result": result,
        }
        VISION_CACHE_CHANGED = True
        return result
    except Exception as error:
        VISION_STATS["errors"] += 1
        entries[cache_key] = {
            "pdf_relative_path": f"slides/{pdf.name}",
            "page": page_number,
            "pdf_sha256": pdf_hash,
            "prompt_hash": VISION_PROMPT_HASH,
            "model": RAG_VISION_MODEL,
            "status": "error",
            "error_type": type(error).__name__,
        }
        VISION_CACHE_CHANGED = True
        return None


def reset_vision_state(*, retry_errors: bool = False) -> None:
    global VISION_CACHE_RUNTIME, VISION_CACHE_CHANGED, VISION_RETRY_ERRORS, VISION_STATS
    VISION_CACHE_RUNTIME = None
    VISION_CACHE_CHANGED = False
    VISION_RETRY_ERRORS = retry_errors
    VISION_STATS = {"candidate_pages": 0, "vision_calls": 0, "cache_hits": 0, "errors": 0}
