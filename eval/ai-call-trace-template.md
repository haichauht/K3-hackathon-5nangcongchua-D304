# AI Call Trace Template - MVP

MVP hiện tại chỉ gọi OpenAI **sau retrieval** để tạo grounded answer hoặc thực hiện action `summarize / synthesize / self_check`. Routing, guardrail, query cleanup, absolute relevance gate và ranking đều deterministic/local. File này là template trace ngắn; không lưu API key, raw transcript, raw chatlog hoặc snippet dài.

## Decision Trung Tâm Đề Xuất

**Grounded answer/action sau deterministic retrieval**

Luồng trước AI:

1. Guardrail deterministic trả `CLARIFY / RESTRICTED / OUT_OF_SCOPE / FOUND_CANDIDATE`.
2. Hybrid retrieval chạy trên slide + transcript, không load chatlog.
3. Absolute relevance gate loại query ngoài domain.
4. Backend lấy tối đa 3 nguồn và chuẩn hóa source contract.

Chỉ khi đã có nguồn đủ hỗ trợ, OpenAI mới đọc evidence giới hạn và tạo answer có citation. Nếu không có key/lỗi mạng, fallback chỉ diễn giải retrieved source; không có câu trả lời hard-code theo topic.

## Prompt Đề Xuất

```text
Bạn là VLearn Recall, trợ lý diễn giải evidence sau retrieval.

Nhiệm vụ:
1. Chỉ dùng evidence được cung cấp.
2. Gắn mỗi khẳng định với citation_format của nguồn hỗ trợ.
3. Với summarize: ý chính + đúng 3 điều cần nhớ + citation.
4. Với synthesize: loại ý trùng và giữ citation theo từng ý.
5. Với self_check: tạo 1-3 câu hỏi, không đưa đáp án.

Luật:
- Không xuất raw chatlog/transcript.
- Không suy luận danh tính từ mã ẩn danh.
- Không dùng kiến thức ngoài evidence để lấp chỗ trống.

User input:
{{user_input}}

Retrieved evidence:
{{redacted_evidence}}

Public source contract:
{{public_sources}}

Requested task:
{{answer|summarize_first|synthesize_sources|self_check}}
```

## Trace Cần Lưu

| Field | Nội dung |
|---|---|
| Timestamp |  |
| Model |  |
| Input |  |
| Output JSON |  |
| Router result | deterministic/local |
| Retrieval relevance |  |
| Requested task |  |
| Latency |  |
| Có dùng data nhạy cảm không? | Không |
| Người kiểm |  |

## Cách Chạy Backend Python

```powershell
$env:OPENAI_API_KEY="DAN_API_KEY_CUA_BAN"
$env:OPENAI_MODEL="gpt-5"
cd C:\VinUni-Lab\K3-Day05-5nangcongchua\codebase
python server.py
```

Endpoint có thể gọi AI sau retrieval:

```text
POST http://127.0.0.1:8000/api/recall-search
```

## Ví Dụ Trace Sau Khi Có AI Call

```json
{
  "input": "Tóm tắt nguồn này",
  "router": "history_followup",
  "task": "summarize_first",
  "retrieved_sources": [
    {
      "source_type": "slide",
      "file": "d1-slide-hackathon.pdf",
      "page": 23
    }
  ],
  "output": {
    "answer": "Ý chính ... [[d1-slide-hackathon.pdf#page=23]]",
    "confidence": "medium"
  }
}
```

## Lưu Ý Bảo Mật

- Không commit API key.
- Chỉ gửi tối đa ba evidence block đã giới hạn; không bao giờ gửi chatlog hoặc toàn bộ transcript.
- Lưu trace ngắn trong repo, không lưu secret hoặc raw data dài.
