"""Text normalization and redaction helpers."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

from ..config import SETTINGS

TRANSCRIPT_ROOT = SETTINGS.transcript_root
GENERIC_RETRIEVAL_TERMS = {
    "ai", "model", "product", "prompt", "workflow", "data", "system",
    "nguon", "noi", "dung", "lam", "phan", "context", "source",
    "value", "cost", "outcome", "impact", "effort", "baseline",
    "scope", "problem", "use", "case",
}


def remove_vietnamese_tone(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.replace("đ", "d")


def tokenize(value: str) -> list[str]:
    normalized = remove_vietnamese_tone(value.lower())
    tokens = re.findall(r"[a-z0-9]+", normalized)
    stopwords = {
        "ban",
        "minh",
        "toi",
        "em",
        "anh",
        "chi",
        "thay",
        "co",
        "noi",
        "ve",
        "voi",
        "dau",
        "ay",
        "la",
        "gi",
        "nao",
        "phan",
        "tim",
        "cho",
        "hoi",
        "muon",
        "nho",
        "mang",
        "mot",
        "cai",
        "nay",
        "kia",
        "trong",
        "duoc",
        "khong",
        "can",
        "hay",
        "slide",
        "trang",
        "sao",
        "nhin",
        "gon",
        "hon",
        "bo",
        "the",
        "thi",
        "neu",
        "khac",
        "nhau",
        "nen",
        "dua",
        "chon",
    }
    return [token for token in tokens if len(token) > 2 and token not in stopwords]


def score_text(value: str, query_tokens: list[str]) -> int:
    normalized = remove_vietnamese_tone(value.lower())
    word_counts = Counter(re.findall(r"[a-z0-9]+", normalized))
    score = 0
    for token in query_tokens:
        count = word_counts.get(token, 0)
        if not count:
            continue
        weight = 1 if token in GENERIC_RETRIEVAL_TERMS else 3
        score += min(count, 3) * weight
    return score


def clean_extracted_text(value: str) -> str:
    """Normalize PDF extraction artifacts before indexing or prompting."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\ufffd", " ")
    text = re.sub(r"[\ue000-\uf8ff]", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_content(value: str, max_chars: int = 280) -> str:
    compact = clean_extracted_text(value)
    compact = re.sub(r"\s+", " ", compact).strip()
    compact = re.sub(r"\[REDACTED_[^\]]+\]", "[REDACTED]", compact)
    compact = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL_REDACTED]", compact)
    compact = re.sub(r"(?<!\d)(?:\+?84|0)(?:\s|\.|-)?(?:3|5|7|8|9)(?:\d(?:\s|\.|-)?){8}(?!\d)", "[PHONE_REDACTED]", compact)
    compact = re.sub(r"\b(?:user_id|conversation_id|message_id)\b\s*[:=]\s*\S+", "[ID_REDACTED]", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\b(?:U|C|M)\d{4,}\b", "[ID_REDACTED]", compact)

    if len(compact) > max_chars:
        return compact[: max_chars - 1].rstrip() + "…"
    return compact


def sanitize_user_answer(value: str, max_chars: int = 900) -> str:
    compact = sanitize_content(value, max_chars=max_chars)
    compact = re.sub(r"\btranscript\b", "nguồn học", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bchatlog\b", "nguồn học", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bturn_id\b|\bmessage_id\b|\bconversation_id\b|\buser_id\b", "mã nguồn", compact, flags=re.IGNORECASE)
    return compact


def safe_history_items(raw_history: object) -> list[dict]:
    if not isinstance(raw_history, list):
        return []
    cleaned = []
    for item in raw_history[-4:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = sanitize_content(str(item.get("content", "")), max_chars=420)
        if content:
            cleaned.append({"role": item["role"], "content": content})
    return cleaned


def safe_preview(value: str, max_chars: int = 280) -> str:
    return sanitize_content(value, max_chars=max_chars)


def transcript_title(path_or_name) -> str:
    path = path_or_name if isinstance(path_or_name, Path) else TRANSCRIPT_ROOT / str(path_or_name)

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as file:
            for line in file:
                if line.startswith("#"):
                    return line.lstrip("#").strip()
    except OSError:
        pass

    return path.name


def extract_openai_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]

    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue

        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                return content["text"]

    raise KeyError("output_text")
