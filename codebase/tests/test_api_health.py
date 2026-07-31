from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
from unittest.mock import Mock, patch

os.environ["OPENAI_API_KEY"] = ""

from backend.api.router import VLearnRequestHandler  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.schemas.requests import RecallRequest  # noqa: E402


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), VLearnRequestHandler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request_json(
        self,
        path: str,
        *,
        payload: dict | None = None,
        origin: str = "",
    ) -> tuple[dict, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        response = urllib.request.urlopen(request, timeout=30)
        return json.loads(response.read().decode("utf-8")), response

    def test_health_and_library_contract(self) -> None:
        health, _ = self.request_json("/api/health")
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["ai_mode"], "fallback")
        self.assertFalse(health["data"]["chatlog_available"])
        self.assertGreater(health["data"]["retrieval"]["documents"], 0)

        library, _ = self.request_json("/api/library")
        self.assertEqual(len(library["slides"]), 2)
        self.assertEqual(len(library["transcripts"]), 6)
        self.assertNotIn("absolute_path", json.dumps(library))

    def test_removed_compare_action_is_not_accepted_by_api_schema(self) -> None:
        request = RecallRequest.from_payload(
            {
                "request_id": "removed-compare",
                "input": "So sánh các slide",
                "action": "compare",
            }
        )
        self.assertEqual(request.action, "")

    def test_recall_payload_matches_frontend_contract(self) -> None:
        result, _ = self.request_json(
            "/api/recall-search",
            payload={
                "request_id": "request-contract-1",
                "input": "RAG and citation",
                "history": [],
                "previous_sources": [],
                "action": "",
                "scope": "all",
                "current_slide_source_id": "",
            },
        )
        self.assertEqual(result["status"], "FOUND")
        self.assertEqual(result["request_id"], "request-contract-1")
        self.assertLessEqual(len(result["results"]), 3)

        locate, _ = self.request_json(
            "/api/recall-search",
            payload={
                "request_id": "request-locate-1",
                "input": "Slide nào nói về AI Agent?",
                "scope": "all",
            },
        )
        self.assertEqual(locate["request_id"], "request-locate-1")
        self.assertEqual(locate["intent"]["type"], "LOCATE_SLIDE")
        self.assertEqual(
            [item["page"] for item in locate["results"][:2]],
            [23, 24],
        )
        self.assertLessEqual(len(locate["results"]), 3)

        current, _ = self.request_json(
            "/api/recall-search",
            payload={
                "input": "Giải thích slide đang mở",
                "scope": "current",
                "current_slide_source_id": "d1-slide-hackathon.pdf#page=23",
            },
        )
        self.assertEqual(current["status"], "FOUND")
        self.assertEqual(current["results"][0]["page"], 23)

    def test_direct_file_frontend_is_allowed_by_cors(self) -> None:
        _, response = self.request_json("/api/health", origin="null")
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "null")

        frontend = urllib.request.urlopen(self.base_url + "/", timeout=10)
        self.assertEqual(frontend.headers.get("Cache-Control"), "no-store")

    def test_summary_action_is_pinned_to_one_source(self) -> None:
        source_ids = [
            "d1-slide-hackathon.pdf#page=16",
            "d2-slide-hackathon.pdf#page=4",
            "d1-slide-hackathon.pdf#page=28",
        ]
        result, _ = self.request_json(
            "/api/recall-search",
            payload={
                "request_id": "action-summary-one-source",
                "input": "Tóm tắt slide đã chọn",
                "action": "summarize",
                "previous_sources": [
                    {"type": "slide", "source_id": source_id}
                    for source_id in source_ids
                ],
            },
        )

        self.assertEqual(result["status"], "FOUND")
        self.assertEqual(result["request_id"], "action-summary-one-source")
        self.assertEqual(
            [source["source_id"] for source in result["results"]],
            [source_ids[0]],
        )
        self.assertEqual(
            [source["source_id"] for source in result["citations"]],
            [source_ids[0]],
        )

    def test_viewers_resolve_exact_page_and_segment(self) -> None:
        slide = urllib.request.urlopen(
            self.base_url + "/api/slide-page?file=d1-slide-hackathon.pdf&page=1",
            timeout=30,
        )
        self.assertEqual(slide.headers.get_content_type(), "image/png")
        self.assertTrue(slide.read(8).startswith(b"\x89PNG"))

        segment = urllib.parse.quote("[T01-001]")
        transcript, _ = self.request_json(
            f"/api/transcript-segment?segment_id={segment}"
        )
        self.assertEqual(transcript["segment_id"], "[T01-001]")
        self.assertTrue(transcript["content"])
        self.assertNotIn("file_path", transcript)

    def test_invalid_json_returns_safe_structured_error(self) -> None:
        request = urllib.request.Request(
            self.base_url + "/api/recall-search",
            data=b"{invalid",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "BAD_REQUEST")
        self.assertNotIn("traceback", json.dumps(payload).lower())

    def test_application_entrypoint_uses_the_health_contract(self) -> None:
        fake_server = Mock()
        fake_server.serve_forever.side_effect = KeyboardInterrupt
        with (
            patch("backend.app.ensure_runtime_index"),
            patch("backend.app.ThreadingHTTPServer", return_value=fake_server),
            redirect_stdout(StringIO()) as output,
        ):
            create_app().run()

        self.assertIn("answer_mode=fallback", output.getvalue())
        self.assertIn("rag_index=", output.getvalue())
        fake_server.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
