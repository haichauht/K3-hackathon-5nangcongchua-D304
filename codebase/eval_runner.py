from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
GOLDEN_SET = REPO_ROOT / "eval" / "golden-set.json"
RESULT_PATHS = {
    "fallback": REPO_ROOT / "eval" / "run-fallback-results.md",
    # Preserve the first live 30/33 run as failure evidence. The post-fix
    # validation writes separately instead of overwriting history.
    "openai": REPO_ROOT / "eval" / "run-openai-after-action-fix-results.md",
}

LEAK_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+|"
    r"(?<!\d)(?:\+?84|0)(?:\s|\.|-)?(?:3|5|7|8|9)(?:\d(?:\s|\.|-)?){8}(?!\d)|"
    r"\b(?:conversation_id|user_id|message_id)\b",
    re.IGNORECASE,
)
def load_server(mode: str):
    if mode == "fallback":
        os.environ["OPENAI_API_KEY"] = ""

    sys.path.insert(0, str(ROOT))
    from backend import runtime as server  # noqa: PLC0415

    return server


def load_cases() -> list[dict]:
    return json.loads(GOLDEN_SET.read_text(encoding="utf-8"))["cases"]


def public_payload(result: dict) -> dict:
    return {
        "status": result.get("status"),
        "message": result.get("message"),
        "answer": result.get("answer"),
        "confidence": result.get("confidence"),
        "source_map": result.get("source_map"),
        "citations": result.get("citations", []),
        "results": result.get("results", [])[:3],
        "suggestions": result.get("suggestions", [])[:3],
    }


def suggestion_contract_ok(result: dict) -> bool:
    suggestions = result.get("suggestions", [])
    status = result.get("status")
    if not isinstance(suggestions, list):
        return False
    if status == "FOUND":
        return 1 <= len(suggestions) <= 3 and all(
            isinstance(item, dict)
            and (
                (
                    item.get("type") == "source_action"
                    and item.get("action") in {"summarize", "synthesize", "self_check"}
                )
                or (item.get("type") == "search" and item.get("input"))
            )
            for item in suggestions
        )
    if status == "CLARIFY":
        return 1 <= len(suggestions) <= 3 and all(
            isinstance(item, dict) and item.get("type") == "search" and item.get("input")
            for item in suggestions
        )
    if result.get("intent", {}).get("source") == "local_guardrail":
        return suggestions == []
    return 1 <= len(suggestions) <= 3 and all(
        isinstance(item, dict) and item.get("type") == "search" and item.get("input")
        for item in suggestions
    )


def answer_quality_ok(case: dict, result: dict) -> bool:
    if case.get("expected_status") != "FOUND":
        return True
    if result.get("intent", {}).get("type") == "LOCATE_SLIDE":
        return bool(result.get("answer") and result.get("results"))
    answer = str(result.get("answer", ""))
    sources = result.get("results", [])
    citation_markers = [server_marker for server_marker in case.get("_citation_markers", []) if server_marker]
    return bool(answer and citation_markers and any(marker in answer for marker in citation_markers))


def source_contract_ok(server, source: dict) -> bool:
    source_type = source.get("source_type")
    if source_type not in {"slide", "transcript"}:
        return False
    if not source.get("document_title"):
        return False
    preview = source.get("preview", "")
    if not isinstance(preview, str) or not preview or len(preview) > server.PUBLIC_PREVIEW_CHARS:
        return False
    if not isinstance(source.get("relevance_score"), int):
        return False
    action = source.get("open_action")
    if not isinstance(action, dict):
        return False
    if source_type == "slide":
        return (
            action.get("type") == "open_slide"
            and action.get("file") == source.get("file")
            and action.get("page") == source.get("page")
            and server.find_slide_page(action.get("file", ""), action.get("page")) is not None
        )
    payload = server.transcript_segment_payload(action.get("segment_id", ""))
    return bool(
        action.get("type") == "open_transcript"
        and action.get("segment_id") == source.get("segment_id")
        and payload
        and payload.get("segment_id") == source.get("segment_id")
        and len(payload.get("content", "")) <= server.TRANSCRIPT_VIEW_CHARS
    )


def answer_grounding_ok(server, result: dict) -> bool:
    if result.get("status") != "FOUND":
        return True
    answer = str(result.get("answer", ""))
    sources = result.get("results", [])
    if result.get("intent", {}).get("type") == "LOCATE_SLIDE":
        return bool(
            answer
            and sources
            and len(sources) <= 3
            and all(source.get("source_type") == "slide" for source in sources)
        )
    markers = [server.citation_marker(item) for item in sources]
    if not answer or not markers or not any(marker in answer for marker in markers):
        return False

    answer_without_citations = re.sub(r"\[\[?[^\]\n]{2,120}\]\]?", " ", answer)
    answer_tokens = {
        token
        for token in server.tokenize(answer_without_citations)
        if token not in server.GENERIC_RETRIEVAL_TERMS
    }
    evidence_tokens = set()
    for source in sources:
        runtime_source = server.resolve_runtime_source(source)
        if runtime_source:
            evidence_tokens.update(
                token
                for token in server.tokenize(server.document_search_text(runtime_source))
                if token not in server.GENERIC_RETRIEVAL_TERMS
            )
    if not answer_tokens:
        return False
    overlap = len(answer_tokens & evidence_tokens)
    return overlap >= 2 or overlap / len(answer_tokens) >= 0.18


def source_reference(source: dict) -> str:
    if source.get("source_type") == "slide":
        return f"{source.get('file', '')}#page={source.get('page', '')}"
    return str(source.get("segment_id") or source.get("source_id") or "")


def expected_source_support_ok(case: dict, result: dict) -> bool:
    expected = {
        str(reference)
        for reference in case.get("expected_source_refs", [])
        if str(reference)
    }
    if case.get("expected_status") != "FOUND" or not expected:
        return True
    actual = {source_reference(source) for source in result.get("results", [])}
    return bool(actual & expected)


def check_case(server, case: dict, mode: str) -> dict:
    result = server.search_recall(case["question"])
    case = {
        **case,
        "_citation_markers": [
            server.citation_marker(item)
            for item in result.get("results", [])
        ],
    }
    actual_status = result.get("status", "")
    output_blob = json.dumps(public_payload(result), ensure_ascii=False)
    leak_ok = LEAK_RE.search(output_blob) is None
    status_ok = actual_status == case["expected_status"]

    found_ok = True
    source_valid = True
    citation_valid = True
    confidence_ok = True
    suggestions_ok = suggestion_contract_ok(result)
    answer_quality = answer_quality_ok(case, result) and answer_grounding_ok(server, result)
    source_support_ok = expected_source_support_ok(case, result)
    if case["expected_status"] == "FOUND":
        found_ok = bool(result.get("answer") and result.get("results"))
        source_valid = all(
            server.is_valid_public_source(item)
            and source_contract_ok(server, item)
            for item in result.get("results", [])
        )
        citations = result.get("citations") or result.get("source_map") or []
        if result.get("intent", {}).get("type") == "LOCATE_SLIDE":
            citation_valid = citations == []
        else:
            citation_valid = bool(citations) and all(
                server.is_valid_public_source(
                    {
                        "type": item.get("type"),
                        "source_id": item.get("source_id") or item.get("source"),
                        "citation": item.get("citation") or item.get("source"),
                        "file": item.get("file", ""),
                        "page": item.get("page"),
                    }
                )
                for item in citations
            )
        confidence = result.get("confidence", "")
        retrieval = server.retrieval_confidence(result.get("results", []))
        rank = {"low": 0, "medium": 1, "high": 2}
        confidence_ok = confidence in rank and rank[confidence] <= rank[retrieval]

    openai_ok = True
    if mode == "openai" and case["expected_status"] == "FOUND":
        if result.get("intent", {}).get("type") == "LOCATE_SLIDE":
            # Locate is deliberately retrieval-only: one lead, source cards and
            # actions. Calling OpenAI here would reintroduce duplicate answers
            # and latency that the product flow explicitly removed.
            openai_ok = result.get("answer_source") == "retrieval"
        else:
            openai_ok = result.get("answer_source") == "openai"

    passed = (
        status_ok
        and found_ok
        and source_valid
        and citation_valid
        and confidence_ok
        and suggestions_ok
        and answer_quality
        and source_support_ok
        and leak_ok
        and openai_ok
    )

    return {
        "id": case["id"],
        "category": case["category"],
        "expected_status": case["expected_status"],
        "actual_status": actual_status,
        "passed": passed,
        "leak_ok": leak_ok,
        "intent_source": result.get("intent", {}).get("source", ""),
        "answer_source": result.get("answer_source", ""),
        "confidence": result.get("confidence", ""),
        "result_count": len(result.get("results", [])),
        "source_valid": source_valid,
        "citation_valid": citation_valid,
        "confidence_ok": confidence_ok,
        "suggestions_ok": suggestions_ok,
        "answer_quality": answer_quality,
        "source_support_ok": source_support_ok,
    }


def check_action_cases(server, mode: str) -> list[dict]:
    base = server.search_recall("RAG and citation")
    if base.get("status") != "FOUND":
        return []
    sources = server.safe_history_sources(base.get("results", []))
    definitions = [
        ("A01", "summarize", "Tom tat nguon nay"),
        ("A02", "synthesize", "Tong hop noi dung lien quan"),
        ("A03", "self_check", "Tao cau tu kiem tra"),
    ]
    rows = []
    for case_id, action, question in definitions:
        selected = sources[:1] if action == "summarize" else sources[:3]
        result = server.search_recall(
            question,
            previous_sources=selected,
            action=action,
        )
        answer = str(result.get("answer", ""))
        markers = [server.citation_marker(item) for item in result.get("results", [])]
        if action == "summarize":
            action_ok = (
                "Ý chính" in answer
                and "3 điều cần nhớ" in answer
                and bool(re.search(r"(?m)^1\..*\n2\..*\n3\.", answer))
                and any(marker in answer for marker in markers)
            )
        elif action == "synthesize":
            action_ok = (
                "Tổng hợp theo vấn đề" in answer
                and any(marker in answer for marker in markers)
            )
        elif action == "self_check":
            question_count = len(re.findall(r"(?m)^\d+\..*\?.*$", answer))
            action_ok = (
                "chưa hiển thị đáp án" in answer
                and 1 <= question_count <= 3
                and any(marker in answer for marker in markers)
            )
        source_valid = bool(result.get("results")) and all(
            source_contract_ok(server, item)
            for item in result.get("results", [])
        )
        openai_ok = mode != "openai" or result.get("answer_source") == "openai"
        passed = (
            result.get("status") == "FOUND"
            and action_ok
            and source_valid
            and answer_grounding_ok(server, result)
            and openai_ok
        )
        rows.append(
            {
                "id": case_id,
                "category": f"action_{action}",
                "expected_status": "FOUND",
                "actual_status": result.get("status", ""),
                "passed": passed,
                "leak_ok": LEAK_RE.search(json.dumps(public_payload(result), ensure_ascii=False)) is None,
                "intent_source": result.get("intent", {}).get("source", ""),
                "answer_source": result.get("answer_source", ""),
                "confidence": result.get("confidence", ""),
                "result_count": len(result.get("results", [])),
                "source_valid": source_valid,
                "citation_valid": any(marker in answer for marker in markers),
                "confidence_ok": result.get("confidence") in {"high", "medium", "low"},
                "suggestions_ok": suggestion_contract_ok(result),
                "answer_quality": action_ok and answer_grounding_ok(server, result),
                "source_support_ok": True,
            }
        )
    return rows


def render_markdown(rows: list[dict], mode: str, server) -> str:
    passed_count = sum(1 for row in rows if row["passed"])
    leak_count = sum(1 for row in rows if not row["leak_ok"])
    source_invalid_count = sum(1 for row in rows if not row["source_valid"])
    citation_invalid_count = sum(1 for row in rows if not row["citation_valid"])
    confidence_invalid_count = sum(1 for row in rows if not row["confidence_ok"])
    suggestion_invalid_count = sum(1 for row in rows if not row["suggestions_ok"])
    answer_quality_invalid_count = sum(1 for row in rows if not row["answer_quality"])
    source_support_invalid_count = sum(1 for row in rows if not row["source_support_ok"])
    outside_domain_false_found = sum(
        1
        for row in rows
        if row["category"] == "outside_domain" and row["actual_status"] == "FOUND"
    )
    action_failures = sum(
        1
        for row in rows
        if row["category"].startswith("action_") and not row["passed"]
    )
    total = len(rows)
    pass_rate = round(passed_count / total * 100, 1) if total else 0
    health = server.health_status()

    display_mode = "OpenAI" if mode == "openai" else "Fallback"
    lines = [
        f"# {display_mode} Results - VLearn Recall Eval",
        "",
        f"Ngày chạy: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Mode: `{mode}`",
        f"AI mode server: `{health['ai_mode']}`",
        f"Model: `{health['model'] or 'N/A'}`",
        "Data rule: không ghi answer/snippet/source text vào file kết quả; chỉ ghi status và metadata kiểm thử.",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Total cases | {total} |",
        f"| Pass | {passed_count} |",
        f"| Fail | {total - passed_count} |",
        f"| Pass rate | {pass_rate}% |",
        f"| Restricted-data leak | {leak_count} |",
        f"| Invalid public source | {source_invalid_count} |",
        f"| Invalid citation map | {citation_invalid_count} |",
        f"| Inconsistent confidence | {confidence_invalid_count} |",
        f"| Invalid suggestions | {suggestion_invalid_count} |",
        f"| Weak answer grounding/action contract | {answer_quality_invalid_count} |",
        f"| Curated source-support mismatch | {source_support_invalid_count} |",
        f"| Outside-domain false FOUND | {outside_domain_false_found} |",
        f"| Action failures | {action_failures} |",
        f"| Slides detected | {health['data']['slides']} |",
        f"| Transcripts detected | {health['data']['transcripts']} |",
        f"| Chatlog available | {health['data']['chatlog_available']} |",
        "",
        "## Results",
        "",
        "| ID | Category | Expected | Actual | Pass | Sources | Source OK | Support OK | Citation OK | Suggestions | Answer | Confidence | Leak OK |",
        "|---|---|---|---|---|---:|---|---|---|---|---|---|---|",
    ]

    for row in rows:
        mark = "PASS" if row["passed"] else "FAIL"
        leak_mark = "yes" if row["leak_ok"] else "no"
        lines.append(
            "| {id} | {category} | {expected_status} | {actual_status} | {mark} | {result_count} | "
            "{source_valid} | {source_support_ok} | {citation_valid} | {suggestions_ok} | {answer_quality} | {confidence} | {leak_mark} |".format(
                **row,
                mark=mark,
                leak_mark=leak_mark,
            )
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Run VLearn Recall MVP eval set.")
    parser.add_argument("--mode", choices=["openai", "fallback"], default="openai")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the mode-specific eval result file.",
    )
    args = parser.parse_args()

    server = load_server(args.mode)
    rows = [check_case(server, case, args.mode) for case in load_cases()]
    rows.extend(check_action_cases(server, args.mode))
    markdown = render_markdown(rows, args.mode, server)

    if args.write:
        RESULT_PATHS[args.mode].write_text(markdown, encoding="utf-8")

    print(markdown)


if __name__ == "__main__":
    main()
