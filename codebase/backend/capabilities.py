"""Runtime capability and health reporting."""

from __future__ import annotations

from .config import SETTINGS
from .rag import document_loader, retriever, vision_processor
from .services.answer_service import is_openai_ready


def health_status() -> dict:
    library = document_loader.list_library()
    documents, _ = retriever.ensure_runtime_index()
    retrieval_status = dict(retriever.RUNTIME_INDEX_STATUS)
    retrieval_status.update(
        {
            "backend": (
                "hybrid_sparse_dense"
                if retrieval_status.get("dense", {}).get("active")
                else "local_tfidf_char3"
            ),
            "documents": len(documents),
            "slide_pages": sum(1 for item in documents if item.get("source_type") == "slide"),
            "transcript_chunks": sum(1 for item in documents if item.get("source_type") == "transcript"),
            "transcript_segments": len(document_loader.load_transcript_segments()),
            "disk_index": SETTINGS.rag_index_mode == "persistent",
            "vision": {
                "enabled": vision_processor.RAG_VISION_ENABLED,
                "model": vision_processor.RAG_VISION_MODEL,
                **vision_processor.VISION_STATS,
            },
        }
    )
    return {
        "status": "ok",
        "ai_ready": is_openai_ready(),
        "ai_mode": "openai" if is_openai_ready() else "fallback",
        "model": SETTINGS.openai_model if is_openai_ready() else "",
        "data": {
            "slides": len(library["slides"]),
            "transcripts": len(library["transcripts"]),
            "chatlog_available": False,
            "retrieval": retrieval_status,
        },
    }
