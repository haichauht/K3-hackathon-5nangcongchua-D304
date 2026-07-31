"""Fast evidence-aware reranking over a small hybrid candidate set."""

from __future__ import annotations

from ..config import SETTINGS, SLIDE_EQUIVALENCE_BONUS


def source_key(item: dict) -> tuple[str, str, object]:
    source_type = str(item.get("source_type") or item.get("type") or "slide")
    if source_type == "slide":
        return source_type, str(item.get("file", "")), item.get("page")
    return source_type, str(item.get("parent_segment_id") or item.get("source_id") or ""), None


def rerank_candidates(candidates: list[dict], *, dense_active: bool, limit: int) -> list[dict]:
    """Fuse evidence signals and collapse transcript subchunks to their parent.

    When dense embeddings are active this is a neural bi-encoder reranker. It
    intentionally does not make a second LLM/cross-encoder call, keeping the
    interactive path fast and deterministic.
    """

    by_source: dict[tuple[str, str, object], dict] = {}
    for candidate in candidates:
        dense_score = float(candidate.get("dense_score", 0.0))
        token_coverage = float(candidate.get("token_coverage", 0.0))
        relevance = float(candidate.get("relevance_score", candidate.get("score", 0)))
        source_type = str(candidate.get("source_type") or candidate.get("type") or "slide")
        rank_score = relevance
        if dense_active:
            rank_score += max(0.0, dense_score - 0.30) * 34
        rank_score += min(1.0, token_coverage) * 6
        if source_type == "slide":
            rank_score += SLIDE_EQUIVALENCE_BONUS
        ranked = {
            **candidate,
            "_rank_score": round(rank_score, 4),
            "reranker_mode": (
                "dense_bi_encoder"
                if dense_active and SETTINGS.rag_rerank_enabled
                else "deterministic_evidence"
            ),
        }
        key = source_key(ranked)
        previous = by_source.get(key)
        if previous is None or ranked["_rank_score"] > previous["_rank_score"]:
            by_source[key] = ranked

    ranked = sorted(
        by_source.values(),
        key=lambda item: (
            item.get("_rank_score", 0),
            item.get("relevance_score", 0),
            item.get("dense_score", 0),
            item.get("lexical_score", 0),
        ),
        reverse=True,
    )
    if ranked and str(ranked[0].get("source_type") or ranked[0].get("type")) == "transcript":
        best_slide_index = next(
            (
                index
                for index, item in enumerate(ranked)
                if str(item.get("source_type") or item.get("type")) == "slide"
            ),
            None,
        )
        if best_slide_index is not None:
            top_relevance = float(ranked[0].get("relevance_score", 0))
            slide_relevance = float(ranked[best_slide_index].get("relevance_score", 0))
            if top_relevance - slide_relevance <= SLIDE_EQUIVALENCE_BONUS + 3:
                ranked.insert(0, ranked.pop(best_slide_index))
    return ranked[:limit]
