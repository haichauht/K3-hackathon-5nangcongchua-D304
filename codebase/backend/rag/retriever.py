"""Fast sparse+dense hybrid retrieval and index lifecycle."""

from __future__ import annotations

import math
import hashlib
import re
import threading
from collections import Counter

from ..config import (
    DENSE_MIN_SUPPORT_SCORE,
    DENSE_STRONG_SUPPORT_SCORE,
    DENSE_WEIGHT,
    LEXICAL_WEIGHT,
    MIN_OUT_OF_DOMAIN_COVERAGE,
    MIN_RETRIEVAL_SCORE,
    SEMANTIC_WEIGHT,
    SETTINGS,
    SLIDE_EQUIVALENCE_BONUS,
    VISION_CACHE_FILE,
)
from ..security.guardrails import (
    DIRECT_TOPIC_TERMS,
    GENERIC_RETRIEVAL_TERMS,
    LEARNING_CONTEXT_RE,
    MIN_SLIDE_SCORE,
    exact_source_anchor_terms,
    is_course_topic,
)
from ..utils.text_utils import remove_vietnamese_tone, tokenize
from .document_loader import build_runtime_documents
from .dense_retriever import DENSE_CLIENT, dense_cosine
from .index_manager import RagIndexManager
from .reranker import rerank_candidates
from . import document_loader, vision_processor

DATA_ROOT = SETTINGS.data_root
RAG_INDEX_DIR = SETTINGS.rag_index_dir
RAG_INDEX_MODE = SETTINGS.rag_index_mode
RAG_AUTO_REFRESH = SETTINGS.rag_auto_refresh
RAG_EMBEDDING_MODEL = SETTINGS.rag_embedding_model
RAG_CHUNKING_VERSION = SETTINGS.rag_chunking_version
RAG_NORMALIZATION_VERSION = SETTINGS.rag_normalization_version
RAG_INDEX_SCHEMA_VERSION = SETTINGS.rag_index_schema_version
RUNTIME_DOCUMENT_CACHE: list[dict] | None = None
SEMANTIC_INDEX_CACHE = None
RUNTIME_INDEX_STATUS: dict = {}
RAG_INDEX_MANAGER: RagIndexManager | None = None
INDEX_LOCK = threading.Lock()


class LocalTfidfIndex:
    """Sparse TF-IDF plus optional persisted dense document vectors."""

    def __init__(self, documents: list[dict], *, build_dense: bool = True) -> None:
        self.documents = documents
        self.idf: dict[str, float] = {}
        self.vectors: list[dict[str, float]] = []
        self.dense_model = DENSE_CLIENT.model
        self.dense_dimensions = DENSE_CLIENT.dimensions
        self.dense_vectors: list[list[float]] = []
        self._build()
        if build_dense:
            self.dense_vectors = DENSE_CLIENT.embed_documents(documents)

    @classmethod
    def from_serialized(cls, documents: list[dict], payload: dict) -> "LocalTfidfIndex":
        if payload.get("format_version") != 2:
            raise ValueError("unsupported vector index format")
        idf = payload.get("idf")
        vectors = payload.get("vectors")
        if not isinstance(idf, dict) or not isinstance(vectors, list) or len(vectors) != len(documents):
            raise ValueError("invalid serialized vector index")

        index = cls.__new__(cls)
        index.documents = documents
        index.idf = {str(key): float(value) for key, value in idf.items()}
        index.vectors = [
            {str(key): float(value) for key, value in vector.items()}
            for vector in vectors
            if isinstance(vector, dict)
        ]
        if len(index.vectors) != len(documents):
            raise ValueError("invalid serialized vector vectors")
        index.dense_model = str(payload.get("dense_model", ""))
        index.dense_dimensions = int(payload.get("dense_dimensions", 0) or 0)
        dense_vectors = payload.get("dense_vectors", [])
        if (
            isinstance(dense_vectors, list)
            and len(dense_vectors) == len(documents)
            and index.dense_model == DENSE_CLIENT.model
            and index.dense_dimensions == DENSE_CLIENT.dimensions
        ):
            index.dense_vectors = [
                [float(value) for value in vector]
                for vector in dense_vectors
                if isinstance(vector, list)
            ]
        else:
            index.dense_vectors = []
        if index.dense_vectors and any(
            len(vector) != index.dense_dimensions for vector in index.dense_vectors
        ):
            index.dense_vectors = []
        return index

    def to_serialized(self) -> dict:
        return {
            "format_version": 2,
            "idf": self.idf,
            "vectors": self.vectors,
            "dense_model": self.dense_model,
            "dense_dimensions": self.dense_dimensions,
            "dense_vectors": [
                [round(value, 7) for value in vector]
                for vector in self.dense_vectors
            ],
        }

    @property
    def dense_ready(self) -> bool:
        return bool(
            len(self.dense_vectors) == len(self.documents)
            and self.dense_vectors
            and all(len(vector) == self.dense_dimensions for vector in self.dense_vectors)
        )

    @staticmethod
    def features(value: str) -> Counter:
        normalized = remove_vietnamese_tone(value)
        words = tokenize(normalized)
        features = Counter(LocalTfidfIndex.opaque_feature("w", word) for word in words)
        compact = re.sub(r"[^a-z0-9]+", " ", normalized)
        for word in compact.split():
            if len(word) < 3:
                continue
            for index in range(len(word) - 2):
                features[LocalTfidfIndex.opaque_feature("c", word[index:index + 3])] += 0.35
        return features

    @staticmethod
    def opaque_feature(kind: str, value: str) -> str:
        digest = hashlib.sha256(f"{kind}:{value}".encode("utf-8")).hexdigest()[:20]
        return f"h:{digest}"

    def _build(self) -> None:
        document_features = [
            self.features(str(item.get("_search_text") or document_search_text(item)))
            for item in self.documents
        ]
        document_frequency = Counter()
        for features in document_features:
            document_frequency.update(features.keys())

        count = max(len(self.documents), 1)
        self.idf = {
            feature: math.log((count + 1) / (frequency + 1)) + 1
            for feature, frequency in document_frequency.items()
        }

        for features in document_features:
            vector = {
                feature: math.log1p(value) * self.idf.get(feature, 1)
                for feature, value in features.items()
                if value > 0
            }
            self.vectors.append(normalize_vector(vector))

    def search_sparse(self, query: str) -> list[float]:
        features = self.features(query)
        if not features:
            return [0.0] * len(self.documents)

        query_vector = normalize_vector(
            {
                feature: math.log1p(value) * self.idf.get(feature, 1)
                for feature, value in features.items()
                if value > 0
            }
        )
        return [cosine_similarity(query_vector, vector) for vector in self.vectors]

    def search_dense(self, query: str) -> list[float]:
        if not self.dense_ready or not DENSE_CLIENT.enabled:
            return [0.0] * len(self.documents)
        query_vector = DENSE_CLIENT.embed_query(query)
        if not query_vector:
            return [0.0] * len(self.documents)
        return [dense_cosine(query_vector, vector) for vector in self.dense_vectors]

    def search(self, query: str) -> list[float]:
        """Compatibility alias: this score is sparse and never called semantic."""
        return self.search_sparse(query)


def normalize_vector(vector: dict[str, float]) -> dict[str, float]:
    magnitude = math.sqrt(sum(value * value for value in vector.values()))
    if magnitude <= 0:
        return {}
    return {key: value / magnitude for key, value in vector.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return max(0.0, min(1.0, sum(value * right.get(key, 0.0) for key, value in left.items())))


def document_search_text(document: dict) -> str:
    return " ".join(
        str(document.get(key, ""))
        for key in (
            "title",
            "document_title",
            "lesson",
            "source_id",
            "text",
            "context",
            "visual_summary",
            "important_labels",
            "relationships",
        )
    )


def prepare_runtime_documents(documents: list[dict]) -> list[dict]:
    """Cache normalized fields once instead of reprocessing every source/query."""

    for document in documents:
        search_text = document_search_text(document)
        normalized_search = remove_vietnamese_tone(search_text.lower())
        title_text = " ".join(
            str(document.get(key, ""))
            for key in ("title", "document_title", "lesson", "source_id")
        )
        normalized_title = remove_vietnamese_tone(title_text.lower())
        context_text = str(document.get("text") or document.get("context", ""))
        normalized_context = remove_vietnamese_tone(context_text.lower())
        document["_search_text"] = search_text
        document["_normalized_title"] = normalized_title
        document["_search_tokens"] = frozenset(re.findall(r"[a-z0-9]+", normalized_search))
        document["_title_tokens"] = frozenset(re.findall(r"[a-z0-9]+", normalized_title))
        document["_context_tokens"] = frozenset(re.findall(r"[a-z0-9]+", normalized_context))
        document["_title_counts"] = Counter(re.findall(r"[a-z0-9]+", normalized_title))
        document["_context_counts"] = Counter(re.findall(r"[a-z0-9]+", normalized_context))
        document["_anchor_terms"] = exact_source_anchor_terms(context_text)
    return documents


def weighted_token_score(counts: Counter, query_tokens: list[str]) -> int:
    score = 0
    for token in query_tokens:
        count = counts.get(token, 0)
        if not count:
            continue
        weight = 1 if token in GENERIC_RETRIEVAL_TERMS else 3
        score += min(count, 3) * weight
    return score


def get_rag_index_manager() -> RagIndexManager:
    global RAG_INDEX_MANAGER
    if RAG_INDEX_MANAGER is None:
        RAG_INDEX_MANAGER = RagIndexManager(
            data_root=DATA_ROOT,
            index_dir=RAG_INDEX_DIR,
            mode=RAG_INDEX_MODE,
            auto_refresh=RAG_AUTO_REFRESH,
            embedding_model=RAG_EMBEDDING_MODEL,
            chunking_version=RAG_CHUNKING_VERSION,
            normalization_version=RAG_NORMALIZATION_VERSION,
            index_schema_version=RAG_INDEX_SCHEMA_VERSION,
        )
    return RAG_INDEX_MANAGER


def runtime_document_id(document: dict) -> str:
    value = document.get("document_id")
    if value:
        return str(value)
    source_type = document.get("source_type") or document.get("type") or "source"
    return f"{source_type}:{document.get('source_id') or document.get('source') or ''}"


def topic_signal_bonus(topic_hint: str, page: dict) -> int:
    normalized = remove_vietnamese_tone(topic_hint.lower())
    title_tokens = page.get("_title_tokens") or set(
        tokenize(f"{page.get('title', '')} {page.get('lesson', '')}")
    )
    context_tokens = page.get("_context_tokens") or set(tokenize(page.get("context", "")))

    def bonus_for(anchors: tuple[str, ...], step: int = 8) -> int:
        title_matches = sum(1 for anchor in anchors if anchor in title_tokens)
        context_matches = sum(1 for anchor in anchors if anchor in context_tokens)
        return title_matches * (step + 4) + min(context_matches, 2) * step

    if re.search(r"\b(?:rag|citation|grounding|hallucination)\b", normalized):
        return bonus_for(("rag", "citation", "grounding", "hallucination"), step=10)
    if re.search(r"\b(?:roi|return on investment)\b", topic_hint.lower()):
        return bonus_for(("baseline", "measurement", "target", "evaluation", "cost", "impact"), step=6)
    if re.search(r"\b(?:quick win|impact effort|effort impact)\b", normalized):
        return bonus_for(("impact", "effort", "priority", "use", "case"), step=10)
    if re.search(r"\b(?:mvp|poc|prototype)\b", normalized):
        return bonus_for(("problem", "scope", "prototype", "evaluation", "go", "not", "yet"), step=5)
    if re.search(r"(?:khong nen dua ai|not put ai|should not use ai)", normalized):
        return bonus_for(("automate", "augment", "risk", "controls", "not", "yet"), step=8)
    return 0


def lexical_document_score(document: dict, query_tokens: list[str], topic_hint: str = "") -> int:
    title_text = " ".join(
        str(document.get(key, "")) for key in ("title", "document_title", "lesson", "source_id")
    )
    title_multiplier = 4 if document.get("type") == "slide" else 2
    title_counts = document.get("_title_counts")
    context_counts = document.get("_context_counts")
    if title_counts is None:
        title_counts = Counter(re.findall(r"[a-z0-9]+", remove_vietnamese_tone(title_text.lower())))
    if context_counts is None:
        context_text = str(document.get("text") or document.get("context", ""))
        context_counts = Counter(re.findall(r"[a-z0-9]+", remove_vietnamese_tone(context_text.lower())))
    title_score = weighted_token_score(title_counts, query_tokens) * title_multiplier
    context_score = weighted_token_score(context_counts, query_tokens)
    normalized_query = " ".join(query_tokens)
    normalized_title = str(document.get("_normalized_title") or remove_vietnamese_tone(title_text.lower()))
    phrase_bonus = 8 if len(query_tokens) >= 2 and normalized_query in normalized_title else 0
    topic_bonus = topic_signal_bonus(topic_hint, document) if document.get("type") == "slide" else 0
    return title_score + context_score + phrase_bonus + topic_bonus


def relevance_signals(
    document: dict,
    absolute_query: str,
    expanded_query: str,
    topic_hint: str,
    lexical_score: int,
    sparse_score: float,
    dense_score: float,
    dense_active: bool,
) -> dict:
    """Measure absolute support instead of trusting whichever document ranks first.

    Sparse TF-IDF can always produce a top result, even for an unrelated query.
    This gate therefore requires observable token support in the source itself.
    Course-topic expansions are only used when the user's direct query is too
    generic to carry a useful anchor.
    """

    direct_tokens = list(dict.fromkeys(tokenize(absolute_query)))
    direct_topic_tokens = [token for token in direct_tokens if token in DIRECT_TOPIC_TERMS]
    distinctive_tokens = [token for token in direct_tokens if token not in GENERIC_RETRIEVAL_TERMS]
    if direct_topic_tokens:
        signal_tokens = direct_topic_tokens
    elif distinctive_tokens:
        signal_tokens = distinctive_tokens
    elif is_course_topic(topic_hint):
        signal_tokens = [
            token
            for token in dict.fromkeys(tokenize(expanded_query))
            if token not in GENERIC_RETRIEVAL_TERMS
        ][:8]
    else:
        signal_tokens = direct_tokens

    document_text = str(document.get("text") or document.get("context") or "")
    document_tokens = document.get("_search_tokens") or set(tokenize(document_search_text(document)))
    required_anchors = exact_source_anchor_terms(absolute_query)
    document_anchors = document.get("_anchor_terms")
    if document_anchors is None:
        document_anchors = exact_source_anchor_terms(document_text)
    matched_anchors = required_anchors & document_anchors
    matched_tokens = [
        token
        for token in signal_tokens
        if token in document_tokens
        and (token not in required_anchors or token in matched_anchors)
    ]
    token_count = len(signal_tokens)
    coverage = len(matched_tokens) / token_count if token_count else 0.0
    course_context = bool(is_course_topic(topic_hint) or LEARNING_CONTEXT_RE.search(topic_hint))

    dense_support = bool(dense_active and dense_score >= DENSE_MIN_SUPPORT_SCORE)
    strong_dense_support = bool(dense_active and dense_score >= DENSE_STRONG_SUPPORT_SCORE)
    supported = bool(matched_tokens or strong_dense_support)
    if required_anchors and not matched_anchors:
        supported = False
    if token_count >= 4 and len(matched_tokens) < 2 and coverage < 0.50:
        supported = strong_dense_support
    if not course_context and token_count >= 3:
        lexical_support = len(matched_tokens) >= 2 and coverage >= MIN_OUT_OF_DOMAIN_COVERAGE
        supported = supported and (lexical_support or strong_dense_support)
    if lexical_score <= 0 and sparse_score < 0.18 and not dense_support:
        supported = False

    lexical_strength = min(lexical_score / 36, 1.0)
    sparse_strength = min(sparse_score / 0.25, 1.0)
    lexical_absolute = round(
        100
        * (
            0.50 * coverage
            + 0.32 * lexical_strength
            + 0.18 * sparse_strength
        )
    )
    dense_strength = max(0.0, min(1.0, (dense_score - 0.25) / 0.35)) if dense_active else 0.0
    dense_absolute = round(100 * dense_strength) if dense_support else 0
    absolute_score = max(lexical_absolute, dense_absolute)
    if course_context and matched_tokens:
        absolute_score = min(100, absolute_score + 5)

    return {
        "supported": supported and absolute_score >= MIN_RETRIEVAL_SCORE,
        "absolute_score": absolute_score,
        "query_token_count": token_count,
        "matched_token_count": len(matched_tokens),
        "token_coverage": round(coverage, 4),
        "matched_tokens": matched_tokens[:8],
        "required_anchors": sorted(required_anchors),
        "matched_anchors": sorted(matched_anchors),
        "dense_supported": dense_support,
    }


def search_hybrid_sources(
    query: str,
    limit: int = 6,
    topic_hint: str = "",
    source_types: set[str] | None = None,
    absolute_query: str = "",
) -> list[dict]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    documents, vector_index = ensure_runtime_index()
    sparse_scores = vector_index.search_sparse(query)
    required_anchors = exact_source_anchor_terms(absolute_query or query)

    lexical_rows: list[tuple[int, int, int]] = []
    for index, document in enumerate(documents):
        if source_types and document.get("type") not in source_types:
            continue
        document_anchors = document.get("_anchor_terms") or set()
        if required_anchors and not (required_anchors & document_anchors):
            continue
        lexical_score = lexical_document_score(document, query_tokens, topic_hint=topic_hint)
        direct_topic_score = weighted_token_score(
            document.get("_context_counts", Counter()),
            [token for token in query_tokens if token in DIRECT_TOPIC_TERMS],
        )
        lexical_rows.append((index, lexical_score, direct_topic_score))

    best_lexical = max((row[1] for row in lexical_rows), default=0)
    best_sparse = max((sparse_scores[row[0]] for row in lexical_rows), default=0.0)
    dense_would_help = best_lexical < 18 or best_sparse < 0.12
    dense_active = bool(
        SETTINGS.rag_dense_enabled
        and vector_index.dense_ready
        and DENSE_CLIENT.enabled
        and dense_would_help
    )
    dense_query = absolute_query or topic_hint or query
    dense_scores = (
        vector_index.search_dense(dense_query)
        if dense_active
        else [0.0] * len(documents)
    )

    candidates = []
    for index, lexical_score, direct_topic_score in lexical_rows:
        document = documents[index]
        sparse_score = sparse_scores[index]
        dense_score = dense_scores[index]
        if lexical_score <= 0 and sparse_score < 0.08 and dense_score < DENSE_MIN_SUPPORT_SCORE:
            continue
        if (
            lexical_score < MIN_SLIDE_SCORE
            and direct_topic_score < 6
            and sparse_score < 0.14
            and dense_score < DENSE_MIN_SUPPORT_SCORE
        ):
            continue

        lexical_component = min(lexical_score / 36, 1.0)
        sparse_component = min(sparse_score / 0.25, 1.0)
        dense_component = max(0.0, min(1.0, (dense_score - 0.25) / 0.35))
        if dense_active:
            remaining = 1 - DENSE_WEIGHT
            hybrid_score = round(
                100
                * (
                    remaining * LEXICAL_WEIGHT * lexical_component
                    + remaining * SEMANTIC_WEIGHT * sparse_component
                    + DENSE_WEIGHT * dense_component
                )
            )
        else:
            hybrid_score = round(
                100
                * (
                    LEXICAL_WEIGHT * lexical_component
                    + SEMANTIC_WEIGHT * sparse_component
                )
            )
        signals = relevance_signals(
            document,
            absolute_query=absolute_query or query,
            expanded_query=query,
            topic_hint=topic_hint,
            lexical_score=lexical_score,
            sparse_score=sparse_score,
            dense_score=dense_score,
            dense_active=dense_active,
        )
        if not signals["supported"]:
            continue
        relevance_score = round(0.45 * hybrid_score + 0.55 * signals["absolute_score"])
        if relevance_score < MIN_RETRIEVAL_SCORE:
            continue
        candidates.append(
            {
                **document,
                "score": relevance_score,
                "relevance_score": relevance_score,
                "lexical_score": lexical_score,
                "sparse_score": round(sparse_score, 4),
                "dense_score": round(dense_score, 4) if dense_active else 0.0,
                "semantic_backend": (
                    DENSE_CLIENT.model if dense_active else "disabled_fast_path"
                ),
                "token_coverage": signals["token_coverage"],
                "matched_token_count": signals["matched_token_count"],
                "query_token_count": signals["query_token_count"],
            }
        )

    return rerank_candidates(
        candidates,
        dense_active=dense_active and SETTINGS.rag_rerank_enabled,
        limit=limit,
    )


def search_slide_pages(query: str, limit: int = 3, topic_hint: str = "") -> list[dict]:
    return search_hybrid_sources(
        query,
        limit=limit,
        topic_hint=topic_hint,
        source_types={"slide"},
        absolute_query=query,
    )


def ensure_runtime_index(force_rebuild: bool = False) -> tuple[list[dict], LocalTfidfIndex]:
    global RUNTIME_DOCUMENT_CACHE, SEMANTIC_INDEX_CACHE, RUNTIME_INDEX_STATUS
    if RUNTIME_DOCUMENT_CACHE is not None and SEMANTIC_INDEX_CACHE is not None and not force_rebuild:
        return RUNTIME_DOCUMENT_CACHE, SEMANTIC_INDEX_CACHE
    with INDEX_LOCK:
        if force_rebuild:
            document_loader.reset_document_caches()
            vision_processor.reset_vision_state(retry_errors=True)
            RUNTIME_DOCUMENT_CACHE = None
            SEMANTIC_INDEX_CACHE = None
        if RUNTIME_DOCUMENT_CACHE is None:
            RUNTIME_DOCUMENT_CACHE = prepare_runtime_documents(build_runtime_documents())
        if SEMANTIC_INDEX_CACHE is None:
            SEMANTIC_INDEX_CACHE, RUNTIME_INDEX_STATUS = get_rag_index_manager().load_or_build(
                documents=RUNTIME_DOCUMENT_CACHE,
                build_index=lambda documents: LocalTfidfIndex(
                    documents,
                    build_dense=DENSE_CLIENT.enabled,
                ),
                serialize_index=lambda index: index.to_serialized(),
                deserialize_index=LocalTfidfIndex.from_serialized,
                document_id_fn=runtime_document_id,
                force_rebuild=force_rebuild or vision_processor.VISION_CACHE_CHANGED,
                extra_files={VISION_CACHE_FILE: vision_processor.vision_cache_payload()},
            )
            # Server startup must never turn into a bulk external embedding job.
            # If persisted dense vectors are absent, retrieval remains sparse
            # until an operator explicitly runs `python rag_index.py build --force`.
            RUNTIME_INDEX_STATUS["vision"] = {
                "enabled": vision_processor.RAG_VISION_ENABLED,
                "model": vision_processor.RAG_VISION_MODEL,
                **vision_processor.VISION_STATS,
            }
            RUNTIME_INDEX_STATUS["dense"] = DENSE_CLIENT.public_status(
                document_vectors_ready=SEMANTIC_INDEX_CACHE.dense_ready,
            )
            RUNTIME_INDEX_STATUS["reranker"] = {
                "configured": SETTINGS.rag_rerank_enabled,
                "mode": (
                    "dense_bi_encoder"
                    if SETTINGS.rag_rerank_enabled and SEMANTIC_INDEX_CACHE.dense_ready
                    else "deterministic_evidence"
                ),
                "extra_model_call_per_query": False,
            }
    return RUNTIME_DOCUMENT_CACHE, SEMANTIC_INDEX_CACHE


def rag_index_status() -> dict:
    if RUNTIME_DOCUMENT_CACHE is not None and RUNTIME_INDEX_STATUS:
        return dict(RUNTIME_INDEX_STATUS)
    return get_rag_index_manager().public_status()


def rag_index_build(force_rebuild: bool = False) -> dict:
    ensure_runtime_index(force_rebuild=force_rebuild)
    return dict(RUNTIME_INDEX_STATUS)
