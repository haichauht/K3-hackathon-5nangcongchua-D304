"""Compatibility facade for tests, eval and CLI; contains no business logic."""

from .capabilities import health_status
from .config import MIN_FOUND_SCORE, PUBLIC_PREVIEW_CHARS, SETTINGS, TRANSCRIPT_VIEW_CHARS
from .rag.document_loader import list_library, load_slide_pages
from .rag.retriever import (
    GENERIC_RETRIEVAL_TERMS,
    document_search_text,
    ensure_runtime_index,
    rag_index_build,
    rag_index_status,
    search_hybrid_sources,
)
from .security.guardrails import exact_source_anchor_terms
from .services.answer_service import (
    citation_marker,
    normalize_task_answer,
    retrieval_confidence,
)
from .services.recall_service import safe_history_sources, search_recall
from .services.source_service import (
    find_slide_page,
    is_valid_public_source,
    public_result,
    resolve_runtime_source,
    search_transcripts,
    source_matches_scope,
    transcript_segment_payload,
)
from .utils.text_utils import tokenize

ROOT = SETTINGS.codebase_root
