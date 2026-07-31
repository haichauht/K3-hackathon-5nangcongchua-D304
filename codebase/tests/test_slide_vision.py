from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["OPENAI_API_KEY"] = ""

from backend.rag import vision_processor as server


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakePixmap:
    def tobytes(self, format_name: str) -> bytes:
        assert format_name == "png"
        return b"fake-png"


class FakePage:
    def get_pixmap(self, **kwargs) -> FakePixmap:
        assert kwargs["alpha"] is False
        return FakePixmap()


VISION_RESULT = {
    "title": "Workflow diagram",
    "visual_summary": "A sequence of visible boxes connected by arrows.",
    "important_labels": ["Input", "Action"],
    "relationships": ["Input leads to Action"],
    "uncertain_details": ["Small annotation is unreadable"],
}


def test_candidate_rules() -> None:
    assert server.is_visual_slide_candidate("short text", image_count=1, drawing_count=0)
    assert server.is_visual_slide_candidate("short text", image_count=0, drawing_count=8)
    assert not server.is_visual_slide_candidate("short text", image_count=0, drawing_count=7)
    assert not server.is_visual_slide_candidate("x" * (server.RAG_VISION_MAX_TEXT_CHARS + 1), 1, 0)


def test_vision_payload_uses_gpt5_high_detail_and_schema(monkeypatch) -> None:
    original_key = server.OPENAI_API_KEY
    server.OPENAI_API_KEY = "test-key"
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"output_text": json.dumps(VISION_RESULT)})

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    try:
        result = server.call_openai_vision(b"image-bytes")
    finally:
        server.OPENAI_API_KEY = original_key

    assert result == VISION_RESULT
    payload = captured["payload"]
    assert payload["model"] == "gpt-5"
    image_part = payload["input"][0]["content"][1]
    assert image_part["type"] == "input_image"
    assert image_part["detail"] == "high"
    assert image_part["image_url"].startswith("data:image/png;base64,")
    assert payload["text"]["format"]["type"] == "json_schema"
    assert set(payload["text"]["format"]["schema"]["required"]) == {
        "title",
        "visual_summary",
        "important_labels",
        "relationships",
        "uncertain_details",
    }


def test_visual_result_is_cached_and_error_falls_back_to_text(monkeypatch) -> None:
    original_key = server.OPENAI_API_KEY
    original_cache = server.VISION_CACHE_RUNTIME
    original_changed = server.VISION_CACHE_CHANGED
    original_enabled = server.RAG_VISION_ENABLED
    server.OPENAI_API_KEY = "test-key"
    server.RAG_VISION_ENABLED = True
    server.VISION_CACHE_RUNTIME = {"schema_version": "slide-vision-cache-v1", "entries": {}}
    server.VISION_CACHE_CHANGED = False
    calls = {"count": 0}

    def fake_call(image_bytes: bytes, prompt: str):
        del image_bytes, prompt
        calls["count"] += 1
        return VISION_RESULT

    monkeypatch.setattr(server, "call_openai_vision", fake_call)
    pdf = Path("deck.pdf")
    first = server.get_slide_vision(pdf, 2, "pdf-hash", "short", FakePage(), 1, 0)
    second = server.get_slide_vision(pdf, 2, "pdf-hash", "short", FakePage(), 1, 0)
    assert first == VISION_RESULT
    assert second == VISION_RESULT
    assert calls["count"] == 1
    assert server.VISION_CACHE_RUNTIME["entries"]["slides/deck.pdf#page=2"]["status"] == "ok"

    server.VISION_CACHE_RUNTIME = {"schema_version": "slide-vision-cache-v1", "entries": {}}
    calls["count"] = 0

    def failing_call(image_bytes: bytes, prompt: str):
        del image_bytes, prompt
        calls["count"] += 1
        raise OSError("vision unavailable")

    monkeypatch.setattr(server, "call_openai_vision", failing_call)
    assert server.get_slide_vision(pdf, 2, "pdf-hash", "short", FakePage(), 1, 0) is None
    assert server.get_slide_vision(pdf, 2, "pdf-hash", "short", FakePage(), 1, 0) is None
    assert calls["count"] == 1
    assert server.VISION_CACHE_RUNTIME["entries"]["slides/deck.pdf#page=2"]["status"] == "error"

    server.OPENAI_API_KEY = original_key
    server.VISION_CACHE_RUNTIME = original_cache
    server.VISION_CACHE_CHANGED = original_changed
    server.RAG_VISION_ENABLED = original_enabled


def test_disabled_vision_does_not_invalidate_cache_or_force_index_rebuild() -> None:
    original_key = server.OPENAI_API_KEY
    original_cache = server.VISION_CACHE_RUNTIME
    original_changed = server.VISION_CACHE_CHANGED
    original_enabled = server.RAG_VISION_ENABLED
    stale_entry = {
        "pdf_sha256": "old-hash",
        "prompt_hash": "old-prompt",
        "model": "old-model",
        "status": "ok",
        "result": VISION_RESULT,
    }
    server.OPENAI_API_KEY = "test-key"
    server.RAG_VISION_ENABLED = False
    server.VISION_CACHE_RUNTIME = {
        "schema_version": "slide-vision-cache-v1",
        "entries": {"slides/deck.pdf#page=2": stale_entry},
    }
    server.VISION_CACHE_CHANGED = False

    try:
        result = server.get_slide_vision(
            Path("deck.pdf"),
            2,
            "new-hash",
            "short",
            FakePage(),
            1,
            0,
        )
        assert result is None
        assert server.VISION_CACHE_CHANGED is False
        assert (
            server.VISION_CACHE_RUNTIME["entries"]["slides/deck.pdf#page=2"]
            == stale_entry
        )
    finally:
        server.OPENAI_API_KEY = original_key
        server.VISION_CACHE_RUNTIME = original_cache
        server.VISION_CACHE_CHANGED = original_changed
        server.RAG_VISION_ENABLED = original_enabled
