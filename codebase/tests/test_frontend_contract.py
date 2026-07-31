from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_frontend_is_modular_and_has_no_embedded_secrets_or_mock_results(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        js_paths = sorted((ROOT / "assets" / "js").glob("*.js"))
        css_paths = sorted((ROOT / "assets" / "css").glob("*.css"))
        frontend = "\n".join(
            [html, *(path.read_text(encoding="utf-8") for path in js_paths)]
        )

        self.assertNotIn("<style", html)
        self.assertNotIn("<script>", html)
        self.assertNotRegex(frontend, r"sk-[A-Za-z0-9_-]{20,}")
        self.assertNotIn("mock FOUND", frontend)
        self.assertIn("window.VLearn", frontend)
        self.assertTrue((ROOT / "assets" / "icons" / "assistant-robot.svg").is_file())
        self.assertGreaterEqual(len(js_paths), 6)
        self.assertGreaterEqual(len(css_paths), 4)
        self.assertNotRegex(frontend, r"(?m)^(?:const|let|var|function|class)\s+")

    def test_frontend_calls_only_the_local_backend_contract(self) -> None:
        api = (ROOT / "assets" / "js" / "api.js").read_text(encoding="utf-8")
        config = (ROOT / "assets" / "js" / "config.js").read_text(encoding="utf-8")
        combined = api + "\n" + config

        self.assertIn('recallSearch: "/api/recall-search"', config)
        self.assertIn('slidePage: "/api/slide-page"', config)
        self.assertIn('transcriptSegment: "/api/transcript-segment"', config)
        self.assertNotIn("api.openai.com", combined)
        self.assertNotIn("OPENAI_API_KEY", combined)
        self.assertIn("request_id", api)
        self.assertIn("current_slide_source_id", api)
        self.assertIn("previous_sources", api)

    def test_drawer_and_viewer_keep_separate_state(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        state = (ROOT / "assets" / "js" / "state.js").read_text(encoding="utf-8")
        self.assertIn('id="assistantFab"', html)
        self.assertIn('id="chatDrawer"', html)
        self.assertNotIn('class="right-panel"', html)
        for field in (
            "isChatOpen",
            "currentSlide",
            "conversationMessages",
            "actionStatusByMessage",
            "chatScrollPosition",
        ):
            self.assertRegex(state, rf"\b{re.escape(field)}\b")
        self.assertNotIn("previousTopSlides", state)
        self.assertNotIn("openedSlideMessages", state)

    def test_slide_viewer_has_no_download_or_print_controls(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        state = (ROOT / "assets" / "js" / "state.js").read_text(encoding="utf-8")
        app = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
        viewer = (ROOT / "assets" / "js" / "viewer.js").read_text(encoding="utf-8")
        frontend = "\n".join((html, state, app, viewer))

        self.assertNotIn('id="downloadPdf"', html)
        self.assertNotIn('id="printPdf"', html)
        self.assertNotIn("downloadPdfBtn", frontend)
        self.assertNotIn("printPdfBtn", frontend)
        self.assertNotIn("downloadCurrentPdf", frontend)
        self.assertNotIn("printCurrentPdf", frontend)

    def test_dynamic_chat_events_and_requests_are_idempotent(self) -> None:
        app = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
        api = (ROOT / "assets" / "js" / "api.js").read_text(encoding="utf-8")
        chatbot = (ROOT / "assets" / "js" / "chatbot.js").read_text(encoding="utf-8")
        actions = (ROOT / "assets" / "js" / "actions.js").read_text(encoding="utf-8")
        frontend = app + "\n" + api + "\n" + chatbot + "\n" + actions

        self.assertEqual(app.count('dom.chatForm.addEventListener("submit"'), 1)
        self.assertEqual(app.count('dom.chatMessages.addEventListener("click"'), 1)
        self.assertIn("dom.chatForm.requestSubmit()", app)
        self.assertEqual(app.count("chatbot.askQuestion(dom.chatInput.value)"), 1)
        self.assertIn("if (state.initialized) return", app)
        self.assertNotIn("onclick=", frontend)

        self.assertIn("request_id: options.requestId", api)
        self.assertIn("state.activeRequest?.id !== requestId", chatbot)
        self.assertIn("payload.request_id !== requestId", chatbot)
        self.assertIn("existingElement", chatbot)
        self.assertIn("message?.slides", actions)
        self.assertIn("message?.citations", actions)
        self.assertNotIn("previousTopSlides", frontend)
        self.assertNotIn("addOpenedSlideMessage", frontend)
        self.assertNotIn("Đã mở trang", actions)
        self.assertNotIn('data-source-action="compare"', frontend)
        self.assertNotIn('apiAction: "compare"', actions)

    def test_locate_slide_has_one_compact_response_block(self) -> None:
        chatbot = (ROOT / "assets" / "js" / "chatbot.js").read_text(encoding="utf-8")
        locate_branch = chatbot.split("if (isLocate) {", 1)[1].split(
            "const answer = splitAnswer", 1
        )[0]

        self.assertIn("renderSourceCards(slideSources, messageId)", locate_branch)
        self.assertIn('intent: "LOCATE_SLIDE"', locate_branch)
        self.assertIn("slides: slideSources", locate_branch)
        self.assertIn("citations: []", locate_branch)
        self.assertIn("actionResults: {}", locate_branch)
        self.assertNotIn("renderCitations", locate_branch)
        self.assertNotIn("answer-card", locate_branch)

    def test_raw_citation_tokens_are_not_rendered_as_answer_text(self) -> None:
        chatbot = (ROOT / "assets" / "js" / "chatbot.js").read_text(encoding="utf-8")
        context = (ROOT / "assets" / "js" / "context.js").read_text(encoding="utf-8")

        self.assertIn("function isRawCitationLine", chatbot)
        self.assertIn("function formatAnswerLine", chatbot)
        self.assertIn("function hasVisibleInlineCitations", chatbot)
        self.assertIn('class="citation-link inline-citation"', chatbot)
        self.assertIn("context.formatSourceLabel(sources[sourceIndex], sourceIndex)", chatbot)
        self.assertNotIn(">Nguồn ${sourceIndex + 1}</button>", chatbot)
        self.assertIn("`Slide [${source.page}]`", context)
        self.assertIn("<span>Slide [${source.page}]</span>", chatbot)
        self.assertNotIn("Slide ${sourceNumber} · Trang", context)
        self.assertIn("formatAnswerBody(answer.body, sources, messageId)", chatbot)
        self.assertIn("formatAnswerBody(answer.body, sources, element.id)", chatbot)


if __name__ == "__main__":
    unittest.main()
