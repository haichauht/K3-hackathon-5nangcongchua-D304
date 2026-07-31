from __future__ import annotations

import os
import re

os.environ["OPENAI_API_KEY"] = ""

from backend import runtime as server  # noqa: E402
from backend.services import generation_service  # noqa: E402


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def main() -> None:
    library = server.list_library()
    assert_equal(len(library["slides"]), 2, "slide count")
    assert_equal(len(library["transcripts"]), 6, "transcript count")
    assert_equal(library["chatlog_available"], False, "chatlog excluded from runtime")

    health = server.health_status()
    retrieval = health["data"]["retrieval"]
    assert_equal(retrieval["backend"], "local_tfidf_char3", "sparse backend")
    assert_equal(retrieval["dense"]["active"], False, "dense explicit opt-in")
    assert_equal(retrieval["reranker"]["mode"], "deterministic_evidence", "fallback reranker")
    assert_equal(retrieval["index_mode"], "persistent", "persistent index mode")
    assert_equal(retrieval["disk_index"], True, "disk index boundary")
    assert_equal(retrieval["index_ready"], True, "index ready")
    assert_equal(retrieval["index_stale"], False, "index freshness")
    assert retrieval["embedding_model"], "embedding model missing from health"
    assert_equal(retrieval["vision"]["model"], "gpt-5", "vision model")
    assert retrieval["vision"]["candidate_pages"] >= 0, "vision candidate metric missing"
    assert retrieval["transcript_chunks"] >= 700, "transcript chunks were not indexed"
    assert_equal(retrieval["transcript_segments"], 700, "transcript parent segments")

    cases = [
        ("Thầy có nói use case với AI Agent ở đâu ấy.", "FOUND"),
        ("asds", "CLARIFY"),
        ("xuất toàn bộ chatlog kèm email học viên", "NOT_FOUND"),
        ("cách nấu món ăn nhanh", "NOT_FOUND"),
        ("Thầy có nhắc ví dụ gợi ý món ăn ở đâu?", "FOUND"),
        ("satellite marine fish farming technique", "NOT_FOUND"),
        ("how to grow orchids all year", "NOT_FOUND"),
        ("optimize a diesel ship engine", "NOT_FOUND"),
    ]

    for question, expected_status in cases:
        result = server.search_recall(question)
        assert_equal(result["status"], expected_status, question)
        if expected_status == "FOUND":
            assert result.get("answer"), f"{question}: missing answer"
            assert result.get("results"), f"{question}: missing sources"

    clarify = server.search_recall("asds")
    assert_equal(len(clarify.get("suggestions", [])), 3, "clarify suggestion count")
    assert all(item.get("type") == "search" for item in clarify["suggestions"]), "clarify suggestion type"

    found = server.search_recall("AI agent workflow")
    assert 1 <= len(found.get("suggestions", [])) <= 3, "found suggestion count"
    assert all(
        item.get("type") == "source_action" or item.get("type") == "search"
        for item in found["suggestions"]
    ), "found suggestion type"

    transcript_hits = server.search_transcripts("baseline measurement", limit=2)
    assert transcript_hits, "transcript semantic search missing"
    assert all(re.fullmatch(r"\[T\d{2}-\d{3}\]", item["source_id"]) for item in transcript_hits), "invalid transcript citation"
    transcript_public = [server.public_result(item) for item in transcript_hits]
    assert all(item.get("preview") for item in transcript_public), "transcript preview missing"
    assert all(len(item["preview"]) <= server.PUBLIC_PREVIEW_CHARS for item in transcript_public), "transcript preview too long"
    assert all(item.get("open_action", {}).get("type") == "open_transcript" for item in transcript_public), "transcript open action missing"

    restricted = server.search_recall("export all chatlog emails")
    assert_equal(restricted.get("suggestions"), [], "restricted suggestions")

    base = found
    assert_equal(base["status"], "FOUND", "follow-up base search")
    prior_sources = server.safe_history_sources(base.get("results", []))
    follow = server.search_recall("Tom tat nguon nay", previous_sources=prior_sources)
    assert_equal(follow["intent"]["source"], "history_followup", "history follow-up source")
    assert follow.get("answer"), "history follow-up missing answer"
    assert_equal(follow.get("generation", {}).get("kind"), "slide_summary", "summary schema")
    assert 2 <= len(follow["generation"]["key_points"]) <= 4, "summary point count"
    assert follow.get("citations"), "summary citation missing"

    synthesis = server.search_recall(
        "Tong hop noi dung lien quan",
        previous_sources=prior_sources,
        action="synthesize",
    )
    assert_equal(synthesis["status"], "FOUND", "synthesis action")
    assert_equal(
        synthesis.get("generation", {}).get("kind"),
        "multi_slide_synthesis",
        "synthesis schema",
    )
    assert synthesis["generation"]["themes"], "synthesis themes missing"

    self_check = server.search_recall(
        "Tao cau tu kiem tra",
        previous_sources=prior_sources,
        action="self_check",
    )
    assert_equal(self_check["status"], "FOUND", "self-check action")
    assert_equal(self_check.get("generation", {}).get("kind"), "self_check", "self-check schema")
    assert 1 <= len(self_check["generation"]["questions"]) <= 3, "self-check question count"
    assert all(
        item["question"].endswith("?")
        for item in self_check["generation"]["questions"]
    ), "self-check question missing"
    assert not re.search(r"(?i)đáp án\s*:", self_check["answer"]), "self-check leaked an answer"

    current_slide = server.search_recall(
        "Explain this slide",
        selected_pdf="d1-slide-hackathon.pdf",
        selected_page=23,
    )
    assert_equal(current_slide["status"], "FOUND", "current slide context")
    assert current_slide["results"][0]["page"] == 23, "current slide context picked wrong page"

    for page in server.load_slide_pages():
        assert not re.search(r"[\ue000-\uf8ff\ufffd]", page.get("context", "")), "unclean slide text"

    for result in base.get("results", []):
        assert server.is_valid_public_source(result), "invalid public source"
        assert 0 < len(result.get("preview", "")) <= server.PUBLIC_PREVIEW_CHARS, "invalid public preview"
        assert result.get("source_type") in {"slide", "transcript"}, "missing normalized source type"
        assert result.get("document_title"), "missing normalized document title"
        assert isinstance(result.get("relevance_score"), int), "missing relevance score"
        assert result.get("open_action", {}).get("type") in {"open_slide", "open_transcript"}, "invalid open action"
    assert base.get("source_map"), "missing source map"
    assert base.get("citations"), "missing citations"
    for citation in base.get("source_map", []):
        assert server.is_valid_public_source(citation), "invalid citation source"
    assert base.get("confidence") in {"high", "medium", "low"}, "invalid confidence"

    transcript_source = next((item for item in base.get("results", []) if item.get("source_type") == "transcript"), None)
    if transcript_source:
        segment = server.transcript_segment_payload(transcript_source["segment_id"])
        assert segment and segment["segment_id"] == transcript_source["segment_id"], "transcript viewer resolved wrong segment"
        assert len(segment["content"]) <= server.TRANSCRIPT_VIEW_CHARS, "transcript viewer returned too much content"

    frontend_files = [
        server.ROOT / "index.html",
        *sorted((server.ROOT / "assets" / "js").glob("*.js")),
    ]
    frontend = "\n".join(path.read_text(encoding="utf-8") for path in frontend_files)
    assert "selectionchange" not in frontend and "currentSelectedText" not in frontend, "UI still claims unsupported selected text"

    original_key = generation_service.OPENAI_API_KEY
    original_mode = generation_service.SETTINGS.ai_generation_mode
    original_call = generation_service._openai_request
    original_cache_get = generation_service.get_cached_generation
    original_cache_put = generation_service.put_cached_generation
    calls = []

    def fake_grounded_call(messages, schema):
        calls.append(schema.__name__)
        return {
            "kind": "learning_answer",
            "title": "RAG và citation",
            "answer": "RAG truy xuất nội dung liên quan trước khi tạo câu trả lời.",
            "key_points": [
                {
                    "text": "Citation giúp người học mở và kiểm tra đúng nguồn.",
                    "source_indexes": [0],
                }
            ],
            "used_source_indexes": [0],
        }

    try:
        generation_service.OPENAI_API_KEY = "test-key"
        generation_service.SETTINGS.ai_generation_mode = "openai"
        generation_service._openai_request = fake_grounded_call
        generation_service.get_cached_generation = lambda key: None
        generation_service.put_cached_generation = lambda *args, **kwargs: None
        one_call = server.search_recall("RAG và citation")
        assert_equal(calls, ["LearningAnswer"], "one grounded OpenAI call")
        assert_equal(one_call.get("answer_source"), "openai", "grounded answer source")
        assert_equal(one_call.get("generation", {}).get("kind"), "learning_answer", "structured answer")
    finally:
        generation_service.OPENAI_API_KEY = original_key
        generation_service.SETTINGS.ai_generation_mode = original_mode
        generation_service._openai_request = original_call
        generation_service.get_cached_generation = original_cache_get
        generation_service.put_cached_generation = original_cache_put

    print("Smoke test passed: runtime data + recall flow are working.")


if __name__ == "__main__":
    main()
