# Run 01 Results - Runtime Data MVP

Ngày chạy: 2026-07-30  
MVP: `codebase/index.html` + `codebase/server.py`  
Kiểu chạy: backend fallback local, ép không gọi mạng/API key thật.  
Data rule: đọc `data/vlearn-pack` tại runtime; không copy dữ liệu từ `data/` ra ngoài.

## Summary

| Metric | Result |
|---|---:|
| PDF files detected | 2 |
| PDF page counts detected | 29, 29 |
| Smoke cases | 5 |
| Pass | 5 |
| Fail / needs improvement | 0 |
| Pass rate | 100% |
| Restricted-data leak | 0 |
| Python backend syntax | Pass |
| Runtime search endpoint | Yes, `POST /api/recall-search` |
| Intent endpoint coded | Yes, deterministic/local `POST /api/recall-intent` |

## Ghi Chú

Đây là lượt chạy lịch sử trước khi nâng relevance gate. Runtime hiện tại đọc PDF + transcript; chatlog không tham gia retrieval/answer. Intent routing là deterministic/local. Khi có `OPENAI_API_KEY`, OpenAI chỉ được gọi sau retrieval để tạo grounded answer/action. Kết quả hiện tại xem ở file mode-specific, không suy diễn mode OpenAI từ lượt fallback này.
