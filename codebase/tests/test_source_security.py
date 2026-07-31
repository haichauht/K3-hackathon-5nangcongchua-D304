from __future__ import annotations

import json
import os
import unittest

os.environ["OPENAI_API_KEY"] = ""

from backend.config import TRANSCRIPT_VIEW_CHARS  # noqa: E402
from backend.rag.retriever import ensure_runtime_index  # noqa: E402
from backend.services.source_service import (  # noqa: E402
    resolve_slide_file,
    transcript_segment_payload,
)


class SourceSecurityTests(unittest.TestCase):
    def test_slide_path_cannot_escape_data_directory(self) -> None:
        self.assertIsNone(resolve_slide_file("../.env"))
        self.assertIsNone(resolve_slide_file(r"..\transcript\transcript-01-clean.md"))
        self.assertIsNotNone(resolve_slide_file("d1-slide-hackathon.pdf"))

    def test_transcript_viewer_is_bounded_and_does_not_expose_paths(self) -> None:
        payload = transcript_segment_payload("[T01-001]")
        self.assertIsNotNone(payload)
        self.assertLessEqual(len(payload["content"]), TRANSCRIPT_VIEW_CHARS)
        serialized = json.dumps(payload, ensure_ascii=False).lower()
        self.assertNotIn("absolute", serialized)
        self.assertNotIn("transcript-01-clean.md", serialized)

    def test_chatlog_never_enters_retrieval_documents(self) -> None:
        documents, _ = ensure_runtime_index()
        self.assertFalse(
            any(item.get("source_type") == "chatlog" for item in documents)
        )


if __name__ == "__main__":
    unittest.main()
