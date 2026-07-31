"""Optional dense embeddings for semantic recall.

Document embeddings are built once and persisted as vectors under ``data/``.
At request time only the normalized search query is sent to the embeddings
endpoint. Conversation history and chatlog data are never accepted here.
"""

from __future__ import annotations

import http.client
import json
import math
import re
import threading
import time
from collections import OrderedDict
from typing import Iterable

from ..config import SETTINGS
from ..utils.text_utils import sanitize_content

ALLOWED_EMBEDDING_SOURCE_TYPES = frozenset({"slide", "transcript"})
MAX_CONSENTED_PROJECTION_CHARS = 1200
PII_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE),
    re.compile(r"(?<!\w)(?:\+?84|0)(?:[\s().-]*\d){8,10}(?!\w)"),
    re.compile(r"(?<!\w)\d{9,12}(?!\w)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)


def normalize_dense(vector: Iterable[float]) -> list[float]:
    values = [float(value) for value in vector]
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude <= 0:
        return []
    return [value / magnitude for value in values]


def dense_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))


def _redact_projection_pii(value: str) -> tuple[str, int]:
    redacted = value
    matches = 0
    for pattern in PII_PATTERNS:
        redacted, count = pattern.subn("[REDACTED]", redacted)
        matches += count
    return redacted, matches


def _embedding_document_projection(document: dict) -> tuple[str, int]:
    """Build one consent-bounded projection and return its PII redaction count."""

    source_type = str(document.get("source_type") or document.get("type") or "").lower()
    if source_type not in ALLOWED_EMBEDDING_SOURCE_TYPES:
        raise ValueError("unsupported_embedding_source_type")
    if source_type == "slide" and (
        not document.get("file") or not isinstance(document.get("page"), int)
    ):
        raise ValueError("slide_embedding_requires_page")
    if source_type == "transcript" and (
        not document.get("chunk_id") or not document.get("parent_segment_id")
    ):
        raise ValueError("transcript_embedding_requires_subchunk")

    field_order = (
        ("title", "Title"),
        ("document_title", "Lesson"),
        ("lesson", "Lesson"),
        ("visual_summary", "Visual"),
        ("important_labels", "Labels"),
        ("relationships", "Relations"),
        ("context", "Content"),
    )
    parts: list[str] = []
    seen_values: set[str] = set()
    for key, label in field_order:
        field_value = sanitize_content(str(document.get(key, "")), max_chars=1200)
        normalized_value = " ".join(field_value.lower().split())
        if not normalized_value or normalized_value in seen_values:
            continue
        seen_values.add(normalized_value)
        parts.append(f"{label}: {field_value}")
    value = " | ".join(parts)
    value, redaction_count = _redact_projection_pii(value)
    max_chars = min(SETTINGS.rag_dense_max_chars, MAX_CONSENTED_PROJECTION_CHARS)
    return sanitize_content(value, max_chars=max_chars), redaction_count


def embedding_document_text(document: dict) -> str:
    """Return the smallest useful source projection for document indexing."""

    projection, _ = _embedding_document_projection(document)
    return projection


class OpenAIEmbeddingClient:
    """Small dependency-free embeddings client with connection reuse and cache."""

    def __init__(self) -> None:
        self.enabled = bool(SETTINGS.rag_dense_enabled and SETTINGS.openai_api_key)
        self.model = SETTINGS.rag_dense_model
        self.dimensions = SETTINGS.rag_dense_dimensions
        self.batch_size = SETTINGS.rag_dense_batch_size
        self.timeout = SETTINGS.rag_dense_timeout_seconds
        self._local = threading.local()
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self.last_error = ""
        self.request_count = 0
        self.cache_hits = 0
        self.last_index_audit: dict = {}

    def _connection(self) -> http.client.HTTPSConnection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = http.client.HTTPSConnection("api.openai.com", timeout=self.timeout)
            self._local.connection = connection
        return connection

    def _reset_connection(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        self._local.connection = None

    def _request(self, inputs: list[str]) -> list[list[float]]:
        if not self.enabled or not inputs:
            return []
        payload = json.dumps(
            {
                "model": self.model,
                "input": inputs,
                "dimensions": self.dimensions,
                "encoding_format": "float",
            },
            ensure_ascii=False,
        )
        headers = {
            "Authorization": f"Bearer {SETTINGS.openai_api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(6):
            try:
                connection = self._connection()
                connection.request("POST", "/v1/embeddings", body=payload.encode("utf-8"), headers=headers)
                response = connection.getresponse()
                raw = response.read()
                self.request_count += 1
                if response.status == 429 and attempt < 5:
                    try:
                        retry_after = float(response.getheader("retry-after") or 2 ** attempt)
                    except ValueError:
                        retry_after = float(2 ** attempt)
                    self._reset_connection()
                    time.sleep(max(0.5, min(30.0, retry_after)))
                    continue
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"embedding_http_{response.status}")
                parsed = json.loads(raw.decode("utf-8"))
                ordered = sorted(parsed.get("data", []), key=lambda item: int(item.get("index", 0)))
                vectors = [normalize_dense(item.get("embedding", [])) for item in ordered]
                if len(vectors) != len(inputs) or any(len(vector) != self.dimensions for vector in vectors):
                    raise ValueError("invalid_embedding_shape")
                self.last_error = ""
                return vectors
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError, http.client.HTTPException) as error:
                last_error = error
                self._reset_connection()
        self.last_error = type(last_error).__name__ if last_error else "embedding_failed"
        return []

    def embed_documents(self, documents: list[dict]) -> list[list[float]]:
        if not self.enabled:
            return []
        inputs: list[str] = []
        source_counts: dict[str, int] = {}
        pii_redactions = 0
        for document in documents:
            projection, redaction_count = _embedding_document_projection(document)
            if not projection:
                raise ValueError("empty_embedding_projection")
            source_type = str(document.get("source_type") or document.get("type")).lower()
            source_counts[source_type] = source_counts.get(source_type, 0) + 1
            pii_redactions += redaction_count
            inputs.append(projection)
        self.last_index_audit = {
            "document_count": len(inputs),
            "source_counts": source_counts,
            "max_projection_chars": max((len(value) for value in inputs), default=0),
            "pii_redactions": pii_redactions,
            "chatlog_documents": source_counts.get("chatlog", 0),
            "raw_transcript_documents": 0,
        }
        vectors: list[list[float]] = []
        for start in range(0, len(inputs), self.batch_size):
            batch = inputs[start : start + self.batch_size]
            embedded = self._request(batch)
            if len(embedded) != len(batch):
                raise RuntimeError("embedding_batch_failed")
            vectors.extend(embedded)
        return vectors

    def embed_query(self, query: str) -> list[float]:
        query = sanitize_content(query, max_chars=600)
        if not self.enabled or not query:
            return []
        with self._cache_lock:
            cached = self._cache.get(query)
            if cached is not None:
                self._cache.move_to_end(query)
                self.cache_hits += 1
                return cached
        vectors = self._request([query])
        if not vectors:
            return []
        vector = vectors[0]
        with self._cache_lock:
            self._cache[query] = vector
            self._cache.move_to_end(query)
            while len(self._cache) > 256:
                self._cache.popitem(last=False)
        return vector

    def public_status(self, *, document_vectors_ready: bool) -> dict:
        return {
            "configured": bool(SETTINGS.rag_dense_enabled),
            "active": bool(self.enabled and document_vectors_ready),
            "model": self.model if SETTINGS.rag_dense_enabled else "",
            "dimensions": self.dimensions if SETTINGS.rag_dense_enabled else 0,
            "query_cache_size": len(self._cache),
            "cache_hits": self.cache_hits,
            "request_count": self.request_count,
            "last_error": self.last_error,
            "payload_policy": {
                "allowed_source_types": sorted(ALLOWED_EMBEDDING_SOURCE_TYPES),
                "max_projection_chars": min(
                    SETTINGS.rag_dense_max_chars,
                    MAX_CONSENTED_PROJECTION_CHARS,
                ),
                "chatlog_allowed": False,
                "raw_transcript_allowed": False,
            },
            "last_index_audit": dict(self.last_index_audit),
        }


DENSE_CLIENT = OpenAIEmbeddingClient()
