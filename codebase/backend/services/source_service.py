"""Resolve, validate and expose safe public learning sources."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from ..config import PUBLIC_PREVIEW_CHARS, SETTINGS, TRANSCRIPT_VIEW_CHARS
from ..rag import document_loader, retriever
from ..rag.document_loader import day_from_slide, day_from_transcript
from ..utils.text_utils import clean_extracted_text, safe_preview, sanitize_content

ROOT = SETTINGS.codebase_root
SLIDES_ROOT = SETTINGS.slides_root
ensure_runtime_index = retriever.ensure_runtime_index
load_slide_pages = document_loader.load_slide_pages
load_transcript_chunks = document_loader.load_transcript_chunks
load_transcript_segments = document_loader.load_transcript_segments
search_hybrid_sources = retriever.search_hybrid_sources


def resolve_slide_file(filename: str) -> Path | None:
    file_path = (SLIDES_ROOT / filename).resolve()
    try:
        file_path.relative_to(SLIDES_ROOT.resolve())
    except ValueError:
        return None

    if file_path.suffix.lower() != ".pdf" or not file_path.is_file():
        return None
    return file_path


def render_slide_page(filename: str, page_number: int, zoom: float = 1.6) -> bytes:
    file_path = resolve_slide_file(filename)
    if file_path is None:
        raise FileNotFoundError(filename)

    try:
        import fitz
    except ImportError as error:
        raise RuntimeError("PyMuPDF is not installed. Run: pip install -r requirements.txt") from error

    document = fitz.open(str(file_path))
    try:
        if page_number < 1 or page_number > document.page_count:
            raise IndexError(page_number)

        page = document.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def find_slide_page(filename: str, page: int | None) -> dict | None:
    if not filename or not page:
        return None

    # Ensure any visual analysis has already happened during the one-time
    # index lifecycle, never as an ad-hoc request-time Vision call.
    ensure_runtime_index()
    safe_name = Path(filename).name
    if resolve_slide_file(safe_name) is None:
        return None

    for slide_page in load_slide_pages():
        if slide_page.get("file") == safe_name and slide_page.get("page") == page:
            return slide_page
    return None


def find_transcript_chunk(source_id: str) -> dict | None:
    if not re.fullmatch(r"\[T\d{2}-\d{3}\]", str(source_id or "")):
        return None
    for document in load_transcript_segments():
        if document.get("source_id") == source_id:
            return document
    return None


def resolve_runtime_source(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None

    source_type = str(item.get("type") or item.get("source_type") or "").lower()
    if source_type == "slide":
        source_id = str(item.get("source_id") or item.get("citation") or "")
        source_match = re.fullmatch(r"([^/\\]+\.pdf)#page=(\d+)", source_id, flags=re.IGNORECASE)
        if source_match:
            filename = Path(source_match.group(1)).name
            page = int(source_match.group(2))
        else:
            filename = Path(str(item.get("file", ""))).name
            try:
                page = int(item.get("page", 0))
            except (TypeError, ValueError):
                return None
        return find_slide_page(filename, page)

    if source_type == "transcript":
        source_id = str(item.get("source_id") or item.get("citation") or item.get("source") or "")
        return find_transcript_chunk(source_id)

    return None


def source_matches_scope(source: dict, selected_scope: str) -> bool:
    if selected_scope not in {"day01", "day02"}:
        return True
    source_type = str(source.get("type") or source.get("source_type") or "slide")
    if source_type == "slide":
        return day_from_slide(str(source.get("file", ""))) == selected_scope
    filename = Path(str(source.get("file", ""))).name
    title = str(source.get("document_title") or source.get("title") or "")
    return day_from_transcript(Path(filename), title) == selected_scope


def is_valid_public_source(item: object) -> bool:
    return resolve_runtime_source(item) is not None


def source_open_action(result: dict) -> dict:
    source_type = result.get("type") or result.get("source_type") or "slide"
    if source_type == "transcript":
        segment_id = str(result.get("source_id") or result.get("citation") or result.get("source") or "")
        return {
            "type": "open_transcript",
            "segment_id": segment_id,
            "url": f"/api/transcript-segment?segment_id={urllib.parse.quote(segment_id)}",
        }
    filename = str(result.get("file", ""))
    try:
        page = int(result.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    return {
        "type": "open_slide",
        "file": filename,
        "page": page,
        "url": f"/data/slides/{urllib.parse.quote(filename)}#page={page}&zoom=page-width",
    }


def public_result(result: dict) -> dict:
    source_type = result.get("type") or result.get("source_type") or "slide"
    try:
        relevance_score = int(result.get("relevance_score", result.get("score", 0)))
    except (TypeError, ValueError):
        relevance_score = 0
    if source_type == "transcript":
        source_id = result.get("source_id") or result.get("source") or ""
        return {
            "type": "transcript",
            "source_type": "transcript",
            "source": source_id,
            "source_id": source_id,
            "citation": source_id,
            "title": result.get("title", ""),
            "lesson": result.get("lesson", ""),
            "document_title": result.get("document_title") or result.get("title", ""),
            "lesson_title": result.get("lesson") or result.get("title", ""),
            "page": None,
            "segment_id": source_id,
            "preview": safe_preview(
                result.get("context") or result.get("text") or "",
                max_chars=PUBLIC_PREVIEW_CHARS,
            ),
            "url": source_open_action(result)["url"],
            "score": relevance_score,
            "relevance_score": relevance_score,
            "open_action": source_open_action(result),
        }

    source_id = result.get("source_id") or f"{result.get('file', '')}#page={result.get('page', '')}"
    return {
        "type": "slide",
        "source_type": "slide",
        "source": result.get("source", ""),
        "source_id": source_id,
        "citation": result.get("citation", source_id),
        "title": result.get("title", ""),
        "lesson": result.get("lesson", ""),
        "document_title": result.get("document_title") or result.get("lesson", ""),
        "lesson_title": result.get("lesson") or result.get("document_title", ""),
        "file": result.get("file", ""),
        "page": result.get("page", 1),
        "segment_id": None,
        "preview": safe_preview(
            result.get("preview") or result.get("context") or result.get("text") or "",
            max_chars=PUBLIC_PREVIEW_CHARS,
        ),
        "url": result.get("url", ""),
        "score": relevance_score,
        "relevance_score": relevance_score,
        "open_action": source_open_action(result),
    }


def transcript_segment_payload(segment_id: str) -> dict | None:
    source = find_transcript_chunk(segment_id)
    if source is None:
        return None
    raw_content = str(source.get("text") or source.get("context") or "")
    content = sanitize_content(raw_content, max_chars=TRANSCRIPT_VIEW_CHARS)
    public_source = public_result(source)
    return {
        "source": public_source,
        "segment_id": segment_id,
        "document_title": public_source.get("document_title", ""),
        "content": content,
        "truncated": len(clean_extracted_text(raw_content)) > TRANSCRIPT_VIEW_CHARS,
    }


def search_transcripts(query: str, limit: int = 5) -> list[dict]:
    return search_hybrid_sources(query, limit=limit, source_types={"transcript"})
