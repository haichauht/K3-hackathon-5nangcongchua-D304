"""Environment and filesystem configuration for VLearn Recall."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .rag.index_manager import parse_bool


CODEBASE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = CODEBASE_ROOT.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Settings:
    codebase_root: Path
    repository_root: Path
    data_root: Path
    slides_root: Path
    transcript_root: Path
    host: str
    port: int
    cors_origins: tuple[str, ...]
    openai_api_key: str
    openai_model: str
    openai_answer_timeout_seconds: int
    openai_reasoning_effort: str
    openai_max_output_tokens: int
    rag_index_mode: str
    rag_auto_refresh: bool
    rag_index_dir: Path
    rag_embedding_model: str
    rag_dense_enabled: bool
    rag_dense_model: str
    rag_dense_dimensions: int
    rag_dense_batch_size: int
    rag_dense_timeout_seconds: int
    rag_dense_max_chars: int
    rag_rerank_enabled: bool
    rag_chunking_version: str
    rag_normalization_version: str
    rag_index_schema_version: str
    rag_vision_enabled: bool
    rag_vision_model: str
    rag_vision_max_text_chars: int
    rag_vision_render_scale: float
    rag_vision_timeout_seconds: int


def load_settings() -> Settings:
    load_env_file(CODEBASE_ROOT / ".env")
    data_root = (REPOSITORY_ROOT / "data" / "vlearn-pack").resolve()
    index_value = Path(os.environ.get("RAG_INDEX_DIR", "data/.rag-index"))
    index_dir = (
        (REPOSITORY_ROOT / index_value).resolve()
        if not index_value.is_absolute()
        else index_value.resolve()
    )
    mode = os.environ.get("RAG_INDEX_MODE", "persistent").strip().lower()
    if mode not in {"persistent", "memory"}:
        mode = "persistent"
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key.startswith("your_"):
        api_key = ""
    cors_origins = tuple(
        origin.strip().rstrip("/")
        for origin in os.environ.get(
            "VLEARN_CORS_ORIGINS",
            "null,http://127.0.0.1:8011,http://localhost:8011",
        ).split(",")
        if origin.strip()
    )
    dense_enabled = parse_bool(os.environ.get("RAG_DENSE_ENABLED"), default=False)
    dense_model = os.environ.get("RAG_DENSE_MODEL", "text-embedding-3-small")
    embedding_label = os.environ.get("RAG_EMBEDDING_MODEL", "auto").strip()
    if not embedding_label or embedding_label.lower() == "auto":
        embedding_label = (
            f"hybrid-local-tfidf-char3+{dense_model}"
            if dense_enabled
            else "local-tfidf-char3-v2"
        )
    return Settings(
        codebase_root=CODEBASE_ROOT,
        repository_root=REPOSITORY_ROOT,
        data_root=data_root,
        slides_root=data_root / "slides",
        transcript_root=data_root / "transcript",
        host=os.environ.get("VLEARN_RECALL_HOST", "127.0.0.1"),
        port=int(os.environ.get("VLEARN_RECALL_PORT", "8011")),
        cors_origins=cors_origins,
        openai_api_key=api_key,
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-5"),
        openai_answer_timeout_seconds=max(
            3,
            int(os.environ.get("OPENAI_ANSWER_TIMEOUT_SECONDS", "12")),
        ),
        openai_reasoning_effort=(
            os.environ.get("OPENAI_REASONING_EFFORT", "minimal").strip().lower()
            if os.environ.get("OPENAI_REASONING_EFFORT", "minimal").strip().lower()
            in {"none", "minimal", "low", "medium", "high"}
            else "minimal"
        ),
        openai_max_output_tokens=max(
            300,
            min(2000, int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "700"))),
        ),
        rag_index_mode=mode,
        rag_auto_refresh=parse_bool(os.environ.get("RAG_AUTO_REFRESH"), default=True),
        rag_index_dir=index_dir,
        rag_embedding_model=embedding_label,
        # Dense indexing sends bounded source projections to an external API.
        # Keep it explicit opt-in; an API key alone is not data-egress consent.
        rag_dense_enabled=dense_enabled,
        rag_dense_model=dense_model,
        rag_dense_dimensions=max(64, min(1536, int(os.environ.get("RAG_DENSE_DIMENSIONS", "256")))),
        rag_dense_batch_size=max(1, min(128, int(os.environ.get("RAG_DENSE_BATCH_SIZE", "64")))),
        rag_dense_timeout_seconds=max(3, int(os.environ.get("RAG_DENSE_TIMEOUT_SECONDS", "30"))),
        # External egress consent is bounded to 1,200 characters per source
        # projection. Environment configuration may lower, but never raise it.
        rag_dense_max_chars=max(300, min(1200, int(os.environ.get("RAG_DENSE_MAX_CHARS", "1200")))),
        rag_rerank_enabled=parse_bool(os.environ.get("RAG_RERANK_ENABLED"), default=True),
        rag_chunking_version="transcript-parent-subchunk-180-30-v2",
        rag_normalization_version="nfkc-tone-v4",
        rag_index_schema_version="rag-index-v4",
        rag_vision_enabled=parse_bool(os.environ.get("RAG_VISION_ENABLED"), default=True),
        rag_vision_model="gpt-5",
        rag_vision_max_text_chars=int(os.environ.get("RAG_VISION_MAX_TEXT_CHARS", "280")),
        rag_vision_render_scale=float(os.environ.get("RAG_VISION_RENDER_SCALE", "2.0")),
        rag_vision_timeout_seconds=int(os.environ.get("RAG_VISION_TIMEOUT_SECONDS", "60")),
    )


SETTINGS = load_settings()
PUBLIC_PREVIEW_CHARS = 220
TRANSCRIPT_VIEW_CHARS = 1800
MIN_RETRIEVAL_SCORE = 24
MIN_FOUND_SCORE = 40
LOCATE_RESULT_SCORE_GAP = 12
MIN_OUT_OF_DOMAIN_COVERAGE = 0.50
SLIDE_EQUIVALENCE_BONUS = 5
SEMANTIC_WEIGHT = 0.38
LEXICAL_WEIGHT = 1 - SEMANTIC_WEIGHT
DENSE_WEIGHT = 0.42
DENSE_MIN_SUPPORT_SCORE = 0.40
DENSE_STRONG_SUPPORT_SCORE = 0.48
TRANSCRIPT_CHUNK_TARGET_WORDS = 180
TRANSCRIPT_CHUNK_MAX_WORDS = 220
TRANSCRIPT_CHUNK_OVERLAP_WORDS = 30
VISION_CACHE_FILE = "vision_cache.json"
VISION_PROMPT = """You inspect exactly one lecture slide image for a grounded retrieval index.
Return only the requested JSON object. Describe only what is visibly supported by the image.
Do not guess unreadable text, hidden content, exact numeric values, identities, or relationships
that are not visually clear. Put every unclear or uncertain observation in uncertain_details.
Use empty strings or empty arrays when a field is not visible. Do not create citations, file names,
page numbers, URLs, or information from outside this image.

Extract:
- title: the visible slide title, if readable
- visual_summary: a concise description of the visible diagram, chart, layout, or image
- important_labels: readable labels, axes, legend entries, or node names
- relationships: only clearly visible arrows, sequence, grouping, comparison, or direction
- uncertain_details: anything too small, obscured, ambiguous, or not confidently readable
"""
VISION_PROMPT_HASH = hashlib.sha256(VISION_PROMPT.encode("utf-8")).hexdigest()
VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "visual_summary": {"type": "string"},
        "important_labels": {"type": "array", "items": {"type": "string"}},
        "relationships": {"type": "array", "items": {"type": "string"}},
        "uncertain_details": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "visual_summary", "important_labels", "relationships", "uncertain_details"],
    "additionalProperties": False,
}
