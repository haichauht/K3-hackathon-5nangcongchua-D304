from __future__ import annotations

import os
import re
import unittest

os.environ["OPENAI_API_KEY"] = ""

from backend import runtime as server  # noqa: E402


class RecallWorkflowTests(unittest.TestCase):
    def test_course_typos_and_mixed_language_are_normalized_before_retrieval(self) -> None:
        typo = server.search_recall("có nói ploblem statemant ở đâu ấy nhỉ")
        mixed = server.search_recall(
            "phần problem statement nằm ở slide nào vậy"
        )

        for result in (typo, mixed):
            self.assertEqual(result["status"], "FOUND")
            self.assertEqual(result["intent"]["type"], "LOCATE_SLIDE")
            self.assertEqual(
                [source["page"] for source in result["results"][:2]],
                [26, 27],
            )
            self.assertTrue(
                all(source["source_type"] == "slide" for source in result["results"])
            )

        self.assertEqual(typo["query"], "problem statement")

    def test_course_typo_correction_does_not_pull_unrelated_queries_in_domain(self) -> None:
        result = server.search_recall(
            "ploblem statemant about growing orchids all year"
        )
        self.assertEqual(result["status"], "NOT_FOUND")
        self.assertEqual(result["results"], [])

    def test_slide_cards_use_visual_title_and_nonduplicated_preview(self) -> None:
        pages = {
            item["page"]: item
            for item in server.load_slide_pages()
            if item.get("file") == "d2-slide-hackathon.pdf"
            and item.get("page") in {3, 4}
        }

        self.assertEqual(
            pages[3]["title"],
            "Tìm đúng vấn đề trước khi tìm giải pháp",
        )
        self.assertEqual(pages[4]["title"], "Diamond 1 — Tìm đúng vấn đề")
        self.assertTrue(pages[3]["preview"].startswith("Discover:"))
        self.assertTrue(pages[4]["preview"].startswith("Khám phá / mở rộng góc nhìn"))
        self.assertNotIn("D I A M O N D", pages[3]["preview"])
        self.assertNotIn("D I S C OV E R", pages[4]["preview"])

    def test_locate_slide_returns_only_strong_slide_cards(self) -> None:
        result = server.search_recall("Slide nào nói về AI Agent?")

        self.assertEqual(result["status"], "FOUND")
        self.assertEqual(result["intent"]["type"], "LOCATE_SLIDE")
        self.assertEqual([item["page"] for item in result["results"]], [23, 24])
        self.assertTrue(all(item["source_type"] == "slide" for item in result["results"]))
        self.assertFalse(
            any("Discriminative AI" in item["title"] for item in result["results"])
        )
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["source_map"], [])
        self.assertNotIn("[[", result["answer"])

    def test_distant_context_paraphrase_prefers_the_supported_slide(self) -> None:
        result = server.search_recall(
            "Why can irrelevant context make a language model overlook "
            "the most important instruction?"
        )

        self.assertEqual(result["status"], "FOUND")
        self.assertEqual(
            result["results"][0]["source_id"],
            "d1-slide-hackathon.pdf#page=16",
        )
        self.assertEqual(result["results"][0]["source_type"], "slide")

    def test_unrelated_queries_are_not_found(self) -> None:
        questions = [
            "satellite marine fish farming technique",
            "how to grow orchids all year",
            "cách trồng hoa lan quanh năm",
            "optimize a diesel ship engine",
            "calculate the orbit of a weather satellite",
            "how to mix interior wall paint colors",
            "coffee fermentation process for dark roast",
        ]
        for question in questions:
            with self.subTest(question=question):
                self.assertEqual(server.search_recall(question)["status"], "NOT_FOUND")

    def test_roi_acronym_does_not_match_vietnamese_tone_folding(self) -> None:
        self.assertEqual(server.exact_source_anchor_terms("rồi rơi"), set())
        self.assertEqual(server.exact_source_anchor_terms("ROI model"), {"roi"})
        result = server.search_recall(
            "ROI model 3-6-12 tháng phải tính kiểu nào để không pitch sai?"
        )
        self.assertEqual(result["status"], "NOT_FOUND")
        self.assertEqual(result["results"], [])

    def test_found_sources_follow_normalized_contract(self) -> None:
        result = server.search_recall("Thay co noi use case voi AI Agent o dau ay")
        self.assertEqual(result["status"], "FOUND")
        self.assertLessEqual(len(result["results"]), 3)
        for source in result["results"]:
            self.assertIn(source["source_type"], {"slide", "transcript"})
            self.assertTrue(source["document_title"])
            self.assertIsInstance(source["relevance_score"], int)
            self.assertGreaterEqual(source["relevance_score"], server.MIN_FOUND_SCORE)
            self.assertTrue(source["preview"])
            self.assertLessEqual(len(source["preview"]), server.PUBLIC_PREVIEW_CHARS)
            self.assertIn(source["open_action"]["type"], {"open_slide", "open_transcript"})
            if source["source_type"] == "slide":
                self.assertIsInstance(source["page"], int)
                self.assertIsNone(source["segment_id"])
            else:
                self.assertIsNone(source["page"])
                self.assertRegex(source["segment_id"], r"^\[T\d{2}-\d{3}\]$")

    def test_slide_wins_when_relevance_is_equivalent(self) -> None:
        result = server.search_recall("RAG and citation")
        self.assertEqual(result["status"], "FOUND")
        self.assertEqual(result["results"][0]["source_type"], "slide")
        self.assertTrue(any(item["source_type"] == "transcript" for item in result["results"]))

    def test_every_open_action_resolves_exact_source(self) -> None:
        result = server.search_recall("RAG and citation")
        self.assertEqual(result["status"], "FOUND")
        for source in result["results"]:
            action = source["open_action"]
            if source["source_type"] == "slide":
                resolved = server.find_slide_page(action["file"], action["page"])
                self.assertIsNotNone(resolved)
                self.assertEqual(resolved["file"], source["file"])
                self.assertEqual(resolved["page"], source["page"])
            else:
                payload = server.transcript_segment_payload(action["segment_id"])
                self.assertIsNotNone(payload)
                self.assertEqual(payload["segment_id"], source["segment_id"])
                self.assertLessEqual(len(payload["content"]), server.TRANSCRIPT_VIEW_CHARS)

    def test_transcripts_use_bounded_subchunks_but_open_parent_segment(self) -> None:
        from backend.rag.document_loader import load_transcript_chunks, load_transcript_segments

        segments = load_transcript_segments()
        chunks = load_transcript_chunks()
        self.assertGreater(len(chunks), len(segments))
        self.assertLessEqual(max(len(item["text"].split()) for item in chunks), 220)
        self.assertEqual(len({item["document_id"] for item in chunks}), len(chunks))

        child = next(item for item in chunks if item.get("chunk_index", 0) > 1)
        self.assertEqual(child["source_id"], child["parent_segment_id"])
        public = server.public_result(child)
        self.assertEqual(public["segment_id"], child["parent_segment_id"])
        payload = server.transcript_segment_payload(public["segment_id"])
        self.assertIsNotNone(payload)
        self.assertEqual(payload["segment_id"], child["parent_segment_id"])
        self.assertLessEqual(len(payload["content"]), server.TRANSCRIPT_VIEW_CHARS)

    def test_degraded_answer_uses_structured_retrieved_citations(self) -> None:
        result = server.search_recall("RAG and citation")
        self.assertEqual(result["answer_source"], "extractive")
        self.assertEqual(result["generation"]["kind"], "learning_answer")
        self.assertTrue(result["generation_meta"]["degraded"])
        self.assertTrue(result["citations"])
        self.assertNotIn("[[", result["answer"])
        self.assertNotIn("Citation:", result["answer"])
        self.assertNotRegex(
            result["answer"],
            r"ROI: baseline|Quick win: impact cao|AI Agent trong workflow",
        )

    def test_learning_actions_are_grounded(self) -> None:
        base = server.search_recall("RAG and citation")
        sources = server.safe_history_sources(base["results"])

        summary = server.search_recall(
            "Tom tat nguon nay",
            previous_sources=sources[:1],
            action="summarize",
        )
        self.assertEqual(summary["status"], "FOUND")
        self.assertEqual(summary["generation"]["kind"], "slide_summary")
        self.assertGreaterEqual(len(summary["generation"]["key_points"]), 2)
        self.assertLessEqual(len(summary["generation"]["key_points"]), 4)
        self.assertNotIn("[[", summary["answer"])
        self.assertEqual(len(summary["results"]), 1)
        self.assertEqual(len(summary["citations"]), 1)
        expected_source_id = sources[0].get("source_id") or (
            f"{sources[0].get('file', '')}#page={sources[0].get('page', '')}"
        )
        self.assertEqual(
            summary["results"][0]["source_id"],
            expected_source_id,
        )
        self.assertEqual(
            summary["citations"][0]["source_id"],
            expected_source_id,
        )

        synthesis = server.search_recall(
            "Tong hop noi dung lien quan",
            previous_sources=sources,
            action="synthesize",
        )
        self.assertEqual(synthesis["status"], "FOUND")
        self.assertEqual(
            synthesis["generation"]["kind"],
            "multi_slide_synthesis",
        )
        self.assertTrue(synthesis["generation"]["themes"])
        self.assertTrue(synthesis["citations"])

        self_check = server.search_recall(
            "Tao cau tu kiem tra",
            previous_sources=sources,
            action="self_check",
        )
        self.assertEqual(self_check["status"], "FOUND")
        self.assertEqual(self_check["generation"]["kind"], "self_check")
        question_count = len(self_check["generation"]["questions"])
        self.assertGreaterEqual(question_count, 1)
        self.assertLessEqual(question_count, 3)
        self.assertNotRegex(self_check["answer"], r"(?i)đáp án\s*:")

    def test_fallback_learning_actions_keep_complete_ideas_without_filler(self) -> None:
        from backend.services.learning_action_service import (
            fallback_source_summary,
            fallback_source_synthesis,
            sentence_limited_content,
        )

        sources = server.safe_history_sources(
            [
                {
                    "source_type": "slide",
                    "source_id": "d1-slide-hackathon.pdf#page=23",
                    "file": "d1-slide-hackathon.pdf",
                    "page": 23,
                },
                {
                    "source_type": "slide",
                    "source_id": "d1-slide-hackathon.pdf#page=24",
                    "file": "d1-slide-hackathon.pdf",
                    "page": 24,
                },
                {
                    "source_type": "slide",
                    "source_id": "d2-slide-hackathon.pdf#page=18",
                    "file": "d2-slide-hackathon.pdf",
                    "page": 18,
                },
            ]
        )

        summary = fallback_source_summary(sources[:1])
        synthesis = fallback_source_synthesis(sources)

        self.assertIn("LEVEL 0", summary)
        self.assertIn("LEVEL 1", summary)
        self.assertIn("LEVEL 2", summary)
        self.assertIn("LEVEL 3", summary)
        self.assertIn("Bậc 4 — LEVEL 3:", summary)
        self.assertEqual(len(re.findall(r"(?m)^[1-3]\. ", summary)), 3)
        self.assertNotIn("Nguồn thuộc bài học", summary)
        self.assertNotIn("Hãy đối chiếu trực tiếp", summary)
        self.assertNotIn("Có kết nối +.", summary)
        self.assertNotIn("code 4 Action", synthesis)
        self.assertNotIn("…", summary + synthesis)
        self.assertIn("[[d1-slide-hackathon.pdf#page=23]]", synthesis)
        self.assertIn("[[d1-slide-hackathon.pdf#page=24]]", synthesis)
        self.assertEqual(
            sentence_limited_content("một mệnh đề chưa kết thúc " * 30, max_chars=120),
            "",
        )

        incomplete_model_summary, used_model = server.normalize_task_answer(
            (
                "Ý chính: Từ LLM đến agent có bốn mức độ. "
                "3 điều cần nhớ "
                "1. LEVEL 0 không có công cụ. "
                "2. LEVEL 1 có kết nối. "
                f"3. LEVEL 2 biết lập kế hoạch. {server.citation_marker(sources[0])}"
            ),
            sources[:1],
            task="summarize_first",
        )
        self.assertEqual(incomplete_model_summary, "")
        self.assertFalse(used_model)

    def test_openai_action_output_is_normalized_without_inventing_content(self) -> None:
        base = server.search_recall("RAG and citation")
        sources = server.safe_history_sources(base["results"])
        markers = [server.citation_marker(source) for source in sources]

        summary, summary_uses_model = server.normalize_task_answer(
            (
                "Chủ đề\nÝ chính: Giới hạn context cần được quản lý.\n"
                "3 điều cần nhớ\n1. Giữ context sạch. 2. Chỉ lấy phần liên quan. "
                f"3. Đối chiếu nguồn. {markers[0]}"
            ),
            sources[:1],
            task="summarize_first",
        )
        self.assertTrue(summary_uses_model)
        self.assertRegex(summary, r"(?m)^1\..*\n2\..*\n3\.")
        self.assertIn(markers[0], summary)

        synthesis, synthesis_uses_model = server.normalize_task_answer(
            (
                f"Ý thứ nhất dựa trên slide. {markers[0]} "
                f"Ý thứ hai bổ sung từ bài giảng. {markers[1]}"
            ),
            sources,
            task="synthesize_sources",
        )
        self.assertTrue(synthesis_uses_model)
        self.assertTrue(synthesis.startswith("Tổng hợp theo vấn đề"))
        self.assertIn(markers[0], synthesis)
        self.assertIn(markers[1], synthesis)

        self_check, self_check_uses_model = server.normalize_task_answer(
            (
                "Phần giải thích này không được đưa vào kết quả. "
                f"- Vì sao cần giữ context sạch? {markers[0]} "
                f"- Khi nào nên chỉ lấy đoạn liên quan? {markers[1]}"
            ),
            sources,
            task="self_check",
        )
        self.assertTrue(self_check_uses_model)
        self.assertTrue(self_check.startswith("Câu tự kiểm tra — chưa hiển thị đáp án"))
        self.assertNotIn("Phần giải thích", self_check)
        self.assertEqual(
            len(re.findall(r"(?m)^\d+\..*\?.*$", self_check)),
            2,
        )

    def test_ui_does_not_claim_selected_text_support(self) -> None:
        html = (server.ROOT / "index.html").read_text(encoding="utf-8")
        js_files = sorted((server.ROOT / "assets" / "js").glob("*.js"))
        frontend = "\n".join([html, *(path.read_text(encoding="utf-8") for path in js_files)])
        self.assertNotIn("selectionchange", frontend)
        self.assertNotIn("currentSelectedText", frontend)
        self.assertNotIn("selected_text:", frontend)
        self.assertIn('id="transcriptOverlay"', html)
        self.assertNotIn("<style", html)
        self.assertNotIn("<script>", html)
        self.assertIn('assets/css/tokens.css', html)
        self.assertIn('assets/js/app.js', html)
        self.assertIn("renderSourceCards", frontend)
        self.assertIn('data-source-action="open"', frontend)
        self.assertIn('data-source-index="${index}"', frontend)
        self.assertIn('id="assistantFab"', html)
        self.assertIn('id="chatDrawer"', html)
        self.assertIn('id="contextSelect"', html)
        self.assertNotIn('class="right-panel"', html)
        self.assertIn("window.VLearn", frontend)
        self.assertNotRegex(frontend, r"(?m)^(?:const|let|var|function|class)\s+")
        for path in js_files:
            self.assertTrue(path.is_file(), f"missing frontend module: {path.name}")

    def test_safe_slide_source_id_and_context_scope(self) -> None:
        safe_sources = server.safe_history_sources(
            [{"type": "slide", "source_id": "d1-slide-hackathon.pdf#page=23"}]
        )
        self.assertEqual(len(safe_sources), 1)
        self.assertEqual(safe_sources[0]["page"], 23)

        current = server.search_recall(
            "Giải thích slide đang mở",
            selected_scope="current",
            current_slide_source_id="d1-slide-hackathon.pdf#page=23",
        )
        self.assertEqual(current["status"], "FOUND")
        self.assertEqual(current["results"][0]["page"], 23)

        scoped = server.search_recall("Automate", selected_scope="day02")
        self.assertEqual(scoped["status"], "FOUND")
        self.assertTrue(
            all(server.source_matches_scope(item, "day02") for item in scoped["results"])
        )

    def test_chatlog_is_not_a_runtime_source(self) -> None:
        library = server.list_library()
        self.assertFalse(library["chatlog_available"])
        documents, _ = server.ensure_runtime_index()
        self.assertFalse(any(item.get("source_type") == "chatlog" for item in documents))


if __name__ == "__main__":
    unittest.main()
