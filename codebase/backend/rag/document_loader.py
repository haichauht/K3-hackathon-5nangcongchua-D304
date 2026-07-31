"""Load the course library and normalize slide/transcript documents in memory."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from ..config import (
    PUBLIC_PREVIEW_CHARS,
    SETTINGS,
    TRANSCRIPT_CHUNK_MAX_WORDS,
    TRANSCRIPT_CHUNK_OVERLAP_WORDS,
    TRANSCRIPT_CHUNK_TARGET_WORDS,
)
from ..utils.text_utils import (
    clean_extracted_text,
    remove_vietnamese_tone,
    safe_preview,
    sanitize_content,
    transcript_title,
)
from .vision_processor import (
    VISION_STATS,
    format_vision_context,
    get_slide_vision,
    sha256_file,
)

SLIDES_ROOT = SETTINGS.slides_root
TRANSCRIPT_ROOT = SETTINGS.transcript_root
SLIDE_PAGE_CACHE: list[dict] | None = None
TRANSCRIPT_CHUNK_CACHE: list[dict] | None = None
TRANSCRIPT_SEGMENT_CACHE: list[dict] | None = None


def list_library() -> dict:
    slides = []
    if SLIDES_ROOT.exists():
        for pdf in sorted(SLIDES_ROOT.glob("*.pdf")):
            pages = estimate_pdf_pages(pdf)
            slides.append(
                {
                    "id": pdf.name,
                    "kind": "slide",
                    "day_id": day_from_slide(pdf.name),
                    "title": slide_title(pdf.name),
                    "filename": pdf.name,
                    "pages": pages,
                    "subtitle": f"{pages} trang · PDF slide",
                    "url": f"/data/slides/{urllib.parse.quote(pdf.name)}",
                }
            )

    transcripts = []
    if TRANSCRIPT_ROOT.exists():
        for md in sorted(TRANSCRIPT_ROOT.glob("transcript-*-clean.md")):
            title = transcript_title(md)
            transcripts.append(
                {
                    "id": md.name,
                    "kind": "transcript",
                    "day_id": day_from_transcript(md, title),
                    "title": title,
                    "filename": md.name,
                    "subtitle": "Transcript · dùng cho Recall search",
                }
            )

    return {
        "slides": slides,
        "transcripts": transcripts,
        "days": group_documents_by_day(slides, transcripts),
        "chatlog": {"available": False, "messages": 0, "turns": 0},
        "chatlog_available": False,
        "data_root": "data/vlearn-pack",
    }


def day_from_slide(filename: str) -> str:
    match = re.search(r"\bd(\d+)", filename.lower())
    if match:
        return f"day{int(match.group(1)):02d}"
    return "other"


def day_from_transcript(path: Path, title: str) -> str:
    normalized = remove_vietnamese_tone(f"{path.name} {title}".lower())
    if "day 1" in normalized or "foundation" in normalized:
        return "day01"
    if "day 2" in normalized or "bai toan" in normalized or "danh gia" in normalized or "du lieu" in normalized:
        return "day02"
    return "other"


def day_label(day_id: str) -> str:
    if day_id.startswith("day") and day_id[3:].isdigit():
        return f"Day{int(day_id[3:]):02d}"
    return "Nguồn khác"


def day_sort_key(day_id: str) -> tuple[int, str]:
    if day_id.startswith("day") and day_id[3:].isdigit():
        return (int(day_id[3:]), day_id)
    return (99, day_id)


def slide_title(filename: str) -> str:
    mapping = {
        "d1-slide-hackathon.pdf": "AI & LLM Foundation",
        "d2-slide-hackathon.pdf": "Xác định bài toán cho AI",
    }
    return mapping.get(filename, Path(filename).stem)


def group_documents_by_day(slides: list[dict], transcripts: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for doc in slides:
        grouped.setdefault(doc["day_id"], []).append(doc)

    days = []
    for day_id in sorted(grouped, key=day_sort_key):
        docs = sorted(grouped[day_id], key=lambda item: item["title"])
        days.append(
            {
                "id": day_id,
                "title": day_label(day_id),
                "doc_count": len(docs),
                "slide_count": len(docs),
                "transcript_count": 0,
                "status": "STUDYING" if day_id == "day02" else "PUBLISHED",
                "docs": docs,
            }
        )

    return days


def estimate_pdf_pages(path: Path) -> int:
    try:
        content = path.read_bytes()
    except OSError:
        return 0

    return len(re.findall(rb"/Type\s*/Page\b", content))


def first_meaningful_line(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 4:
            continue
        if re.fullmatch(r"\d+\s*/\s*\d+", line):
            continue
        if remove_vietnamese_tone(line.lower()) in {"vinuniversity", "ai in action"}:
            continue
        return sanitize_content(line, max_chars=90)
    return ""


def is_slide_boilerplate(value: str) -> bool:
    normalized = remove_vietnamese_tone(value.lower())
    return bool(
        "ai in action" in normalized
        or normalized.startswith(("day 0", "nguon ", "bai toan ·"))
        or re.fullmatch(r"\d+\s*/\s*\d+", normalized)
    )


def looks_like_spaced_ocr_heading(value: str) -> bool:
    words = re.findall(r"[^\W\d_]+", value, flags=re.UNICODE)
    if len(words) < 5:
        return False
    short_words = sum(1 for word in words if len(word) <= 2)
    return short_words / len(words) >= 0.6


def layout_slide_title(page, fallback_text: str) -> str:
    """Select the visual page heading instead of the first PDF text object."""
    candidates: list[tuple[float, str]] = []
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        blocks = []

    for block in blocks:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = " ".join(
                str(span.get("text", "")).strip()
                for span in spans
                if str(span.get("text", "")).strip()
            ).strip()
            text = sanitize_content(text, max_chars=110)
            letters = re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)
            if (
                len(text) < 4
                or len(text) > 105
                or sum(len(word) for word in letters) < 4
                or is_slide_boilerplate(text)
            ):
                continue
            size = max((float(span.get("size", 0)) for span in spans), default=0)
            candidates.append((size, text))

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return first_meaningful_line(fallback_text)


def slide_preview(text: str, title: str, max_chars: int = 220) -> str:
    normalized_title = remove_vietnamese_tone(title.lower()).strip()
    lines = []
    for raw_line in text.splitlines():
        line = sanitize_content(raw_line, max_chars=240)
        if not line or is_slide_boilerplate(line) or looks_like_spaced_ocr_heading(line):
            continue
        if remove_vietnamese_tone(line.lower()).strip() == normalized_title:
            continue
        lines.append(line)
    return safe_preview(" ".join(lines), max_chars=max_chars)


def load_slide_pages() -> list[dict]:
    global SLIDE_PAGE_CACHE
    if SLIDE_PAGE_CACHE is not None:
        return SLIDE_PAGE_CACHE

    pages: list[dict] = []
    if not SLIDES_ROOT.exists():
        SLIDE_PAGE_CACHE = pages
        return pages

    try:
        import fitz
    except ImportError:
        SLIDE_PAGE_CACHE = pages
        return pages

    for pdf in sorted(SLIDES_ROOT.glob("*.pdf")):
        try:
            pdf_hash = sha256_file(pdf)
            document = fitz.open(str(pdf))
        except Exception:
            continue

        try:
            for index in range(1, document.page_count + 1):
                page = document.load_page(index - 1)
                try:
                    text = clean_extracted_text(page.get_text("text") or "")
                except Exception:
                    text = ""
                try:
                    image_count = len(page.get_images(full=True))
                except Exception:
                    image_count = 0
                try:
                    drawing_count = len(page.get_drawings())
                except Exception:
                    drawing_count = 0

                vision = get_slide_vision(
                    pdf,
                    index,
                    pdf_hash,
                    text,
                    page,
                    image_count,
                    drawing_count,
                )
                visual_context = format_vision_context(vision)
                title = layout_slide_title(page, text)
                if not title and vision and vision.get("title"):
                    title = vision["title"]
                title = title or f"{slide_title(pdf.name)} - Trang {index}"
                pages.append(
                    {
                        "type": "slide",
                        "kind": "slide",
                        "source": f"Trang {index}",
                        "title": title,
                        "lesson": slide_title(pdf.name),
                        "file": pdf.name,
                        "page": index,
                        "url": f"/data/slides/{urllib.parse.quote(pdf.name)}#page={index}&zoom=page-width",
                        "text": text,
                        "preview": slide_preview(text, title, max_chars=220),
                        "context": sanitize_content("\n".join(filter(None, [text, visual_context])), max_chars=1100),
                        "visual_summary": (vision or {}).get("visual_summary", ""),
                        "important_labels": " ".join((vision or {}).get("important_labels", [])),
                        "relationships": " ".join((vision or {}).get("relationships", [])),
                        "uncertain_details": " ".join((vision or {}).get("uncertain_details", [])),
                        "vision_status": "ok" if vision else "text_only",
                        "score": 0,
                    }
                )
        finally:
            document.close()

    SLIDE_PAGE_CACHE = pages
    return pages


def transcript_subchunks(
    value: str,
    *,
    target_words: int = TRANSCRIPT_CHUNK_TARGET_WORDS,
    max_words: int = TRANSCRIPT_CHUNK_MAX_WORDS,
    overlap_words: int = TRANSCRIPT_CHUNK_OVERLAP_WORDS,
) -> list[str]:
    """Split a parent transcript segment without losing sentence boundaries.

    Retrieval works on bounded subchunks, while the public open action continues
    to target the immutable parent ``[Txx-xxx]`` segment.
    """

    text = clean_extracted_text(value)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?…])\s+|\n+", text)
        if sentence.strip()
    ]
    if not sentences:
        return []

    units: list[list[str]] = []
    for sentence in sentences:
        words = sentence.split()
        if len(words) <= max_words:
            units.append(words)
            continue
        for start in range(0, len(words), max_words):
            units.append(words[start : start + max_words])

    chunks: list[list[str]] = []
    current: list[str] = []
    for words in units:
        if current and len(current) + len(words) > max_words:
            chunks.append(current)
            current = current[-overlap_words:] if overlap_words else []
        current.extend(words)
        if len(current) >= target_words:
            chunks.append(current[:max_words])
            current = current[max(0, len(current) - overlap_words) :]
    if current:
        if chunks and len(current) <= overlap_words:
            chunks[-1].extend(current)
            chunks[-1] = chunks[-1][:max_words]
        else:
            chunks.append(current[:max_words])

    return [" ".join(words).strip() for words in chunks if words]


def load_transcript_segments() -> list[dict]:
    global TRANSCRIPT_SEGMENT_CACHE
    if TRANSCRIPT_SEGMENT_CACHE is not None:
        return TRANSCRIPT_SEGMENT_CACHE

    segments: list[dict] = []
    if not TRANSCRIPT_ROOT.exists():
        TRANSCRIPT_SEGMENT_CACHE = segments
        return segments

    for path in sorted(TRANSCRIPT_ROOT.glob("transcript-*-clean.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        raw_chunks = re.split(r"(?m)(?=^\*\*\[T\d{2}-\d{3}\]\*\*)", text)
        for raw_chunk in raw_chunks:
            cleaned = clean_extracted_text(raw_chunk)
            source_match = re.search(r"\[T\d{2}-\d{3}\]", cleaned)
            if not source_match or len(cleaned) < 12:
                continue

            source_id = source_match.group(0)
            title = transcript_title(path)
            parent_text = re.sub(
                rf"^\s*\*\*{re.escape(source_id)}\*\*\s*",
                "",
                cleaned,
                count=1,
            ).strip()
            segments.append(
                {
                    "type": "transcript",
                    "source_type": "transcript",
                    "source_id": source_id,
                    "citation": source_id,
                    "source": source_id,
                    "title": title,
                    "document_title": title,
                    "lesson": title,
                    "file": path.name,
                    "file_path": str(path),
                    "relative_file_path": f"transcript/{path.name}",
                    "document_id": f"transcript:{source_id}",
                    "text": parent_text,
                    "page": None,
                    "url": "",
                    "preview": "",
                    "context": sanitize_content(parent_text, max_chars=1200),
                    "score": 0,
                }
            )

    TRANSCRIPT_SEGMENT_CACHE = segments
    return segments


def load_transcript_chunks() -> list[dict]:
    global TRANSCRIPT_CHUNK_CACHE
    if TRANSCRIPT_CHUNK_CACHE is not None:
        return TRANSCRIPT_CHUNK_CACHE

    chunks: list[dict] = []
    for segment in load_transcript_segments():
        parts = transcript_subchunks(str(segment.get("text", "")))
        if not parts:
            continue
        for chunk_index, chunk_text in enumerate(parts, start=1):
            source_id = str(segment["source_id"])
            chunk_id = f"{source_id}#chunk={chunk_index}"
            chunks.append(
                {
                    **segment,
                    "parent_segment_id": source_id,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                    "document_id": f"transcript:{chunk_id}",
                    "text": chunk_text,
                    "preview": safe_preview(chunk_text, max_chars=PUBLIC_PREVIEW_CHARS),
                    "context": sanitize_content(chunk_text, max_chars=1200),
                }
            )

    TRANSCRIPT_CHUNK_CACHE = chunks
    return chunks


def build_runtime_documents() -> list[dict]:
    return [
        *[
            {
                **page,
                "source_type": "slide",
                "source_id": f"{page.get('file', '')}#page={page.get('page', '')}",
                "citation": f"{page.get('file', '')} · Trang {page.get('page', '')}",
                "document_title": page.get("lesson", ""),
                "file_path": str(SLIDES_ROOT / str(page.get("file", ""))),
                "relative_file_path": f"slides/{page.get('file', '')}",
                "document_id": f"slide:{page.get('file', '')}#page={page.get('page', '')}",
            }
            for page in load_slide_pages()
        ],
        *load_transcript_chunks(),
    ]


def reset_document_caches() -> None:
    global SLIDE_PAGE_CACHE, TRANSCRIPT_CHUNK_CACHE, TRANSCRIPT_SEGMENT_CACHE
    SLIDE_PAGE_CACHE = None
    TRANSCRIPT_CHUNK_CACHE = None
    TRANSCRIPT_SEGMENT_CACHE = None
