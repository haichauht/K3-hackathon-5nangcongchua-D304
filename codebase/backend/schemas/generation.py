"""Structured generation contracts returned by the OpenAI Responses API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictGenerationModel(BaseModel):
    """Reject fields that are not part of the frontend/backend contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GroundedPoint(StrictGenerationModel):
    text: str = Field(min_length=8, max_length=360)
    source_indexes: list[int] = Field(min_length=1, max_length=3)


class LearningAnswer(StrictGenerationModel):
    kind: Literal["learning_answer"]
    title: str = Field(min_length=3, max_length=120)
    answer: str = Field(min_length=12, max_length=700)
    key_points: list[GroundedPoint] = Field(min_length=1, max_length=4)
    used_source_indexes: list[int] = Field(min_length=1, max_length=3)


class SlideSummary(StrictGenerationModel):
    kind: Literal["slide_summary"]
    title: str = Field(min_length=3, max_length=120)
    main_idea: str = Field(min_length=12, max_length=420)
    key_points: list[GroundedPoint] = Field(min_length=2, max_length=4)
    takeaway: str = Field(min_length=12, max_length=320)
    used_source_indexes: list[int] = Field(min_length=1, max_length=1)


class SynthesisTheme(StrictGenerationModel):
    heading: str = Field(min_length=3, max_length=100)
    summary: str = Field(min_length=12, max_length=420)
    source_indexes: list[int] = Field(min_length=1, max_length=3)


class MultiSlideSynthesis(StrictGenerationModel):
    kind: Literal["multi_slide_synthesis"]
    topic: str = Field(min_length=3, max_length=120)
    overview: str = Field(min_length=12, max_length=420)
    themes: list[SynthesisTheme] = Field(min_length=1, max_length=5)
    connections: str = Field(min_length=12, max_length=420)
    used_source_indexes: list[int] = Field(min_length=1, max_length=3)


class ComparisonItem(StrictGenerationModel):
    aspect: str = Field(min_length=3, max_length=100)
    similarity: str = Field(min_length=8, max_length=320)
    difference: str = Field(min_length=8, max_length=320)
    source_indexes: list[int] = Field(min_length=2, max_length=3)


class SlideComparison(StrictGenerationModel):
    """Kept as an internal contract; the removed compare UI is not reintroduced."""

    kind: Literal["slide_comparison"]
    title: str = Field(min_length=3, max_length=120)
    overview: str = Field(min_length=12, max_length=360)
    comparisons: list[ComparisonItem] = Field(min_length=1, max_length=4)
    used_source_indexes: list[int] = Field(min_length=2, max_length=3)


class SelfCheckQuestion(StrictGenerationModel):
    question: str = Field(min_length=8, max_length=280)
    source_indexes: list[int] = Field(min_length=1, max_length=3)


class SelfCheck(StrictGenerationModel):
    kind: Literal["self_check"]
    title: str = Field(min_length=3, max_length=120)
    instructions: str = Field(min_length=8, max_length=220)
    questions: list[SelfCheckQuestion] = Field(min_length=1, max_length=3)
    used_source_indexes: list[int] = Field(min_length=1, max_length=3)


TASK_SCHEMAS: dict[str, type[StrictGenerationModel]] = {
    "answer": LearningAnswer,
    "summarize_first": SlideSummary,
    "synthesize_sources": MultiSlideSynthesis,
    "compare_sources": SlideComparison,
    "self_check": SelfCheck,
}


__all__ = [
    "GroundedPoint",
    "LearningAnswer",
    "MultiSlideSynthesis",
    "SelfCheck",
    "SlideComparison",
    "SlideSummary",
    "SynthesisTheme",
    "TASK_SCHEMAS",
]
