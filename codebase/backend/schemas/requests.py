"""Validated API request objects."""

from __future__ import annotations

from dataclasses import dataclass
import re


ALLOWED_ACTIONS = {"", "summarize", "synthesize", "self_check", "open"}
ALLOWED_SCOPES = {"all", "day01", "day02", "current"}


@dataclass(frozen=True)
class RecallRequest:
    request_id: str
    user_input: str
    selected_pdf: str
    selected_page: int | None
    current_slide_source_id: str
    selected_scope: str
    previous_sources: object
    history: object
    selected_text: object
    action: str

    @classmethod
    def from_payload(cls, payload: object) -> "RecallRequest":
        if not isinstance(payload, dict):
            raise ValueError("invalid_payload")
        user_input = str(payload.get("input", ""))[:500].strip()
        if not user_input:
            raise ValueError("empty_input")
        try:
            selected_page = int(payload.get("page", 0))
        except (TypeError, ValueError):
            selected_page = None
        action = str(payload.get("action", ""))[:40]
        scope = str(payload.get("scope", "all"))[:20]
        request_id = str(payload.get("request_id", ""))[:80].strip()
        if request_id and not re.fullmatch(r"[A-Za-z0-9._:-]+", request_id):
            raise ValueError("invalid_request_id")
        return cls(
            request_id=request_id,
            user_input=user_input,
            selected_pdf=str(payload.get("pdf", ""))[:240],
            selected_page=selected_page,
            current_slide_source_id=str(payload.get("current_slide_source_id", ""))[:280],
            selected_scope=scope if scope in ALLOWED_SCOPES else "all",
            previous_sources=payload.get("previous_sources", []),
            history=payload.get("history", []),
            selected_text=payload.get("selected_text", ""),
            action=action if action in ALLOWED_ACTIONS else "",
        )
