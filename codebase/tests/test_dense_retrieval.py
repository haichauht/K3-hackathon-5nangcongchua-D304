from __future__ import annotations

import os

os.environ["OPENAI_API_KEY"] = ""

from backend.rag.dense_retriever import (  # noqa: E402
    DENSE_CLIENT,
    embedding_document_text,
)
from backend.rag import retriever as retriever_module  # noqa: E402
from backend.rag.reranker import rerank_candidates  # noqa: E402
from backend.rag.retriever import LocalTfidfIndex, prepare_runtime_documents  # noqa: E402


def documents() -> list[dict]:
    return prepare_runtime_documents(
        [
            {
                "type": "slide",
                "source_type": "slide",
                "source_id": "deck.pdf#page=1",
                "file": "deck.pdf",
                "page": 1,
                "title": "Problem statement",
                "lesson": "Course",
                "text": "Define the right problem before choosing a solution.",
                "context": "Define the right problem before choosing a solution.",
            },
            {
                "type": "transcript",
                "source_type": "transcript",
                "source_id": "[T01-001]",
                "parent_segment_id": "[T01-001]",
                "title": "Lecture",
                "lesson": "Course",
                "text": "Use evidence and citation.",
                "context": "Use evidence and citation.",
            },
        ]
    )


def test_sparse_index_serialization_is_honest_when_dense_is_not_built() -> None:
    source_documents = documents()
    index = LocalTfidfIndex(source_documents, build_dense=False)
    payload = index.to_serialized()
    loaded = LocalTfidfIndex.from_serialized(source_documents, payload)

    assert payload["format_version"] == 2
    assert payload["dense_vectors"] == []
    assert loaded.dense_ready is False
    assert max(loaded.search_sparse("problem statement")) > 0


def test_server_startup_does_not_trigger_bulk_dense_rebuild(monkeypatch) -> None:
    source_documents = documents()
    sparse_index = LocalTfidfIndex(source_documents, build_dense=False)
    calls = {"count": 0}

    class FakeManager:
        def load_or_build(self, **kwargs):
            del kwargs
            calls["count"] += 1
            return sparse_index, {"index_mode": "persistent", "index_ready": True}

    monkeypatch.setattr(retriever_module, "RUNTIME_DOCUMENT_CACHE", source_documents)
    monkeypatch.setattr(retriever_module, "SEMANTIC_INDEX_CACHE", None)
    monkeypatch.setattr(retriever_module, "RUNTIME_INDEX_STATUS", {})
    monkeypatch.setattr(retriever_module, "get_rag_index_manager", lambda: FakeManager())
    monkeypatch.setattr(retriever_module.DENSE_CLIENT, "enabled", True)
    monkeypatch.setattr(retriever_module.vision_processor, "VISION_CACHE_CHANGED", False)

    _, index = retriever_module.ensure_runtime_index()

    assert calls["count"] == 1
    assert index.dense_ready is False
    assert retriever_module.RUNTIME_INDEX_STATUS["dense"]["active"] is False


def test_persisted_dense_vectors_can_rerank_without_persisting_source_text(monkeypatch) -> None:
    source_documents = documents()
    index = LocalTfidfIndex(source_documents, build_dense=False)
    dimensions = DENSE_CLIENT.dimensions
    first = [1.0] + [0.0] * (dimensions - 1)
    second = [0.0, 1.0] + [0.0] * (dimensions - 2)
    payload = {
        **index.to_serialized(),
        "dense_model": DENSE_CLIENT.model,
        "dense_dimensions": dimensions,
        "dense_vectors": [first, second],
    }
    loaded = LocalTfidfIndex.from_serialized(source_documents, payload)
    monkeypatch.setattr(DENSE_CLIENT, "enabled", True)
    monkeypatch.setattr(DENSE_CLIENT, "embed_query", lambda query: first)

    assert loaded.dense_ready is True
    assert loaded.search_dense("a distant paraphrase")[0] > 0.99
    assert "file_path" not in payload
    assert "context" not in payload
    assert "text" not in payload


def test_reranker_collapses_transcript_children_and_prefers_equivalent_slide() -> None:
    candidates = [
        {
            "type": "transcript",
            "source_type": "transcript",
            "source_id": "[T01-001]",
            "parent_segment_id": "[T01-001]",
            "chunk_id": "[T01-001]#chunk=1",
            "relevance_score": 84,
            "token_coverage": 1.0,
        },
        {
            "type": "transcript",
            "source_type": "transcript",
            "source_id": "[T01-001]",
            "parent_segment_id": "[T01-001]",
            "chunk_id": "[T01-001]#chunk=2",
            "relevance_score": 80,
            "token_coverage": 0.8,
        },
        {
            "type": "slide",
            "source_type": "slide",
            "file": "deck.pdf",
            "page": 2,
            "relevance_score": 78,
            "token_coverage": 0.5,
        },
    ]

    ranked = rerank_candidates(candidates, dense_active=False, limit=3)
    assert len(ranked) == 2
    assert ranked[0]["source_type"] == "slide"


def test_embedding_projection_is_bounded_and_excludes_paths() -> None:
    projection = embedding_document_text(
        {
            "type": "slide",
            "source_type": "slide",
            "file": "deck.pdf",
            "page": 1,
            "title": "Topic",
            "lesson": "Lesson",
            "context": "evidence " * 1000,
            "file_path": r"C:\private\raw-transcript.md",
        }
    )
    assert len(projection) <= 1200
    assert "private" not in projection
    assert "raw-transcript" not in projection


def test_embedding_projection_rejects_chatlog_and_parent_transcript() -> None:
    import pytest

    with pytest.raises(ValueError, match="unsupported_embedding_source_type"):
        embedding_document_text(
            {
                "type": "chatlog",
                "source_type": "chatlog",
                "context": "conversation history",
            }
        )
    with pytest.raises(ValueError, match="transcript_embedding_requires_subchunk"):
        embedding_document_text(
            {
                "type": "transcript",
                "source_type": "transcript",
                "source_id": "[T01-001]",
                "context": "whole parent segment",
            }
        )


def test_embedding_projection_redacts_common_pii() -> None:
    projection = embedding_document_text(
        {
            "type": "transcript",
            "source_type": "transcript",
            "source_id": "[T01-001]",
            "parent_segment_id": "[T01-001]",
            "chunk_id": "[T01-001]#chunk=1",
            "context": (
                "Liên hệ student@example.com, +84 912 345 678 hoặc "
                "https://example.com/profile?id=123."
            ),
        }
    )

    assert "student@example.com" not in projection
    assert "912 345 678" not in projection
    assert "example.com/profile" not in projection
    assert projection.count("REDACTED") == 3


def test_embedding_projection_deduplicates_repeated_lesson_metadata() -> None:
    projection = embedding_document_text(
        {
            "type": "transcript",
            "source_type": "transcript",
            "source_id": "[T01-001]",
            "parent_segment_id": "[T01-001]",
            "chunk_id": "[T01-001]#chunk=1",
            "title": "Foundation lesson",
            "document_title": "Foundation lesson",
            "lesson": "Foundation lesson",
            "context": "Agent uses tools across a workflow.",
        }
    )

    assert projection.count("Foundation lesson") == 1
    assert "Content: Agent uses tools across a workflow." in projection
