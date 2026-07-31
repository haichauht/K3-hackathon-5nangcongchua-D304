from __future__ import annotations

import os
from unittest.mock import patch

os.environ["OPENAI_API_KEY"] = ""

from backend.services import answer_service, generation_service  # noqa: E402


SOURCES = [
    {
        "source_type": "slide",
        "source_id": "d1-slide-hackathon.pdf#page=23",
        "file": "d1-slide-hackathon.pdf",
        "page": 23,
        "title": "Từ LLM đến AI Agent",
        "lesson": "AI & LLM Foundation",
        "context": (
            "LEVEL 0: LLM trần, chưa có công cụ. "
            "LEVEL 1: LLM kết nối search, database và API. "
            "LEVEL 2: hệ thống lập kế hoạch và tự kiểm tra. "
            "LEVEL 3: nhiều agent chuyên biệt phối hợp với nhau."
        ),
        "score": 90,
    },
    {
        "source_type": "slide",
        "source_id": "d1-slide-hackathon.pdf#page=24",
        "file": "d1-slide-hackathon.pdf",
        "page": 24,
        "title": "Giải phẫu một agent",
        "lesson": "AI & LLM Foundation",
        "context": (
            "Một agent vận hành theo vòng lặp gồm mục tiêu, suy luận, công cụ, "
            "hành động và bộ nhớ để tiếp tục điều chỉnh."
        ),
        "score": 84,
    },
    {
        "source_type": "slide",
        "source_id": "d2-slide-hackathon.pdf#page=18",
        "file": "d2-slide-hackathon.pdf",
        "page": 18,
        "title": "Rule và script",
        "lesson": "Xác định bài toán cho AI",
        "context": "Rule phù hợp với đầu vào ổn định và ít thay đổi.",
        "score": 60,
    },
]


SUMMARY_OUTPUT = {
    "kind": "slide_summary",
    "title": "Từ LLM đến AI Agent: bốn mức phát triển",
    "main_idea": (
        "AI Agent là LLM được bổ sung dần công cụ, khả năng lập kế hoạch "
        "và năng lực phối hợp."
    ),
    "key_points": [
        {"text": "Level 0 chỉ suy luận từ kiến thức sẵn có.", "source_indexes": [0]},
        {"text": "Level 1 kết nối với công cụ và dữ liệu mới.", "source_indexes": [0]},
        {"text": "Level 2 biết lập kế hoạch và tự kiểm tra.", "source_indexes": [0]},
        {"text": "Level 3 phối hợp nhiều agent chuyên biệt.", "source_indexes": [0]},
    ],
    "takeaway": "Mỗi cấp độ làm tăng khả năng hành động tự chủ của hệ thống.",
    "used_source_indexes": [0],
}


def _openai_mode():
    return (
        patch.object(generation_service.SETTINGS, "ai_generation_mode", "openai"),
        patch.object(generation_service, "OPENAI_API_KEY", "test-key"),
        patch.object(generation_service, "get_cached_generation", return_value=None),
        patch.object(generation_service, "put_cached_generation"),
    )


def test_single_slide_summary_uses_one_structured_call_and_real_citation() -> None:
    mode, key, cache_get, cache_put = _openai_mode()
    with mode, key, cache_get, cache_put, patch.object(
        generation_service,
        "_openai_request",
        return_value=SUMMARY_OUTPUT,
    ) as request:
        result = generation_service.generate_grounded_content(
            "summarize_first",
            "Tóm tắt slide này",
            SOURCES[:1],
        )

    assert request.call_count == 1
    assert result.call_count == 1
    assert result.generation["kind"] == "slide_summary"
    assert len(result.generation["key_points"]) == 4
    assert {
        point["text"].split()[0].lower()
        for point in result.generation["key_points"]
    } == {"level"}
    assert all(
        point["citations"][0]["source_id"] == SOURCES[0]["source_id"]
        for point in result.generation["key_points"]
    )


def test_multi_slide_synthesis_omits_unused_third_source() -> None:
    output = {
        "kind": "multi_slide_synthesis",
        "topic": "Cách một LLM trở thành AI Agent",
        "overview": "Hai nguồn mô tả quá trình phát triển và cơ chế vận hành của agent.",
        "themes": [
            {
                "heading": "Các cấp độ phát triển",
                "summary": "LLM tiến từ suy luận đơn thuần đến công cụ, kế hoạch và phối hợp.",
                "source_indexes": [0],
            },
            {
                "heading": "Vòng lặp vận hành",
                "summary": "Agent kết hợp mục tiêu, suy luận, công cụ, hành động và bộ nhớ.",
                "source_indexes": [1],
            },
        ],
        "connections": "Cấp độ cho biết agent mạnh đến đâu, còn vòng lặp giải thích cách nó hoạt động.",
        "used_source_indexes": [0, 1],
    }
    mode, key, cache_get, cache_put = _openai_mode()
    with mode, key, cache_get, cache_put, patch.object(
        generation_service,
        "_openai_request",
        return_value=output,
    ):
        result = generation_service.generate_grounded_content(
            "synthesize_sources",
            "Tổng hợp các nguồn",
            SOURCES,
        )

    citations = generation_service.citations_for_generation(result.generation, SOURCES)
    assert [item["source_id"] for item in citations] == [
        SOURCES[0]["source_id"],
        SOURCES[1]["source_id"],
    ]
    assert SOURCES[2]["source_id"] not in str(result.generation)


def test_complete_sentence_without_terminal_mark_is_normalized_not_repaired() -> None:
    output = {
        "kind": "multi_slide_synthesis",
        "topic": "AI Agent",
        "overview": "Hai nguồn mô tả năng lực và vòng lặp của một AI Agent",
        "themes": [
            {
                "heading": "Năng lực",
                "summary": "Agent bổ sung công cụ và khả năng lập kế hoạch cho LLM",
                "source_indexes": [0],
            },
            {
                "heading": "Vòng lặp",
                "summary": "Agent phối hợp mục tiêu, suy luận, công cụ, hành động và bộ nhớ",
                "source_indexes": [1],
            },
        ],
        "connections": "Các năng lực được vận hành trong một vòng lặp có kiểm tra kết quả",
        "used_source_indexes": [0, 1],
    }
    mode, key, cache_get, cache_put = _openai_mode()
    with mode, key, cache_get, cache_put, patch.object(
        generation_service,
        "_openai_request",
        return_value=output,
    ) as request:
        result = generation_service.generate_grounded_content(
            "synthesize_sources",
            "Tổng hợp các nguồn",
            SOURCES[:2],
        )

    assert request.call_count == 1
    assert result.call_count == 1
    assert result.generation["overview"].endswith(".")
    assert result.generation["connections"].endswith(".")
    assert all(theme["summary"].endswith(".") for theme in result.generation["themes"])


def test_invalid_semantics_get_exactly_one_repair_call() -> None:
    invalid = {
        **SUMMARY_OUTPUT,
        "key_points": [
            {"text": "Level 0 và Level 1 bị ghép", "source_indexes": [99]},
            {"text": "Một ý khác.", "source_indexes": [0]},
        ],
    }
    mode, key, cache_get, cache_put = _openai_mode()
    with mode, key, cache_get, cache_put, patch.object(
        generation_service,
        "_openai_request",
        side_effect=[invalid, SUMMARY_OUTPUT],
    ) as request:
        result = generation_service.generate_grounded_content(
            "summarize_first",
            "Tóm tắt",
            SOURCES[:1],
        )
    assert request.call_count == 2
    assert result.call_count == 2


def test_openai_error_returns_ai_unavailable_without_extractive_answer() -> None:
    mode, key, cache_get, cache_put = _openai_mode()
    with mode, key, cache_get, cache_put, patch.object(
        generation_service,
        "_openai_request",
        side_effect=generation_service.AIUnavailableError("timeout"),
    ):
        result = answer_service.build_grounded_answer(
            "Tóm tắt",
            "tom tat",
            SOURCES[:1],
            task="summarize_first",
        )
    assert result["status"] == "AI_UNAVAILABLE"
    assert result["answer"] == ""
    assert result["generation"] is None
    assert result["source"] == "ai_unavailable"


def test_strict_openai_mode_without_key_is_unavailable() -> None:
    with patch.object(generation_service.SETTINGS, "ai_generation_mode", "openai"), patch.object(
        generation_service,
        "OPENAI_API_KEY",
        "",
    ):
        result = answer_service.build_grounded_answer(
            "Giải thích",
            "agent",
            SOURCES[:1],
        )
    assert result["status"] == "AI_UNAVAILABLE"
    assert result["generation_meta"]["mode"] == "openai"


def test_source_projection_is_bounded_and_has_no_raw_citation() -> None:
    source = {
        **SOURCES[0],
        "context": (
            "Từ LLM đến AI Agent\n"
            + "Nội dung có căn cứ trong slide. " * 80
            + "[[fake.pdf#page=99]]"
        ),
    }
    projection = generation_service.source_projection(source)
    assert len(projection["content"]) <= 1200
    assert "[[" not in projection["content"]
