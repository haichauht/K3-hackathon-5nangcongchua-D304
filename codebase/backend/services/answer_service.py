"""Grounded content orchestration after deterministic retrieval."""

from __future__ import annotations

from ..config import MIN_FOUND_SCORE, SETTINGS
from ..utils.text_utils import safe_history_items
from .generation_service import (
    AIUnavailableError,
    InsufficientEvidenceError,
    InvalidModelOutputError,
    citations_for_generation,
    configured_generation_mode,
    generate_grounded_content,
    generation_to_text,
)
from .learning_action_service import (
    citation_marker,
    citation_token,
    display_source_name,
    fallback_self_check,
    fallback_source_answer,
    fallback_source_comparison,
    fallback_source_summary,
    fallback_source_synthesis,
    format_evidence,
    format_public_sources,
    normalize_task_answer,
    sanitize_structured_answer,
    slide_source_map,
)
from .source_service import public_result


MODEL = SETTINGS.openai_model
OPENAI_API_KEY = SETTINGS.openai_api_key
OPENAI_ANSWER_TIMEOUT_SECONDS = SETTINGS.openai_answer_timeout_seconds
OPENAI_REASONING_EFFORT = SETTINGS.openai_reasoning_effort
OPENAI_MAX_OUTPUT_TOKENS = SETTINGS.openai_max_output_tokens
RECALL_FOLLOW_UP_OPTIONS = [
    "Tóm tắt nguồn này",
    "Tổng hợp nội dung liên quan",
    "Mở trang slide",
]
safe_history = safe_history_items


def is_openai_ready() -> bool:
    """True only when generation will actually execute through OpenAI."""

    return configured_generation_mode() == "openai"


def generation_runtime_mode() -> str:
    return configured_generation_mode()


def format_history(history: list[dict] | None) -> str:
    cleaned = safe_history(history or [])
    if not cleaned:
        return "(không có lịch sử hội thoại liên quan)"
    return "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in cleaned
    )


def build_grounded_answer(
    user_input: str,
    query: str,
    source_results: list[dict],
    history: list[dict] | None = None,
    selected_text: str = "",
    task: str = "answer",
) -> dict:
    """Generate structured content while leaving retrieval/citations deterministic."""

    del query, history, selected_text
    selected = source_results[:1] if task == "summarize_first" else source_results[:3]
    try:
        generated = generate_grounded_content(task, user_input, selected)
    except InsufficientEvidenceError:
        return {
            "status": "NOT_FOUND",
            "answer": "",
            "message": "Nguồn được chọn chưa đủ nội dung sạch để tạo câu trả lời an toàn.",
            "confidence": "low",
            "follow_up_options": RECALL_FOLLOW_UP_OPTIONS,
            "source_map": [],
            "citations": [],
            "source": "insufficient_evidence",
            "generation": None,
            "generation_meta": {
                "mode": generation_runtime_mode(),
                "model": "",
                "cache_hit": False,
                "call_count": 0,
                "degraded": generation_runtime_mode() == "degraded",
            },
        }
    except AIUnavailableError:
        return {
            "status": "AI_UNAVAILABLE",
            "answer": "",
            "message": "Tạm thời chưa thể tạo phần tóm tắt. Vui lòng thử lại.",
            "confidence": retrieval_confidence(selected),
            "follow_up_options": RECALL_FOLLOW_UP_OPTIONS,
            "source_map": [],
            "citations": [],
            "source": "ai_unavailable",
            "generation": None,
            "retryable": True,
            "error": {"code": "AI_UNAVAILABLE"},
            "generation_meta": {
                "mode": "openai",
                "model": MODEL,
                "cache_hit": False,
                "call_count": 1,
                "degraded": False,
            },
        }
    except InvalidModelOutputError:
        return {
            "status": "INVALID_MODEL_OUTPUT",
            "answer": "",
            "message": "Kết quả AI chưa đạt định dạng an toàn. Vui lòng thử lại.",
            "confidence": retrieval_confidence(selected),
            "follow_up_options": RECALL_FOLLOW_UP_OPTIONS,
            "source_map": [],
            "citations": [],
            "source": "invalid_model_output",
            "generation": None,
            "retryable": True,
            "error": {"code": "INVALID_MODEL_OUTPUT"},
            "generation_meta": {
                "mode": "openai",
                "model": MODEL,
                "cache_hit": False,
                "call_count": 2,
                "degraded": False,
            },
        }

    generation = generated.generation
    citations = citations_for_generation(generation, selected)
    source_label = "openai" if generated.mode == "openai" else "extractive"
    return {
        "status": "FOUND",
        "answer": generation_to_text(generation),
        "message": "",
        "confidence": retrieval_confidence(selected),
        "follow_up_options": RECALL_FOLLOW_UP_OPTIONS,
        "source_map": citations,
        "citations": citations,
        "source": source_label,
        "generation": generation,
        "generation_meta": {
            "mode": generated.mode,
            "model": generated.model,
            "cache_hit": generated.cache_hit,
            "call_count": generated.call_count,
            "degraded": generated.degraded,
        },
    }


def fallback_grounded_answer(
    results: list[dict],
    user_input: str = "",
    task: str = "answer",
) -> dict:
    """Compatibility helper for explicit offline/debug callers.

    The production path calls ``build_grounded_answer`` and never invokes this
    after an OpenAI error.
    """

    del user_input
    if task == "summarize_first":
        answer = fallback_source_summary(results[:1])
    elif task == "synthesize_sources":
        answer = fallback_source_synthesis(results[:3])
    elif task == "compare_sources":
        answer = fallback_source_comparison(results[:3])
    elif task == "self_check":
        answer = fallback_self_check(results[:3])
    else:
        answer = fallback_source_answer(results[:3])
    public_sources = [public_result(result) for result in results[:3]]
    return {
        "status": "FOUND" if results else "NOT_FOUND",
        "answer": answer,
        "confidence": retrieval_confidence(results),
        "follow_up_options": RECALL_FOLLOW_UP_OPTIONS,
        "source_map": slide_source_map(public_sources, []),
        "citations": slide_source_map(public_sources, []),
        "source": "extractive",
        "generation": None,
        "generation_meta": {
            "mode": "extractive",
            "model": "",
            "cache_hit": False,
            "call_count": 0,
            "degraded": False,
        },
    }


def retrieval_confidence(results: list[dict]) -> str:
    scores = []
    for result in results[:3]:
        try:
            scores.append(int(result.get("score", 0)))
        except (TypeError, ValueError):
            continue
    if not scores or scores[0] < MIN_FOUND_SCORE:
        return "low"
    if scores[0] >= 72 and (len(scores) == 1 or scores[0] - scores[1] >= 12):
        return "high"
    return "medium"


def cap_confidence(candidate: str, evidence: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    safe_candidate = candidate if candidate in order else "medium"
    safe_evidence = evidence if evidence in order else "low"
    return safe_candidate if order[safe_candidate] <= order[safe_evidence] else safe_evidence


__all__ = [
    "build_grounded_answer",
    "cap_confidence",
    "citation_marker",
    "citation_token",
    "display_source_name",
    "fallback_grounded_answer",
    "format_evidence",
    "format_history",
    "format_public_sources",
    "generation_runtime_mode",
    "is_openai_ready",
    "normalize_task_answer",
    "retrieval_confidence",
    "sanitize_structured_answer",
]
