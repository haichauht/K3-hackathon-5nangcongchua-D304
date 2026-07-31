"""HTTP routing for the dependency-free VLearn Recall server."""

from __future__ import annotations

import json
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from backend.capabilities import health_status
from backend.config import SETTINGS
from backend.rag.document_loader import list_library
from backend.schemas.requests import RecallRequest
from backend.security.guardrails import fallback_classify
from backend.services.recall_service import (
    safe_history,
    safe_history_sources,
    safe_selected_text,
    search_recall,
)
from backend.services.source_service import (
    render_slide_page,
    resolve_slide_file,
    transcript_segment_payload,
)


MAX_REQUEST_BYTES = 64 * 1024


class RequestError(ValueError):
    """A client-visible request validation failure."""

    def __init__(self, message: str, *, status: int = 400, code: str = "BAD_REQUEST"):
        super().__init__(message)
        self.status = status
        self.code = code


class VLearnRequestHandler(BaseHTTPRequestHandler):
    """Small HTTP adapter; application decisions live in services."""

    server_version = "VLearnRecall/2.0"

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()
            return
        self.send_error(404)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/health":
            self._send_json(health_status())
            return
        if parsed.path == "/api/library":
            self._send_json(list_library())
            return
        if parsed.path == "/api/transcript-segment":
            self._handle_transcript_segment(query)
            return
        if parsed.path == "/api/slide-page":
            self._handle_slide_page(query)
            return
        if parsed.path.startswith("/data/slides/"):
            self._handle_slide_file(parsed.path)
            return

        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urllib.parse.urlparse(self.path).path
        if path not in {"/api/recall-intent", "/api/recall-search"}:
            self._send_json(
                {"error": {"code": "NOT_FOUND", "message": "Endpoint not found."}},
                status=404,
            )
            return

        try:
            payload = self._read_json_body()
            request = RecallRequest.from_payload(payload)
        except RequestError as exc:
            self._send_json(
                {"error": {"code": exc.code, "message": str(exc)}},
                status=exc.status,
            )
            return
        except ValueError as exc:
            self._send_json(
                {"error": {"code": "INVALID_REQUEST", "message": str(exc)}},
                status=400,
            )
            return

        if path == "/api/recall-intent":
            response = fallback_classify(request.user_input)
            response["request_id"] = request.request_id
            self._send_json(response)
            return

        response = search_recall(
            request.user_input,
            selected_pdf=request.selected_pdf,
            selected_page=request.selected_page,
            action=request.action,
            previous_sources=safe_history_sources(request.previous_sources),
            history=safe_history(request.history),
            selected_scope=request.selected_scope,
            selected_text=safe_selected_text(request.selected_text),
            current_slide_source_id=request.current_slide_source_id,
        )
        response["request_id"] = request.request_id
        self._send_json(response)

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise RequestError("Invalid Content-Length header.") from exc

        if content_length <= 0:
            raise RequestError("JSON request body is required.")
        if content_length > MAX_REQUEST_BYTES:
            raise RequestError(
                "Request body is too large.",
                status=413,
                code="PAYLOAD_TOO_LARGE",
            )

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestError("Request body must be valid UTF-8 JSON.") from exc
        if not isinstance(payload, dict):
            raise RequestError("Request body must be a JSON object.")
        return payload

    def _handle_transcript_segment(self, query: dict[str, list[str]]) -> None:
        segment_id = self._first_query_value(query, "segment_id")
        payload = transcript_segment_payload(segment_id)
        if payload is None:
            self._send_json(
                {
                    "error": {
                        "code": "SOURCE_NOT_FOUND",
                        "message": "Transcript segment not found.",
                    }
                },
                status=404,
            )
            return
        self._send_json(payload)

    def _handle_slide_page(self, query: dict[str, list[str]]) -> None:
        filename = self._first_query_value(query, "file")
        try:
            page = max(1, int(self._first_query_value(query, "page") or "1"))
        except ValueError:
            self._send_json(
                {"error": {"code": "INVALID_PAGE", "message": "Page must be an integer."}},
                status=400,
            )
            return

        try:
            body = render_slide_page(filename, page)
        except (FileNotFoundError, IndexError):
            self._send_json(
                {
                    "error": {
                        "code": "SOURCE_NOT_FOUND",
                        "message": "Slide page not found.",
                    }
                },
                status=404,
            )
            return
        except RuntimeError as exc:
            self._send_json(
                {
                    "error": {
                        "code": "RENDERER_UNAVAILABLE",
                        "message": str(exc),
                    }
                },
                status=503,
            )
            return
        self._send_bytes(
            body,
            content_type="image/png",
            cache_control="private, max-age=60",
        )

    def _handle_slide_file(self, path: str) -> None:
        relative = urllib.parse.unquote(path.removeprefix("/data/slides/"))
        resolved = resolve_slide_file(relative)
        if resolved is None:
            self.send_error(404)
            return
        self._send_file(resolved, cache_control="private, max-age=60")

    def _serve_static(self, path: str) -> None:
        request_path = urllib.parse.unquote(path)
        if request_path in {"", "/"}:
            request_path = "/index.html"

        candidate = (SETTINGS.codebase_root / request_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(SETTINGS.codebase_root)
        except ValueError:
            self.send_error(403)
            return

        if not candidate.is_file():
            self.send_error(404)
            return
        # Development/hackathon UI must not keep an older JS state machine
        # after the backend has been restarted.
        self._send_file(candidate, cache_control="no-store")

    @staticmethod
    def _first_query_value(query: dict[str, list[str]], key: str) -> str:
        values = query.get(key)
        return values[0].strip() if values else ""

    def _send_file(self, path: Path, *, cache_control: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send_bytes(body, content_type=content_type, cache_control=cache_control)

    def _send_bytes(
        self,
        body: bytes,
        *,
        content_type: str,
        status: int = 200,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(
            body,
            content_type="application/json; charset=utf-8",
            status=status,
        )

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        allowed = {item.rstrip("/") for item in SETTINGS.cors_origins}
        if origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def log_message(self, format: str, *args: object) -> None:
        # Keep the built-in concise access log while making the service label explicit.
        super().log_message("vlearn %s", format % args)


__all__ = ["MAX_REQUEST_BYTES", "VLearnRequestHandler"]
