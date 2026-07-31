"""Grounded formatting for summarize, synthesize, compare and self-check actions."""

from __future__ import annotations

import re

from ..utils.text_utils import (
    clean_extracted_text,
    remove_vietnamese_tone,
    sanitize_content,
    sanitize_user_answer,
    tokenize,
)

def citation_token(result: dict) -> str:
    source_type = result.get("type") or result.get("source_type") or "slide"
    if source_type == "transcript":
        return str(result.get("source_id") or result.get("citation") or result.get("source") or "")
    return str(
        result.get("source_id")
        or f"{result.get('file', '')}#page={result.get('page', '')}"
    )


def citation_marker(result: dict) -> str:
    token = citation_token(result)
    if re.fullmatch(r"\[T\d{2}-\d{3}\]", token):
        return token
    return f"[[{token}]]" if token else ""


def source_evidence_bullets(result: dict, limit: int = 4) -> list[str]:
    context = str(result.get("context") or result.get("text") or result.get("preview") or "")
    context = re.sub(r"\[T\d{2}-\d{3}\]", " ", context)
    bullets = extract_summary_bullets(context)
    if not bullets:
        title = clean_slide_heading(result)
        if title:
            bullets.append(f"Nguồn tập trung vào chủ đề {title}")
    return bullets[:limit]


def sanitize_structured_answer(value: str, max_chars: int = 1200) -> str:
    """Redact model output while preserving the line structure required by actions."""
    raw = clean_extracted_text(value)
    lines: list[str] = []
    for raw_line in raw.split("\n"):
        safe_line = sanitize_content(raw_line, max_chars=max_chars)
        safe_line = re.sub(r"\btranscript\b", "nguồn học", safe_line, flags=re.IGNORECASE)
        safe_line = re.sub(r"\bchatlog\b", "nguồn học", safe_line, flags=re.IGNORECASE)
        safe_line = re.sub(
            r"\bturn_id\b|\bmessage_id\b|\bconversation_id\b|\buser_id\b",
            "mã nguồn",
            safe_line,
            flags=re.IGNORECASE,
        )
        if safe_line:
            lines.append(safe_line)
        elif lines and lines[-1] != "":
            lines.append("")

    structured = "\n".join(lines).strip()
    if len(structured) <= max_chars:
        return structured
    candidate = structured[:max_chars].rstrip()
    boundary = max(candidate.rfind("\n"), candidate.rfind(". "), candidate.rfind("? "))
    if boundary >= max_chars // 2:
        candidate = candidate[: boundary + 1].rstrip()
    return candidate + "…"


def strip_known_citations(value: str, markers: list[str]) -> str:
    cleaned = value
    for marker in markers:
        cleaned = cleaned.replace(marker, " ")
    cleaned = re.sub(r"\bCitation\s*:\s*", " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" -:;")


def normalize_task_answer(
    answer: str,
    results: list[dict],
    task: str = "answer",
) -> tuple[str, bool]:
    """Normalize OpenAI action output without inventing content outside its answer."""
    if not answer or not results:
        return "", False

    markers = [
        citation_marker(result)
        for result in results[:3]
        if citation_marker(result)
    ]
    if not markers:
        return "", False
    if task == "answer":
        return ensure_answer_citations(answer, results, task=task), True

    flat = re.sub(r"\s+", " ", answer).strip()
    if task == "summarize_first":
        marker = markers[0]
        heading_pattern = re.compile(
            r"3\s+(?:điều|dieu)\s+(?:cần|can)\s+(?:nhớ|nho)",
            flags=re.IGNORECASE,
        )
        heading_match = heading_pattern.search(flat)
        numbered_section = flat[heading_match.end() :] if heading_match else flat
        main_match = re.search(
            r"(?:Ý|Y)\s+(?:chính|chinh)\s*:\s*(.+?)"
            r"(?=3\s+(?:điều|dieu)\s+(?:cần|can)\s+(?:nhớ|nho))",
            flat,
            flags=re.IGNORECASE,
        )
        numbered = re.findall(
            r"(?:^|\s)([1-3])\.\s*(.+?)(?=(?:\s+[1-3]\.\s)|$)",
            numbered_section,
        )
        items_by_number: dict[str, str] = {}
        for number, item in numbered:
            cleaned = strip_known_citations(item, markers)
            if cleaned and number not in items_by_number:
                items_by_number[number] = sentence_limited_content(cleaned, max_chars=240)
        if set(items_by_number) != {"1", "2", "3"}:
            return "", False
        main_idea = strip_known_citations(
            main_match.group(1) if main_match else items_by_number["1"],
            markers,
        )
        main_idea = sentence_limited_content(main_idea, max_chars=320)
        if not main_idea:
            return "", False
        normalized_summary = (
            "Ý chính\n\n"
            f"{main_idea.rstrip('.')}.\n\n"
            "3 điều cần nhớ\n\n"
            f"1. {items_by_number['1'].rstrip('.')}.\n"
            f"2. {items_by_number['2'].rstrip('.')}.\n"
            f"3. {items_by_number['3'].rstrip('.')}.\n\n"
            f"Citation: {marker}"
        )
        if not covers_structured_levels(normalized_summary, results[0]):
            return "", False
        return normalized_summary, True

    marker_pattern = re.compile("|".join(re.escape(marker) for marker in markers))
    if task in {"synthesize_sources", "compare_sources"}:
        items: list[tuple[str, str]] = []
        seen: set[str] = set()
        cursor = 0
        for match in marker_pattern.finditer(flat):
            idea = flat[cursor : match.start()]
            cursor = match.end()
            idea = re.sub(
                r"^\s*(?:Tổng hợp theo vấn đề\s*)?(?:[-*•]|\d+[.)])?\s*",
                "",
                idea,
                flags=re.IGNORECASE,
            )
            idea = strip_known_citations(idea, markers)
            idea = sentence_limited_content(idea, max_chars=300)
            normalized = " ".join(tokenize(remove_vietnamese_tone(idea.lower())))
            if not idea or normalized in seen:
                continue
            seen.add(normalized)
            items.append((idea, match.group(0)))
            if len(items) >= 5:
                break
        if not items:
            return "", False
        lines = [
            f"{index}. {idea.rstrip('.')}. {marker}"
            for index, (idea, marker) in enumerate(items, start=1)
        ]
        heading = "So sánh các slide" if task == "compare_sources" else "Tổng hợp theo vấn đề"
        return heading + "\n\n" + "\n".join(lines), True

    if task == "self_check":
        split_lists = re.sub(
            r"\s+(?=(?:[-*•]|\d+[.)])\s+)",
            "\n",
            answer,
        )
        questions: list[tuple[str, str]] = []
        seen_questions: set[str] = set()
        for line in split_lists.splitlines():
            question_end = line.rfind("?")
            if question_end < 0:
                continue
            marker_match = marker_pattern.search(line, question_end + 1)
            if not marker_match:
                continue
            question = re.sub(
                r"^\s*(?:[-*•]|\d+[.)])\s*",
                "",
                line[: question_end + 1],
            ).strip()
            if len(tokenize(question)) < 3:
                continue
            normalized = remove_vietnamese_tone(question.lower())
            if normalized in seen_questions:
                continue
            seen_questions.add(normalized)
            questions.append((question, marker_match.group(0)))
            if len(questions) >= 3:
                break
        if not questions:
            return "", False
        lines = [
            f"{index}. {question} {marker}"
            for index, (question, marker) in enumerate(questions, start=1)
        ]
        return (
            "Câu tự kiểm tra — chưa hiển thị đáp án\n\n"
            + "\n".join(lines)
        ), True

    return "", False


def ensure_answer_citations(answer: str, results: list[dict], task: str = "answer") -> str:
    if not answer or not results:
        return answer
    valid_markers = [citation_marker(result) for result in results[:3] if citation_marker(result)]
    if any(marker in answer for marker in valid_markers):
        return answer
    suffix = " ".join(
        valid_markers
        if task in {"synthesize_sources", "compare_sources"}
        else valid_markers[:1]
    )
    return sanitize_structured_answer(f"{answer}\n\n{suffix}", max_chars=1200)


def fallback_source_answer(results: list[dict]) -> str:
    if not results:
        return "Mình chưa có nguồn đủ chắc để trả lời."
    items = []
    for source in results[:3]:
        bullets = source_evidence_bullets(source, limit=1)
        if bullets:
            items.append((bullets[0], source))
    if not items:
        return "Mình chưa có đủ nội dung trong nguồn để trả lời chắc chắn."
    lines = [
        f"{index}. {bullet.rstrip('.')}. {citation_marker(source)}"
        for index, (bullet, source) in enumerate(items, start=1)
    ]
    return (
        "Các nguồn liên quan nhất\n\n"
        + "\n".join(lines)
        + "\n\nMỗi ý trên chỉ phản ánh nội dung của nguồn được trích dẫn; hãy mở nguồn để đối chiếu chi tiết."
    )


def fallback_source_summary(results: list[dict]) -> str:
    if not results:
        return "Mình chưa có nguồn đủ chắc để tóm tắt."
    source = results[0]
    bullets = source_evidence_bullets(source, limit=8)
    if not bullets:
        return "Nguồn được chọn không có đủ nội dung để tóm tắt an toàn."

    main_idea = sentence_limited_content(clean_slide_heading(source), max_chars=280)
    if not main_idea:
        main_idea = bullets[0]
    candidates = [
        bullet
        for bullet in bullets
        if not ideas_are_near_duplicates(bullet, main_idea)
    ]
    takeaways = select_three_complete_takeaways(candidates)
    if len(takeaways) < 3:
        return "Nguồn được chọn chưa có đủ ba ý hoàn chỉnh để tóm tắt an toàn."

    marker = citation_marker(source)
    return (
        "Ý chính\n\n"
        f"{main_idea.rstrip('.')}.\n\n"
        "3 điều cần nhớ\n\n"
        f"1. {takeaways[0].rstrip('.')}.\n"
        f"2. {takeaways[1].rstrip('.')}.\n"
        f"3. {takeaways[2].rstrip('.')}.\n\n"
        f"Citation: {marker}"
    )


def fallback_source_synthesis(results: list[dict]) -> str:
    if not results:
        return "Mình chưa có nguồn đủ chắc để tổng hợp."
    items = []
    for source in results[:3]:
        for bullet in source_evidence_bullets(source, limit=2):
            if not normalized_idea(bullet):
                continue
            if any(ideas_are_near_duplicates(bullet, existing) for existing, _ in items):
                continue
            items.append((bullet, source))
            if len(items) >= 5:
                break
        if len(items) >= 5:
            break
    if not items:
        return "Các nguồn được chọn không có đủ nội dung để tổng hợp an toàn."
    lines = [
        f"{index}. {bullet.rstrip('.')}. {citation_marker(source)}"
        for index, (bullet, source) in enumerate(items, start=1)
    ]
    return "Tổng hợp theo vấn đề\n\n" + "\n".join(lines)


def fallback_source_comparison(results: list[dict]) -> str:
    if len(results) < 2:
        return "Mình cần ít nhất hai slide đủ chắc để so sánh."
    lines = []
    for index, source in enumerate(results[:3], start=1):
        bullets = source_evidence_bullets(source, limit=1)
        if not bullets:
            continue
        lines.append(
            f"{index}. {clean_slide_heading(source)} nhấn mạnh: "
            f"{bullets[0].rstrip('.')}. {citation_marker(source)}"
        )
    if len(lines) < 2:
        return "Các nguồn được chọn chưa có đủ nội dung để so sánh an toàn."
    return "So sánh các slide\n\n" + "\n".join(lines)


def fallback_self_check(results: list[dict]) -> str:
    if not results:
        return "Mình chưa có nguồn đủ chắc để tạo câu tự kiểm tra."
    questions = []
    for source in results[:3]:
        title = clean_slide_heading(source)
        marker = citation_marker(source)
        if not title or not marker:
            continue
        questions.append(
            f"{len(questions) + 1}. Bạn có thể giải thích bằng lời của mình ý chính của “{title}” không? {marker}"
        )
        if len(questions) >= 3:
            break
    if not questions:
        return "Nguồn được chọn không có đủ metadata để tạo câu tự kiểm tra."
    return (
        "Câu tự kiểm tra — chưa hiển thị đáp án\n\n"
        + "\n".join(questions)
    )


def fallback_summary_from_slides(results: list[dict]) -> str:
    if not results:
        return "Mình chưa có nguồn slide đủ chắc để tóm tắt."

    first = results[0]
    source_type = first.get("type") or first.get("source_type") or "slide"
    top_score = int(first.get("score", 0))
    context = sentence_limited_content(first.get("context") or first.get("preview") or first.get("title", ""), max_chars=520)
    bullets = extract_summary_bullets(context)
    title = clean_slide_heading(first)

    if top_score < 16:
        return (
            f"Mình tìm thấy một nguồn có liên quan: {title}.\n\n"
            "Nguồn này chưa đủ trực tiếp để kết luận chắc cho câu hỏi của bạn; "
            "hãy mở slide bên dưới hoặc thêm từ khóa cụ thể để mình tìm đúng hơn."
        )

    source_label = "Đoạn transcript này" if source_type == "transcript" else "Slide này"
    if not bullets:
        return f"{title}\n\n{source_label} tập trung vào chủ đề {title.lower()}. Bạn có thể kiểm tra lại nguồn bên dưới."

    first_sentence = bullets[0].rstrip(".")
    remaining = bullets[1:3]
    if remaining:
        detail = " ".join(sentence.rstrip(".") + "." for sentence in remaining)
        return f"{title}\n\n{source_label} nói về {first_sentence.lower()}. {detail}"
    return f"{title}\n\n{source_label} nói về {first_sentence.lower()}."


def clean_slide_heading(result: dict) -> str:
    title = sanitize_content(str(result.get("title") or result.get("lesson") or "Nội dung bài giảng"), max_chars=90)
    title = re.sub(r"^\d+[\).\s-]+", "", title).strip()
    normalized = remove_vietnamese_tone(title.lower())
    if normalized == "automate":
        return "Khi nào nên dùng AI để tự động hóa?"
    if normalized == "augment":
        return "Khi nào nên để AI hỗ trợ con người?"
    if normalized in {"ai agent", "agentic ai"}:
        return "Từ LLM đến AI Agent"
    return title or "Nội dung bài giảng"


def display_source_name(result: dict) -> str:
    source_type = result.get("type") or result.get("source_type") or "slide"
    if source_type == "transcript":
        return f"{result.get('source_id') or result.get('source') or '[transcript]'} · {sanitize_content(str(result.get('lesson') or 'Transcript bài giảng'), max_chars=80)}"
    lesson = sanitize_content(str(result.get("lesson") or "Bài giảng Hackathon"), max_chars=80)
    page = result.get("page", "")
    return f"{lesson}, trang {page}".strip()


def extract_summary_bullets(text: str) -> list[str]:
    cleaned = clean_extracted_text(text)
    cleaned = re.sub(r"\b\d+\s*/\s*\d+\b", " ", cleaned)
    cleaned = re.sub(
        r"\bAI\s+IN\s+ACTION\s*-\s*HACKATHON\b.*$",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?=(?:LEVEL\s+\d+\b|C\s*ẤP\s+Đ\s*Ộ\s+\d+\b|"
        r"[1-5]\s+(?:Goal|Reasoning|Tools|Action)\b|Memory\s+sổ\s+tay\b))",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    parts = re.split(r"(?:[;•\n]| - |·)+|(?<=[.!?])\s+", cleaned)
    bullets = []
    for part in parts:
        item = complete_evidence_idea(part, max_chars=280).strip(" -:")
        if len(item) < 14:
            continue
        normalized = normalized_idea(item)
        if not normalized:
            continue
        if normalized in {"ai in action", "vinuniversity", "automate", "augment"}:
            continue
        if any(ideas_are_near_duplicates(item, existing) for existing in bullets):
            continue
        bullets.append(item)
        if len(bullets) >= 8:
            break
    return bullets


def normalized_idea(value: str) -> str:
    return " ".join(tokenize(remove_vietnamese_tone(value.lower())))


def structured_level_number(value: str) -> int | None:
    match = re.match(r"^\s*LEVEL\s+(\d+)\b", value, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def label_structured_level(value: str) -> str:
    level = structured_level_number(value)
    if level is None:
        return value
    content = re.sub(r"^\s*LEVEL\s+\d+\s*", "", value, flags=re.IGNORECASE).strip()
    return f"Bậc {level + 1} — LEVEL {level}: {content}"


def select_three_complete_takeaways(candidates: list[str]) -> list[str]:
    """Keep three takeaways without dropping the final level of a sequence."""

    level_items = [item for item in candidates if structured_level_number(item) is not None]
    if len(level_items) > 3:
        labelled = [label_structured_level(item) for item in level_items]
        first_group_size = len(labelled) - 2
        return [
            "; ".join(labelled[:first_group_size]),
            labelled[-2],
            labelled[-1],
        ]
    return candidates[:3]


def covers_structured_levels(answer: str, source: dict) -> bool:
    context = str(source.get("context") or source.get("text") or source.get("preview") or "")
    expected = {
        int(value)
        for value in re.findall(r"\bLEVEL\s+(\d+)\b", context, flags=re.IGNORECASE)
    }
    if len(expected) < 2:
        return True
    actual = {
        int(value)
        for value in re.findall(r"\bLEVEL\s+(\d+)\b", answer, flags=re.IGNORECASE)
    }
    return expected.issubset(actual)


def ideas_are_near_duplicates(left: str, right: str) -> bool:
    left_tokens = set(normalized_idea(left).split())
    right_tokens = set(normalized_idea(right).split())
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap >= 0.8


def complete_evidence_idea(value: str, max_chars: int = 280) -> str:
    compact = sanitize_content(value, max_chars=max_chars * 3).strip()
    if not compact or compact.endswith("…"):
        return ""
    if len(compact) <= max_chars:
        return compact

    candidate = compact[:max_chars].rstrip()
    sentence_end = max(
        candidate.rfind("."),
        candidate.rfind("?"),
        candidate.rfind("!"),
    )
    if sentence_end >= 60:
        return candidate[: sentence_end + 1].strip()

    # A fragment without a real sentence/structural boundary is less useful
    # than omitting the idea; never turn a cut clause into a fake sentence.
    return ""


def sentence_limited_content(value: str, max_chars: int = 520) -> str:
    compact = sanitize_content(value, max_chars=max_chars * 2)
    if len(compact) <= max_chars:
        return compact

    candidate = compact[:max_chars].rstrip()
    sentence_end = max(candidate.rfind("."), candidate.rfind("?"), candidate.rfind("!"))
    if sentence_end >= 80:
        return candidate[: sentence_end + 1].strip()

    # Reject an overlong clause with no sentence boundary. Returning a clipped
    # prefix and adding punctuation later would manufacture a broken sentence.
    return ""


def slide_source_map(slide_results: list[dict], model_reasons: list[dict]) -> list[dict]:
    reasons = [
        sanitize_user_answer(str(item.get("reason", "")), max_chars=140)
        for item in model_reasons
        if isinstance(item, dict)
    ]
    mapped = []
    for index, result in enumerate(slide_results[:3]):
        source_type = result.get("type") or result.get("source_type") or "slide"
        source_id = result.get("source_id") or result.get("source") or ""
        if source_type == "transcript":
            default_reason = "Đoạn transcript này khớp với chủ đề và được dùng làm căn cứ nội bộ để grounding."
        else:
            default_reason = "Trang này khớp với các từ khóa trong câu hỏi và là nguồn slide có thể mở trực tiếp."
        mapped.append(
            {
                "source": source_id or f"{result.get('file', '')} · Trang {result.get('page', '')}",
                "source_id": source_id,
                "citation": result.get("citation", source_id),
                "type": source_type,
                "reason": reasons[index] if index < len(reasons) and reasons[index] else default_reason,
                "url": result.get("url", ""),
                "file": result.get("file", ""),
                "page": result.get("page", 1),
                "score": result.get("score", 0),
            }
        )
    return mapped


def format_public_sources(results: list[dict]) -> str:
    lines = []
    for result in results:
        source_type = result.get("type") or result.get("source_type") or "slide"
        token = citation_token(result)
        marker = citation_marker(result)
        if source_type == "transcript":
            lines.append(
                f"- token={token}, citation_format={marker}, type=transcript, "
                f"title={result.get('title', '')}"
            )
        else:
            lines.append(
                f"- token={token}, citation_format={marker}, type=slide, "
                f"title={result.get('title', '')}, url={result.get('url', '')}"
            )
    return "\n".join(lines)


def format_evidence(results: list[dict]) -> str:
    blocks = []
    for index, result in enumerate(results[:5], start=1):
        context = result.get("context") or result.get("preview", "")
        source_type = result.get("type") or result.get("source_type") or "slide"
        source_id = result.get("source_id") or result.get("source") or ""
        if source_type == "transcript":
            blocks.append(
                "\n".join(
                    [
                        f"[{index}] source_id={source_id}",
                        "type=transcript",
                        f"title={result.get('title', '')}",
                        f"context={sanitize_content(context, max_chars=520)}",
                    ]
                )
            )
            continue

        blocks.append(
            "\n".join(
                [
                    f"[{index}] source={source_id}",
                    "type=slide",
                    f"title={result.get('title', '')}",
                    f"file={result.get('file', '')}",
                    f"page={result.get('page', '')}",
                    f"url={result.get('url', '')}",
                    f"context={sanitize_content(context, max_chars=520)}",
                ]
            )
        )

    return "\n\n".join(blocks)
