# VLearn Recall

VLearn Recall là trợ lý học tập tìm lại nội dung trong slide và transcript của khóa học, trả lời có căn cứ, mở đúng trang/đoạn và hỗ trợ tóm tắt, tổng hợp, tự kiểm tra.

Ứng dụng dùng HTML/CSS/JavaScript thuần và backend Python chuẩn thư viện. Không có npm, bundler hoặc build step.

## Kiến trúc

```text
codebase/
├── index.html                  # semantic markup và thứ tự tải asset
├── assets/
│   ├── css/                    # token, base, layout, viewer, component, chatbot
│   ├── js/                     # config, state, API, viewer, context, action, chat, app
│   └── icons/
├── backend/
│   ├── app.py                  # lifecycle ứng dụng
│   ├── config.py               # env và đường dẫn an toàn
│   ├── capabilities.py         # health/capability report
│   ├── api/router.py           # HTTP adapter, JSON/CORS/static routes
│   ├── schemas/requests.py     # validate request contract
│   ├── security/guardrails.py  # deterministic routing và data guardrail
│   ├── rag/
│   │   ├── document_loader.py  # slide pages + transcript parent/subchunk loader
│   │   ├── vision_processor.py # enrichment ảnh slide tùy chọn
│   │   ├── index_manager.py    # persisted index lifecycle/atomic swap
│   │   ├── dense_retriever.py  # OpenAI dense embedding, explicit opt-in
│   │   ├── reranker.py         # evidence/dense bi-encoder reranking
│   │   └── retriever.py        # fast sparse+dense hybrid + absolute gate
│   ├── services/
│   │   ├── recall_service.py   # điều phối use case
│   │   ├── answer_service.py   # OpenAI/fallback grounded answer
│   │   ├── learning_action_service.py
│   │   └── source_service.py   # source contract và open action
│   └── runtime.py              # facade ổn định cho test/eval/CLI
├── tests/
├── server.py                   # entry point mỏng
├── rag_index.py                # index CLI mỏng
├── smoke_test.py
└── eval_runner.py
```

Các action học tập dùng chung một module vì cùng pipeline citation/normalization; không tách thành nhiều file vài dòng. `server.py` không chứa retrieval, prompt, intent, PDF hay action logic.

## Cài và chạy

```powershell
cd D:\01_HocTap\AIThucChien\Lab\K3-hackathon-5nangcongchua-D304\codebase
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python server.py
```

Mở `http://127.0.0.1:8011`.

Có thể mở trực tiếp `index.html`; frontend sẽ gọi `http://127.0.0.1:8011` qua một `API_BASE_URL` duy nhất. Nếu backend chưa chạy, drawer/welcome UI vẫn hoạt động và chức năng cần API báo lỗi thân thiện, không sinh dữ liệu giả.

## Cấu hình

`.env` là file local và không được commit:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.6-luna
AI_GENERATION_MODE=auto
OPENAI_ANSWER_TIMEOUT_SECONDS=12
OPENAI_REASONING_EFFORT=none
OPENAI_MAX_OUTPUT_TOKENS=700
VLEARN_RECALL_HOST=127.0.0.1
VLEARN_RECALL_PORT=8011
VLEARN_CORS_ORIGINS=null,http://127.0.0.1:8011,http://localhost:8011
RAG_INDEX_MODE=persistent
RAG_AUTO_REFRESH=true
RAG_INDEX_DIR=data/.rag-index
RAG_EMBEDDING_MODEL=auto
RAG_DENSE_ENABLED=false
RAG_DENSE_MODEL=text-embedding-3-small
RAG_DENSE_DIMENSIONS=256
RAG_RERANK_ENABLED=true
RAG_VISION_ENABLED=true
```

`AI_GENERATION_MODE=openai` bắt buộc dùng OpenAI cho generation; timeout/lỗi API trả `AI_UNAVAILABLE`, output sai sau một repair call trả `INVALID_MODEL_OUTPUT`, không âm thầm chuyển sang raw fallback. `extractive` chỉ dành cho debug/offline. `auto` dùng OpenAI khi có key; khi không có key vẫn diễn giải có cấu trúc từ retrieved source và health/UI ghi rõ `degraded`.

## Luồng xử lý

1. Guardrail và intent routing chạy local, deterministic.
2. Slide dùng một page/chunk. Transcript giữ segment cha `[Txx-NNN]` để mở viewer, nhưng retrieval dùng subchunk tối đa 220 từ, target 180 từ và overlap 30 từ.
3. Fast path dùng lexical + local sparse TF-IDF/char-trigram với normalized fields được cache trong RAM. Nếu dense đã được bật và build, truy vấn khó mới gọi query embedding; truy vấn có lexical support rõ không bị cộng thêm network latency.
4. Absolute relevance gate loại top result không đủ căn cứ; query ngoài domain không được `FOUND` chỉ vì có top 1.
5. Evidence reranker loại subchunk trùng parent, giữ tối đa ba nguồn và ưu tiên slide khi tương đương. Khi dense active, health ghi đúng mode `dense_bi_encoder`; đây không phải cross-encoder.
6. OpenAI chỉ được gọi sau retrieval và chỉ nhận projection đã làm sạch của tối đa ba source, không quá 1.200 ký tự/source. Mỗi task dùng prompt và Pydantic Structured Output riêng.
7. Model chỉ trả `source_indexes`; backend validate rồi map sang `source_id`, file/page/segment và open action thật.
8. Kết quả OpenAI hợp lệ được cache theo task, model, prompt version và source hash trong `data/.rag-index/generation_cache.json`; raw prompt/source không được ghi vào cache.

Source policy:

- Slide và transcript đều hợp lệ; slide được ưu tiên nhẹ khi mức phù hợp tương đương.
- Transcript không bị ép map sang slide khi không có liên kết chắc chắn.
- Chatlog không được load vào runtime retrieval và không bao giờ là nguồn trả lời.
- Transcript public chỉ có preview ngắn; viewer nội bộ trả đúng một segment, không trả toàn bộ file.
- Slide mở đúng PDF/page. Viewer hiện render ảnh PNG nên chưa quảng bá selected-text.

Public source contract gồm `source_type`, `document_title`/`lesson_title`, `page` hoặc `segment_id`, `preview`, `relevance_score` và `open_action`.

## API

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/api/health` | Capability, answer mode và index status |
| GET | `/api/library` | Danh mục slide/transcript an toàn |
| POST | `/api/recall-intent` | Deterministic intent/guardrail |
| POST | `/api/recall-search` | Search, answer và learning actions |
| GET | `/api/slide-page?file=...&page=...` | Render đúng trang PDF |
| GET | `/api/transcript-segment?segment_id=[Txx-NNN]` | Viewer đúng đoạn transcript |
| GET | `/data/slides/<file.pdf>` | File PDF đã validate trong slide root |

Payload frontend gửi vào recall:

```json
{
  "input": "Giải thích slide đang mở",
  "history": [],
  "previous_sources": [],
  "action": "",
  "scope": "current",
  "current_slide_source_id": "d1-slide-hackathon.pdf#page=23"
}
```

Action hợp lệ: `summarize`, `synthesize`, `self_check`, `open`. Action `compare` đã bị loại khỏi UI, API schema và eval.

## Data boundary và index

Backend chỉ đọc raw learning data tại:

- `../data/vlearn-pack/slides/*.pdf`
- `../data/vlearn-pack/transcript/*.md`

Index/cache chỉ nằm trong `../data/.rag-index/`. Không copy raw data vào `codebase/`, asset frontend hoặc dịch vụ khác. Index lưu mapping, vector, manifest và Vision metadata; không lưu ảnh, raw transcript, chatlog hay absolute path.

`RAG_DENSE_ENABLED=false` là mặc định an toàn. API key không tự động được hiểu là quyền gửi hàng loạt học liệu ra ngoài. Chỉ đặt `true` khi đã có quyền egress rõ ràng; build sẽ gửi projection đã giới hạn độ dài của từng slide/subchunk để tạo embedding một lần, sau đó chỉ vector được persist trong `data/.rag-index`.

```powershell
python rag_index.py status
python rag_index.py build
python rag_index.py build --force
```

`RAG_INDEX_MODE=memory` tắt persisted index. Khi persistent write lỗi, runtime hạ cấp sang memory và health báo `degraded/fallback_reason` thay vì làm server crash.

## Test

```powershell
$env:OPENAI_API_KEY=""
python -m pytest -q
python smoke_test.py
```

Bộ test gồm service flow, false `FOUND` ngoài domain, index lifecycle, Vision contract, HTTP/CORS, frontend/backend payload, exact page/segment open action, source security và frontend modular contract.

Eval fallback không gửi evidence ra ngoài:

```powershell
python eval_runner.py --mode fallback
```

Eval OpenAI gọi API thật với tối đa ba evidence block đã giới hạn. Chỉ thêm `--write` khi chủ động muốn ghi một artifact kết quả mới:

```powershell
python eval_runner.py --mode openai
```

Runner tách rõ fallback/OpenAI, fail OpenAI case nếu thực tế rơi về fallback, kiểm false `FOUND`, curated answer-source support, citation, open action và ba learning action. Golden set hiện có 60 câu và runner thêm 3 action case. Không sửa golden label hoặc số liệu kết quả để làm đẹp báo cáo.
