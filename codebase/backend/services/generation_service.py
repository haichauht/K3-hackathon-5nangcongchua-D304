"""Grounded content generation with deterministic source and citation control."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ..config import SETTINGS
from ..schemas.generation import TASK_SCHEMAS, StrictGenerationModel
from ..utils.text_utils import (
    clean_extracted_text,
    remove_vietnamese_tone,
    sanitize_content,
    tokenize,
)
from .generation_cache import get_cached_generation, put_cached_generation
from .generation_prompts import (
    PROMPT_BUILDERS,
    PROMPT_VERSION,
    build_repair_prompt,
    prompt_fingerprint,
)
from .learning_action_service import (
    ideas_are_near_duplicates,
    source_evidence_bullets,
)
from .source_service import public_result


MODEL = SETTINGS.openai_model
OPENAI_API_KEY = SETTINGS.openai_api_key
OPENAI_TIMEOUT_SECONDS = SETTINGS.openai_answer_timeout_seconds
OPENAI_REASONING_EFFORT = SETTINGS.openai_reasoning_effort
OPENAI_MAX_OUTPUT_TOKENS = SETTINGS.openai_max_output_tokens
MAX_SOURCE_CHARS = 1200
MAX_GENERATION_CHARS = 3600

RAW_CITATION_RE = re.compile(
    r"\[\[[^\]\r\n]+\]\]|\[T\d{2}-\d{3}\]|\bCitation\s*:",
    flags=re.IGNORECASE,
)
SPACED_CAPITAL_RE = re.compile(
    r"(?<!\w)(?:[A-ZÀ-ỸĐ]\s+){3,}[A-ZÀ-ỸĐ](?!\w)"
)
FOOTER_RE = re.compile(
    r"\b(?:AI\s+IN\s+ACTION\s*-\s*HACKATHON|VINUNIVERSITY)\b.*$",
    flags=re.IGNORECASE,
)


class GenerationError(RuntimeError):
    code = "GENERATION_ERROR"
    retryable = False


class AIUnavailableError(GenerationError):
    code = "AI_UNAVAILABLE"
    retryable = True


class InvalidModelOutputError(GenerationError):
    code = "INVALID_MODEL_OUTPUT"
    retryable = True


class InsufficientEvidenceError(GenerationError):
    code = "INSUFFICIENT_EVIDENCE"
    retryable = False


@dataclass(frozen=True)
class GenerationResult:
    generation: dict
    mode: str
    model: str
    cache_hit: bool
    call_count: int
    degraded: bool


def configured_generation_mode() -> str:
    mode = SETTINGS.ai_generation_mode
    if mode == "extractive":
        return "extractive"
    if mode == "openai":
        return "openai" if OPENAI_API_KEY else "unavailable"
    return "openai" if OPENAI_API_KEY else "degraded"


def _finish_sentence(value: str) -> str:
    compact = RAW_CITATION_RE.sub(" ", value)
    previous = None
    while previous != compact:
        previous = compact
        compact = SPACED_CAPITAL_RE.sub(" ", compact)
    compact = re.sub(r"\s+", " ", compact).strip(" -:;")
    if compact and compact[-1] not in ".!?":
        compact += "."
    return compact


def _safe_heading(source: dict, max_chars: int = 110) -> str:
    raw = clean_extracted_text(
        str(source.get("title") or source.get("document_title") or source.get("lesson") or "")
    )
    compact = re.sub(r"\s+", " ", raw).replace("…", "").strip(" -:;")
    if len(compact) > max_chars:
        candidate = compact[:max_chars].rstrip()
        boundary = max(candidate.rfind(" — "), candidate.rfind(": "), candidate.rfind(" "))
        compact = candidate[:boundary].rstrip(" -:;") if boundary >= max_chars // 2 else candidate
    return compact or "Nội dung bài giảng"


def _dedupe_lines(value: str, title: str) -> str:
    title_key = remove_vietnamese_tone(title.lower())
    seen: set[str] = set()
    kept: list[str] = []
    for raw_line in clean_extracted_text(value).splitlines():
        line = RAW_CITATION_RE.sub(" ", raw_line)
        previous = None
        while previous != line:
            previous = line
            line = SPACED_CAPITAL_RE.sub(" ", line)
        line = FOOTER_RE.sub("", line).strip(" -|")
        line = re.sub(r"\b\d+\s*/\s*\d+\b", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        key = remove_vietnamese_tone(line.lower())
        if not line or key == title_key or key in seen:
            continue
        seen.add(key)
        kept.append(line)
    return " ".join(kept)


def _bounded_complete_text(value: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= max_chars:
        return compact
    candidate = compact[: max_chars + 1]
    boundary = max(candidate.rfind(". "), candidate.rfind("? "), candidate.rfind("! "))
    if boundary >= max_chars // 3:
        return candidate[: boundary + 1].strip()
    # A long OCR clause without a real boundary is not safe generation evidence.
    return ""


def source_projection(source: dict) -> dict:
    source_type = str(source.get("source_type") or source.get("type") or "slide").lower()
    if source_type not in {"slide", "transcript"}:
        raise InsufficientEvidenceError("unsupported_source_type")

    title = _safe_heading(source, max_chars=120)
    raw_content = str(
        source.get("context")
        or source.get("text")
        or source.get("preview")
        or ""
    )
    cleaned = _dedupe_lines(raw_content, title)
    content = _bounded_complete_text(cleaned)
    if not content:
        bullets = source_evidence_bullets(source, limit=4)
        content = _bounded_complete_text(" ".join(_finish_sentence(item) for item in bullets))
    visual = _bounded_complete_text(
        sanitize_content(str(source.get("visual_summary") or ""), max_chars=420),
        max_chars=420,
    )
    if not content and not visual:
        raise InsufficientEvidenceError("source_has_no_clean_evidence")
    return {
        "source_type": source_type,
        "title": title or "Nội dung bài giảng",
        "content": content,
        "visual_summary": visual,
    }


def _source_identity(source: dict) -> str:
    return str(
        source.get("source_id")
        or source.get("citation")
        or source.get("source")
        or f"{source.get('file', '')}#page={source.get('page', '')}"
    )


def _cache_key(
    task: str,
    messages: list[dict],
    sources: list[dict],
    projections: list[dict],
) -> str:
    source_descriptors = [
        {
            "source_id": _source_identity(source),
            "file": source.get("file", ""),
            "page": source.get("page"),
            "projection_hash": hashlib.sha256(
                json.dumps(projection, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }
        for source, projection in zip(sources, projections)
    ]
    payload = {
        "task": task,
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": hashlib.sha256(
            prompt_fingerprint(messages).encode("utf-8")
        ).hexdigest(),
        "sources": source_descriptors,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _normalize_indexes(indexes: object, source_count: int) -> list[int]:
    if not isinstance(indexes, list):
        return []
    values: list[int] = []
    for value in indexes:
        if isinstance(value, bool):
            continue
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= index < source_count and index not in values:
            values.append(index)
    return values


def _text_values(payload: object) -> list[str]:
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, list):
        values: list[str] = []
        for item in payload:
            values.extend(_text_values(item))
        return values
    if isinstance(payload, dict):
        values = []
        for key, value in payload.items():
            if key not in {"kind"}:
                values.extend(_text_values(value))
        return values
    return []


def _dedupe_items(items: list[dict], text_key: str) -> list[dict]:
    kept: list[dict] = []
    for item in items:
        text = str(item.get(text_key, ""))
        if any(ideas_are_near_duplicates(text, str(existing.get(text_key, ""))) for existing in kept):
            continue
        kept.append(item)
    return kept


def _normalize_declarative_fields(task: str, payload: dict) -> None:
    """Add harmless terminal punctuation after safety validation.

    Missing terminal punctuation is not proof that a Vietnamese sentence is
    semantically incomplete. Source indexes and factual content stay intact.
    """

    if task == "answer":
        payload["answer"] = _finish_sentence(payload["answer"])
        for item in payload["key_points"]:
            item["text"] = _finish_sentence(item["text"])
    elif task == "summarize_first":
        payload["main_idea"] = _finish_sentence(payload["main_idea"])
        payload["takeaway"] = _finish_sentence(payload["takeaway"])
        for item in payload["key_points"]:
            item["text"] = _finish_sentence(item["text"])
    elif task == "synthesize_sources":
        payload["overview"] = _finish_sentence(payload["overview"])
        payload["connections"] = _finish_sentence(payload["connections"])
        for item in payload["themes"]:
            item["summary"] = _finish_sentence(item["summary"])
    elif task == "compare_sources":
        for item in payload["comparisons"]:
            item["similarity"] = _finish_sentence(item["similarity"])
            item["difference"] = _finish_sentence(item["difference"])


def _validate_semantics(
    task: str,
    payload: dict,
    schema: type[StrictGenerationModel],
    source_count: int,
) -> dict:
    try:
        validated = schema.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise InvalidModelOutputError("schema_validation_failed") from exc

    nested_collections: list[tuple[str, str, int]] = []
    if task in {"answer", "summarize_first"}:
        nested_collections.append(("key_points", "text", 1 if task == "answer" else 2))
    elif task == "synthesize_sources":
        nested_collections.append(("themes", "summary", 1))
    elif task == "compare_sources":
        nested_collections.append(("comparisons", "similarity", 1))
    elif task == "self_check":
        nested_collections.append(("questions", "question", 1))

    referenced: set[int] = set()
    for collection_key, text_key, minimum in nested_collections:
        items = validated.get(collection_key, [])
        for item in items:
            item["source_indexes"] = _normalize_indexes(
                item.get("source_indexes"),
                source_count,
            )
            if not item["source_indexes"]:
                raise InvalidModelOutputError("item_has_no_valid_source")
            referenced.update(item["source_indexes"])
        items = _dedupe_items(items, text_key)
        if len(items) < minimum:
            raise InvalidModelOutputError("duplicate_or_missing_items")
        validated[collection_key] = items

    used = _normalize_indexes(validated.get("used_source_indexes"), source_count)
    referenced.update(used)
    if task == "summarize_first":
        referenced = {0} if source_count else set()
    if not referenced:
        raise InvalidModelOutputError("no_valid_used_source")
    validated["used_source_indexes"] = sorted(referenced)

    all_text = _text_values(validated)
    if sum(len(value) for value in all_text) > MAX_GENERATION_CHARS:
        raise InvalidModelOutputError("generation_too_long")
    for value in all_text:
        if RAW_CITATION_RE.search(value):
            raise InvalidModelOutputError("model_created_citation")
        if "…" in value or SPACED_CAPITAL_RE.search(value):
            raise InvalidModelOutputError("raw_ocr_or_truncation_detected")

    if task == "self_check":
        if any(not item["question"].rstrip().endswith("?") for item in validated["questions"]):
            raise InvalidModelOutputError("self_check_question_is_fragment")
        forbidden = " ".join(all_text)
        if re.search(r"\b(?:đáp án|lời giải|answer)\s*:", forbidden, flags=re.IGNORECASE):
            raise InvalidModelOutputError("self_check_leaks_answer")

    _normalize_declarative_fields(task, validated)

    return validated


def _openai_request(
    messages: list[dict],
    schema: type[StrictGenerationModel],
) -> dict:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
    except ImportError as exc:
        raise AIUnavailableError("openai_sdk_not_installed") from exc

    client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=OPENAI_TIMEOUT_SECONDS,
        max_retries=0,
    )
    request: dict[str, Any] = {
        "model": MODEL,
        "input": messages,
        "text_format": schema,
        "max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS,
        "store": False,
    }
    if OPENAI_REASONING_EFFORT:
        request["reasoning"] = {"effort": OPENAI_REASONING_EFFORT}
    try:
        response = client.responses.parse(**request)
    except (APIConnectionError, APIStatusError, APITimeoutError) as exc:
        raise AIUnavailableError(exc.__class__.__name__) from exc
    except Exception as exc:
        # Parsing/finish-reason failures are invalid model output, not a
        # license to emit raw extractive content in OpenAI mode.
        raise InvalidModelOutputError(exc.__class__.__name__) from exc

    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise InvalidModelOutputError("missing_output_parsed")
    if isinstance(parsed, StrictGenerationModel):
        return parsed.model_dump()
    if hasattr(parsed, "model_dump"):
        return parsed.model_dump()
    if isinstance(parsed, dict):
        return dict(parsed)
    raise InvalidModelOutputError("unexpected_output_type")


def _fallback_generation(task: str, sources: list[dict]) -> dict:
    if not sources:
        raise InsufficientEvidenceError("no_sources")

    if task == "summarize_first":
        source = sources[0]
        bullets = source_evidence_bullets(source, limit=4)
        if len(bullets) < 2:
            raise InsufficientEvidenceError("not_enough_summary_points")
        points = [
            {"text": _finish_sentence(item), "source_indexes": [0]}
            for item in bullets[:4]
        ]
        return {
            "kind": "slide_summary",
            "title": _safe_heading(source),
            "main_idea": _finish_sentence(bullets[0]),
            "key_points": points,
            "takeaway": _finish_sentence(bullets[-1]),
            "used_source_indexes": [0],
        }

    if task == "synthesize_sources":
        themes: list[dict] = []
        for index, source in enumerate(sources[:3]):
            bullets = source_evidence_bullets(source, limit=2)
            if not bullets:
                continue
            summary = _finish_sentence(" ".join(bullets[:2]))
            if any(
                ideas_are_near_duplicates(summary, item["summary"])
                for item in themes
            ):
                continue
            themes.append(
                {
                    "heading": _safe_heading(source),
                    "summary": summary,
                    "source_indexes": [index],
                }
            )
        if not themes:
            raise InsufficientEvidenceError("not_enough_synthesis_evidence")
        used = sorted({index for theme in themes for index in theme["source_indexes"]})
        return {
            "kind": "multi_slide_synthesis",
            "topic": "Tổng hợp nội dung liên quan",
            "overview": _finish_sentence(
                "Các nguồn làm rõ những khía cạnh liên quan của chủ đề đang tìm"
            ),
            "themes": themes[:5],
            "connections": _finish_sentence(
                "Các ý trên được nhóm theo nội dung hỗ trợ và đã loại phần trùng lặp"
            ),
            "used_source_indexes": used,
        }

    if task == "self_check":
        questions = []
        for index, source in enumerate(sources[:3]):
            title = _safe_heading(source)
            if not title:
                continue
            questions.append(
                {
                    "question": f"Bạn có thể giải thích bằng lời của mình ý chính của “{title}” không?",
                    "source_indexes": [index],
                }
            )
        if not questions:
            raise InsufficientEvidenceError("not_enough_self_check_evidence")
        return {
            "kind": "self_check",
            "title": "Câu tự kiểm tra",
            "instructions": "Hãy tự trả lời trước; đáp án chưa được hiển thị.",
            "questions": questions[:3],
            "used_source_indexes": list(range(min(3, len(questions)))),
        }

    if task == "compare_sources":
        raise InsufficientEvidenceError("comparison_is_not_exposed")

    points: list[dict] = []
    for index, source in enumerate(sources[:3]):
        bullets = source_evidence_bullets(source, limit=1)
        if bullets:
            points.append(
                {
                    "text": _finish_sentence(bullets[0]),
                    "source_indexes": [index],
                }
            )
    if not points:
        raise InsufficientEvidenceError("not_enough_answer_evidence")
    return {
        "kind": "learning_answer",
        "title": _safe_heading(sources[0]),
        "answer": _finish_sentence(" ".join(point["text"] for point in points[:2])),
        "key_points": points,
        "used_source_indexes": sorted(
            {index for point in points for index in point["source_indexes"]}
        ),
    }


def _decorate_item_citations(value: object, sources: list[dict]) -> object:
    if isinstance(value, list):
        return [_decorate_item_citations(item, sources) for item in value]
    if not isinstance(value, dict):
        return value
    decorated = {
        key: _decorate_item_citations(item, sources)
        for key, item in value.items()
    }
    if "source_indexes" in value:
        indexes = _normalize_indexes(value.get("source_indexes"), len(sources))
        decorated["source_indexes"] = indexes
        decorated["citations"] = [public_result(sources[index]) for index in indexes]
    return decorated


def decorate_generation(generation: dict, sources: list[dict]) -> dict:
    return _decorate_item_citations(generation, sources)  # type: ignore[return-value]


def citations_for_generation(generation: dict, sources: list[dict]) -> list[dict]:
    indexes = _normalize_indexes(generation.get("used_source_indexes"), len(sources))
    return [public_result(sources[index]) for index in indexes]


def generation_to_text(generation: dict) -> str:
    """Compatibility/plain-history text; the frontend renders structured fields."""

    kind = generation.get("kind")
    if kind == "slide_summary":
        points = "\n".join(
            f"{index}. {item['text']}"
            for index, item in enumerate(generation.get("key_points", []), start=1)
        )
        return (
            f"{generation.get('title', '')}\n\n"
            f"{generation.get('main_idea', '')}\n\n"
            f"Điều cần nhớ\n{points}\n\n"
            f"{generation.get('takeaway', '')}"
        ).strip()
    if kind == "multi_slide_synthesis":
        themes = "\n".join(
            f"{index}. {item['heading']}: {item['summary']}"
            for index, item in enumerate(generation.get("themes", []), start=1)
        )
        return (
            f"{generation.get('topic', '')}\n\n"
            f"{generation.get('overview', '')}\n\n"
            f"{themes}\n\n{generation.get('connections', '')}"
        ).strip()
    if kind == "self_check":
        questions = "\n".join(
            f"{index}. {item['question']}"
            for index, item in enumerate(generation.get("questions", []), start=1)
        )
        return (
            f"{generation.get('title', '')} — chưa hiển thị đáp án\n\n"
            f"{generation.get('instructions', '')}\n\n{questions}"
        ).strip()
    if kind == "learning_answer":
        points = "\n".join(
            f"- {item['text']}" for item in generation.get("key_points", [])
        )
        return (
            f"{generation.get('title', '')}\n\n"
            f"{generation.get('answer', '')}\n\n{points}"
        ).strip()
    return ""


def generate_grounded_content(
    task: str,
    user_input: str,
    sources: list[dict],
) -> GenerationResult:
    if task not in TASK_SCHEMAS or task not in PROMPT_BUILDERS:
        raise InvalidModelOutputError("unsupported_generation_task")
    selected = sources[:1] if task == "summarize_first" else sources[:3]
    projections = [source_projection(source) for source in selected]
    schema = TASK_SCHEMAS[task]
    mode = configured_generation_mode()

    if mode in {"extractive", "degraded"}:
        fallback = _fallback_generation(task, selected)
        validated = _validate_semantics(task, fallback, schema, len(selected))
        return GenerationResult(
            generation=decorate_generation(validated, selected),
            mode="extractive",
            model="",
            cache_hit=False,
            call_count=0,
            degraded=mode == "degraded",
        )
    if mode == "unavailable":
        raise AIUnavailableError("openai_key_not_configured")

    messages = PROMPT_BUILDERS[task](user_input, projections)
    cache_key = _cache_key(task, messages, selected, projections)
    cached = get_cached_generation(cache_key)
    if cached is not None:
        try:
            validated = _validate_semantics(task, cached, schema, len(selected))
        except InvalidModelOutputError:
            cached = None
        else:
            return GenerationResult(
                generation=decorate_generation(validated, selected),
                mode="openai",
                model=MODEL,
                cache_hit=True,
                call_count=0,
                degraded=False,
            )

    calls = 0
    validation_error = ""
    try:
        calls += 1
        raw = _openai_request(messages, schema)
        validated = _validate_semantics(task, raw, schema, len(selected))
    except AIUnavailableError:
        raise
    except InvalidModelOutputError as exc:
        validation_error = str(exc)
        repair_messages = build_repair_prompt(
            task,
            user_input,
            projections,
            validation_error,
        )
        try:
            calls += 1
            raw = _openai_request(repair_messages, schema)
            validated = _validate_semantics(task, raw, schema, len(selected))
        except AIUnavailableError:
            raise
        except InvalidModelOutputError as repair_error:
            raise InvalidModelOutputError(
                f"repair_failed:{repair_error}"
            ) from repair_error

    put_cached_generation(cache_key, validated, model=MODEL, task=task)
    return GenerationResult(
        generation=decorate_generation(validated, selected),
        mode="openai",
        model=MODEL,
        cache_hit=False,
        call_count=calls,
        degraded=False,
    )


__all__ = [
    "AIUnavailableError",
    "GenerationResult",
    "InsufficientEvidenceError",
    "InvalidModelOutputError",
    "citations_for_generation",
    "configured_generation_mode",
    "generate_grounded_content",
    "generation_to_text",
    "source_projection",
]
