"""Recall use-case orchestration over guardrails, retrieval and grounded answers."""

from __future__ import annotations

import re

from ..config import LOCATE_RESULT_SCORE_GAP, MIN_FOUND_SCORE
from ..rag.retriever import search_hybrid_sources
from ..security.guardrails import (
    ADMIN_OUT_OF_SCOPE_RE,
    fallback_classify,
    expand_course_query,
    is_contextual_followup,
    is_course_topic,
    is_current_slide_request,
    is_locate_slide_request,
    is_likely_out_of_scope,
    make_simple_query,
)
from ..utils.text_utils import (
    remove_vietnamese_tone,
    safe_history_items,
    sanitize_content,
    tokenize,
)
from .answer_service import (
    build_grounded_answer,
    display_source_name,
    retrieval_confidence,
    slide_source_map,
)
from .source_service import (
    find_slide_page,
    public_result,
    resolve_runtime_source,
    source_matches_scope,
)

MAX_SUGGESTIONS = 3


def runtime_source_key(source: dict) -> tuple[str, str, object]:
    source_type = str(source.get("type") or source.get("source_type") or "slide")
    if source_type == "slide":
        return source_type, str(source.get("file", "")), source.get("page")
    return source_type, str(source.get("source_id") or source.get("source") or ""), None


def merge_slide_results(primary: dict, related: list[dict], limit: int = 3) -> list[dict]:
    primary = {
        **primary,
        "source_type": "slide",
        "source_id": primary.get("source_id") or f"{primary.get('file', '')}#page={primary.get('page', '')}",
        "score": max(int(primary.get("score", 0)), 80),
    }
    merged = [primary]
    seen = {runtime_source_key(primary)}
    for result in related:
        key = runtime_source_key(result)
        if key in seen:
            continue
        seen.add(key)
        merged.append(result)
        if len(merged) >= limit:
            break
    return merged


def combine_slide_searches(result_sets: list[list[dict]], limit: int = 3) -> list[dict]:
    by_source = {}
    for results in result_sets:
        for result in results:
            key = runtime_source_key(result)
            if key not in by_source or result.get("score", 0) > by_source[key].get("score", 0):
                by_source[key] = result
    ranked = sorted(
        by_source.values(),
        key=lambda item: (
            item.get("_rank_score", item.get("score", 0)),
            item.get("score", 0),
        ),
        reverse=True,
    )
    if ranked and str(ranked[0].get("source_type") or ranked[0].get("type")) == "transcript":
        best_slide_index = next(
            (
                index
                for index, item in enumerate(ranked)
                if str(item.get("source_type") or item.get("type")) == "slide"
            ),
            None,
        )
        if best_slide_index is not None:
            top_score = int(ranked[0].get("score", 0))
            slide_score = int(ranked[best_slide_index].get("score", 0))
            if top_score - slide_score <= 8:
                ranked.insert(0, ranked.pop(best_slide_index))
    return ranked[:limit]


def select_locate_slide_results(results: list[dict], limit: int = 3) -> list[dict]:
    """Keep only absolutely and relatively strong slide matches.

    A locate response must not pad its cards merely because retrieval always has
    a third-ranked item.
    """
    slides = [
        result
        for result in results
        if str(result.get("source_type") or result.get("type") or "slide") == "slide"
    ]
    if not slides:
        return []

    top_score = max(int(result.get("score", 0)) for result in slides)
    threshold = max(MIN_FOUND_SCORE, top_score - LOCATE_RESULT_SCORE_GAP)
    selected = []
    seen = set()
    for result in slides:
        if int(result.get("score", 0)) < threshold:
            continue
        key = runtime_source_key(result)
        if key in seen:
            continue
        seen.add(key)
        selected.append(result)
        if len(selected) >= limit:
            break
    return selected


def safe_history_sources(raw_sources: object) -> list[dict]:
    if not isinstance(raw_sources, list):
        return []

    sources = []
    for item in raw_sources[:5]:
        source = resolve_runtime_source(item)
        if source:
            try:
                relevance_score = int(
                    item.get("relevance_score", item.get("score", source.get("score", 0)))
                )
            except (TypeError, ValueError):
                relevance_score = int(source.get("score", 0))
            sources.append(
                {
                    **source,
                    "score": relevance_score,
                    "relevance_score": relevance_score,
                }
            )
    return sources


def safe_history(raw_history: object) -> list[dict]:
    return safe_history_items(raw_history)


def safe_selected_text(value: object) -> str:
    return sanitize_content(str(value or ""), max_chars=1200)


def contextual_query_terms(history: list[dict] | None, previous_sources: list[dict]) -> str:
    terms = []
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        terms.extend(tokenize(str(item.get("content", ""))))
        if len(terms) >= 8:
            break

    for source in previous_sources[:2]:
        terms.extend(tokenize(f"{source.get('title', '')} {source.get('lesson', '')}"))

    return " ".join(dict.fromkeys(terms))


def suggestion_card(
    suggestion_id: str,
    label: str,
    input_text: str,
    suggestion_type: str = "search",
    action: str = "",
) -> dict:
    card = {
        "id": suggestion_id,
        "label": label,
        "input": input_text,
        "type": suggestion_type,
    }
    if action:
        card["action"] = action
    return card


def topic_suggestions(user_input: str, current_slide: dict | None = None) -> list[dict]:
    normalized = remove_vietnamese_tone(user_input.lower())
    suggestions = []

    def add(suggestion_id: str, label: str, input_text: str) -> None:
        if any(item["id"] == suggestion_id for item in suggestions):
            return
        suggestions.append(suggestion_card(suggestion_id, label, input_text))

    if re.search(r"(agent|workflow|tu dong|autonom|llm)", normalized):
        add("agent", "Tìm về AI Agent", "Tìm phần nói về AI Agent")
        add("workflow", "Giải thích workflow", "Tìm phần giải thích về workflow")
        add("agent-levels", "Các mức độ tự chủ", "Tìm các mức độ từ LLM đến agent")
    elif re.search(r"(rag|citation|grounding|hallucination|context)", normalized):
        add("rag", "Tìm về RAG", "Tìm phần RAG và citation")
        add("hallucination", "Giảm hallucination", "Tìm phần hallucination và kiểm chứng")
        add("context", "Quản lý context", "Tìm phần context và attention")
    elif re.search(r"(baseline|measurement|impact|effort|quick win)", normalized) or re.search(r"\b(?:roi|return on investment)\b", user_input, re.IGNORECASE):
        add("baseline", "Baseline & measurement", "Tìm phần baseline và measurement")
        add("use-case", "Đánh giá AI use case", "Tìm cách đánh giá AI use case")
        add("problem-scope", "Problem & scope", "Tìm cách xác định problem và scope")
    elif re.search(r"(mvp|poc|prototype|scope|problem)", normalized):
        add("problem-scope", "Problem & scope", "Tìm cách xác định problem và scope")
        add("prototype", "Prototype và evaluation", "Tìm phần prototype và evaluation")
        add("go-no-go", "Go hay Not yet", "Tìm cây quyết định Go và Not yet")
    else:
        add("agent", "AI Agent", "Tìm phần nói về AI Agent")
        add("workflow", "Workflow", "Tìm phần giải thích về workflow")
        add("rag", "RAG & citation", "Tìm phần RAG và citation")

    if current_slide:
        suggestions = [
            suggestion_card(
                "current-slide",
                "Tóm tắt slide hiện tại",
                "Tóm tắt slide hiện tại",
            ),
            *[item for item in suggestions if item["id"] != "current-slide"],
        ]

    return suggestions[:MAX_SUGGESTIONS]


def found_suggestions(sources: list[dict] | None = None) -> list[dict]:
    del sources
    return [
        suggestion_card(
            "summarize-source",
            "Tóm tắt nguồn đầu tiên",
            "Tóm tắt nguồn này",
            "source_action",
            "summarize",
        ),
        suggestion_card(
            "synthesize-sources",
            "Tổng hợp các nguồn liên quan",
            "Tổng hợp nội dung liên quan",
            "source_action",
            "synthesize",
        ),
        suggestion_card(
            "self-check",
            "Tạo câu tự kiểm tra",
            "Tạo câu tự kiểm tra",
            "source_action",
            "self_check",
        ),
    ]


def suggestion_labels(suggestions: list[dict]) -> list[str]:
    return [str(item.get("label", "")) for item in suggestions if item.get("label")]


def build_suggestions(
    status: str,
    user_input: str = "",
    current_slide: dict | None = None,
    sources: list[dict] | None = None,
) -> list[dict]:
    if status == "FOUND":
        return found_suggestions(sources)
    if status in {"CLARIFY", "NOT_FOUND"}:
        return topic_suggestions(user_input, current_slide=current_slide)
    return []


def followup_kind(user_input: str) -> str | None:
    normalized = remove_vietnamese_tone(user_input.strip().lower())
    if re.search(
        r"(tu kiem tra|self check|self-check|quiz question|cau hoi kiem tra|kiem tra da hieu)",
        normalized,
    ):
        return "self_check"
    if re.search(r"\b(?:summarize|explain|clarify)\s+(?:this|the)\s+(?:slide|page|section|source)\b", normalized):
        return "summarize_first"
    if re.search(r"(tong hop noi dung|tong hop|noi dung lien quan|van de nay|cac nguon|nhieu nguon|lien quan)", normalized):
        return "synthesize_sources"
    if re.search(r"(tom tat nguon nay|tom tat nguon|tom tat|noi ngan gon|source dau tien|nguon dau tien|ket qua dau tien|slide dau tien)", normalized):
        return "summarize_first"
    if re.search(r"(mo trang slide|mo trang nguon|truy dan|dan toi|mo nguon|mo slide|xem nguon|den trang|nhay den)", normalized):
        return "open_source"
    if re.search(r"(giai thich|noi ro|de hieu hon|cai do|phan do|nguon do|trang do|ket qua do)", normalized):
        return "summarize_first"
    return None


def contextual_followup_response(
    user_input: str,
    previous_sources: list[dict],
    action: str = "",
) -> dict | None:
    action_map = {
        "summarize": "summarize_first",
        "synthesize": "synthesize_sources",
        "self_check": "self_check",
        "open": "open_source",
    }
    kind = action_map.get(action) or followup_kind(user_input)
    if not kind or not previous_sources:
        return None

    if kind == "open_source":
        target = previous_sources[0]
        return {
            "status": "FOUND",
            "intent": {"label": "FOUND_CANDIDATE", "source": "history_followup", "query": ""},
            "query": "",
            "answer": f"Mình đã mở trang nguồn phù hợp nhất: {display_source_name(target)}.",
            "confidence": "high",
            "follow_up_options": suggestion_labels(found_suggestions(previous_sources)),
            "suggestions": found_suggestions(previous_sources),
            "source_map": slide_source_map([target], []),
            "citations": slide_source_map([target], []),
            "answer_source": "history",
            "results": [public_result(target)],
            "message": "Đã chọn nguồn từ kết quả trước.",
        }

    selected = previous_sources[:1] if kind == "summarize_first" else previous_sources[:3]
    answer = build_grounded_answer(
        user_input,
        " ".join(tokenize(user_input)),
        selected,
        task=kind,
    )
    return {
        "status": "FOUND",
        "intent": {"label": "FOUND_CANDIDATE", "source": "history_followup", "query": ""},
        "query": "",
        "answer": answer["answer"],
        "confidence": answer["confidence"],
        "follow_up_options": suggestion_labels(found_suggestions(previous_sources)),
        "suggestions": found_suggestions(previous_sources),
        "source_map": answer["source_map"],
        "citations": answer["source_map"],
        "answer_source": answer["source"],
        "results": [public_result(result) for result in selected],
        "message": "Trả lời dựa trên kết quả trước trong đoạn chat.",
    }


def search_recall(
    user_input: str,
    selected_pdf: str = "",
    selected_page: int | None = None,
    previous_sources: list[dict] | None = None,
    history: list[dict] | None = None,
    selected_text: str = "",
    action: str = "",
    selected_scope: str = "all",
    current_slide_source_id: str = "",
) -> dict:
    current_slide = resolve_runtime_source(
        {"type": "slide", "source_id": current_slide_source_id}
    ) if current_slide_source_id else find_slide_page(selected_pdf, selected_page)
    selected_scope = selected_scope if selected_scope in {"all", "day01", "day02", "current"} else "all"
    history_sources = previous_sources or []
    history_response = contextual_followup_response(user_input, history_sources, action=action)
    if history_response:
        return history_response

    # Routing is deterministic and local. The only OpenAI call in the normal
    # search flow is the grounded answer generation after retrieval.
    intent = fallback_classify(user_input)
    locate_request = is_locate_slide_request(user_input)
    if intent.get("source") == "fallback":
        intent["source"] = "local_router"
    if selected_text and intent["label"] == "CLARIFY":
        selected_query = make_simple_query(selected_text) or " ".join(tokenize(selected_text))
        if selected_query:
            intent = {
                **intent,
                "label": "FOUND_CANDIDATE",
                "query": selected_query,
                "source": f"{intent.get('source', 'unknown')}+selected_text_context",
            }
    if intent["label"] != "RESTRICTED" and ADMIN_OUT_OF_SCOPE_RE.search(user_input):
        intent = {
            **intent,
            "label": "OUT_OF_SCOPE",
            "query": "",
        }

    if intent["label"] != "RESTRICTED" and is_likely_out_of_scope(user_input):
        intent = {
            **intent,
            "label": "OUT_OF_SCOPE",
            "query": "",
        }

    if (
        intent["label"] in {"CLARIFY", "OUT_OF_SCOPE"}
        and intent.get("source") != "local_guardrail"
        and is_course_topic(user_input)
    ):
        intent = {
            **intent,
            "label": "FOUND_CANDIDATE",
            "query": intent.get("query") or make_simple_query(user_input),
            "source": f"{intent.get('source', 'unknown')}+course_topic_override",
        }

    if current_slide and is_current_slide_request(user_input) and intent["label"] == "CLARIFY":
        intent = {
            **intent,
            "label": "FOUND_CANDIDATE",
            "query": " ".join(tokenize(f"{current_slide.get('title', '')} {current_slide.get('lesson', '')}"))[:160],
            "source": f"{intent.get('source', 'unknown')}+current_slide_context",
        }

    if locate_request and intent["label"] == "FOUND_CANDIDATE":
        intent["type"] = "LOCATE_SLIDE"
    elif current_slide and is_current_slide_request(user_input):
        intent["type"] = "CURRENT_SLIDE"
    else:
        intent["type"] = intent.get("type") or "KNOWLEDGE_ANSWER"

    if intent["label"] == "RESTRICTED":
        return {
            "status": "NOT_FOUND",
            "intent": intent,
            "results": [],
            "suggestions": [],
            "citations": [],
            "message": "Mình không xuất raw data, thông tin định danh hoặc nội dung bị hạn chế.",
        }

    if intent["label"] == "OUT_OF_SCOPE":
        return {
            "status": "NOT_FOUND",
            "intent": intent,
            "results": [],
            "suggestions": [],
            "citations": [],
            "message": "Câu hỏi này ngoài phạm vi nguồn học tập VLearn hiện có.",
        }

    if intent["label"] == "CLARIFY":
        suggestions = build_suggestions("CLARIFY", user_input, current_slide=current_slide)
        return {
            "status": "CLARIFY",
            "intent": intent,
            "results": [],
            "suggestions": suggestions,
            "citations": [],
            "follow_up_options": suggestion_labels(suggestions),
            "message": intent.get("clarifying_question")
            or "Bạn muốn tìm phần liên quan đến use case, workflow hay RAG/citation?",
        }

    query = intent.get("query") or make_simple_query(user_input)
    selected_query = make_simple_query(selected_text) if selected_text else ""
    history_query = contextual_query_terms(history, history_sources) if is_contextual_followup(user_input) else ""
    search_query = expand_course_query(
        user_input,
        " ".join(filter(None, [query, selected_query, history_query])),
    )
    direct_query = make_simple_query(user_input)
    absolute_query = direct_query or query or user_input
    primary_results = search_hybrid_sources(
        search_query,
        limit=6,
        topic_hint=user_input,
        absolute_query=absolute_query,
        source_types={"slide"} if locate_request else None,
    )
    result_sets = [primary_results]
    primary_is_strong = bool(
        primary_results
        and int(primary_results[0].get("score", 0)) >= MIN_FOUND_SCORE
    )
    if direct_query and direct_query != search_query and not primary_is_strong:
        result_sets.append(
            search_hybrid_sources(
                direct_query,
                limit=6,
                topic_hint=user_input,
                absolute_query=direct_query,
                source_types={"slide"} if locate_request else None,
            )
        )
    source_results = combine_slide_searches(
        result_sets,
        limit=18 if selected_scope in {"day01", "day02"} else 5,
    )
    if selected_scope in {"day01", "day02"}:
        source_results = [
            result for result in source_results
            if source_matches_scope(result, selected_scope)
        ][:5]
    if selected_scope == "current" and current_slide:
        source_results = merge_slide_results(current_slide, [], limit=1)
    if current_slide and is_current_slide_request(user_input):
        source_results = merge_slide_results(current_slide, source_results, limit=5)
    elif locate_request:
        source_results = select_locate_slide_results(source_results)

    if not source_results or (
        not (
            current_slide
            and (
                is_current_slide_request(user_input)
                or selected_scope == "current"
            )
        )
        and int(source_results[0].get("score", 0)) < MIN_FOUND_SCORE
    ):
        suggestions = build_suggestions("NOT_FOUND", user_input, current_slide=current_slide)
        return {
            "status": "NOT_FOUND",
            "intent": intent,
            "query": query,
            "results": [],
            "suggestions": suggestions,
            "citations": [],
            "follow_up_options": suggestion_labels(suggestions),
            "message": "Mình chưa tìm thấy nguồn slide hoặc transcript đủ chắc để trả lời. Hãy thêm một vài từ khóa trong nội dung bạn nhớ.",
        }

    public_sources = source_results[:3]
    if locate_request:
        count = len(public_sources)
        noun = "slide" if count == 1 else "slide"
        lead = f"Mình tìm thấy {count} {noun} phù hợp nhất với nội dung bạn đang tìm."
        return {
            "status": "FOUND",
            "intent": intent,
            "query": query,
            "answer": lead,
            "confidence": retrieval_confidence(public_sources),
            "follow_up_options": suggestion_labels(found_suggestions(public_sources)),
            "suggestions": found_suggestions(public_sources),
            "source_map": [],
            "citations": [],
            "answer_source": "retrieval",
            "results": [public_result(result) for result in public_sources],
            "message": lead,
        }

    answer = build_grounded_answer(
        user_input,
        search_query,
        source_results,
        history=history,
        selected_text=selected_text,
    )
    return {
        "status": "FOUND",
        "intent": intent,
        "query": query,
        "answer": answer["answer"],
        "confidence": answer["confidence"],
        "follow_up_options": suggestion_labels(found_suggestions(public_sources)),
        "suggestions": found_suggestions(public_sources),
        "source_map": answer["source_map"],
        "citations": answer["source_map"],
        "answer_source": answer["source"],
        "results": [public_result(result) for result in public_sources],
        "message": f"Tìm thấy {len(public_sources)} nguồn phù hợp.",
    }
