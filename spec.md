# AI SPEC — VLearn Recall · Nhóm 5 Nàng Công Chúa · Zone không có/không áp dụng

- Hướng: [x] A — VLearn  [ ] B — Trợ lý Học viên  [ ] C — Làn mở
- Loại: [ ] Tối ưu tính năng có sẵn  [x] Tính năng mới
- Mức prototype: [ ] Sketch  [ ] Mock  [x] Working local

Trạng thái tài liệu: khớp implementation và bằng chứng có trong repo tại ngày 2026-07-31. Zone của nhóm: không có/không áp dụng.

## Data Boundary & Source Policy

### Nguồn được phép

- Slide PDF và transcript bài giảng trong `data/vlearn-pack/` đều là nguồn trả lời hợp lệ.
- Slide được ưu tiên nhẹ khi slide và transcript có mức phù hợp tương đương.
- Transcript là một nguồn độc lập. Không ép transcript map sang slide nếu không có liên kết chắc chắn.
- Chatlog tuyệt đối không được load vào retrieval index, answer context, source card hoặc OpenAI prompt. Chatlog chỉ được mining/eval tại local.

### Dữ liệu được phép hiển thị

- Mỗi source card chỉ có metadata chuẩn hóa và preview tối đa 220 ký tự.
- Slide mở đúng PDF và page.
- Transcript mở viewer nội bộ tới đúng `segment_id`; endpoint chỉ trả một segment đã giới hạn tối đa 1.800 ký tự, không trả toàn bộ file.
- Không xuất raw chatlog, raw transcript dài, PII, email, số điện thoại hoặc mã có thể dùng để suy ngược danh tính.
- Spec/eval không chứa answer, raw snippet hoặc source text dài; chỉ giữ aggregate, status và metadata kiểm thử.

### Dữ liệu gửi tới OpenAI

- Trong luồng hỏi đáp, OpenAI chỉ được gọi sau khi deterministic routing, retrieval và absolute relevance gate đã tìm được nguồn đủ hỗ trợ.
- Mỗi grounded answer/action gửi tối đa 3 evidence block đã redacted; không gửi chatlog hoặc toàn bộ transcript.
- Có một ngoại lệ kỹ thuật tách biệt với query flow: khi build/rebuild index, optional Slide Vision có thể gửi ảnh render của đúng một trang PDF ít text nhưng có hình/diagram/chart. Kết quả được cache; có thể tắt bằng `RAG_VISION_ENABLED=false`.
- API key chỉ lấy từ biến môi trường/.env local và không được commit.
- Không có key hoặc call lỗi: hệ thống chạy fallback chỉ diễn giải retrieved evidence. Không có evidence đủ hỗ trợ thì `NOT_FOUND`; không dùng answer hard-code theo chủ đề.

## §1. User & Job

### Job executor và workflow hiện tại

**Job executor:** học viên khóa AI Thực Chiến đang làm lab, chuẩn bị bài tập/báo cáo/quiz hoặc ôn lại bài nhưng chỉ nhớ một mảnh nội dung từng nghe.

Workflow hiện tại:

1. Học viên nhớ một ý như “hình như thầy có nói phần này”.
2. Họ tự lục slide trên VLearn, tìm tài liệu ngoài, xem ghi chú, hỏi bạn/TA hoặc hỏi một chatbot chung.
3. Nếu không nhớ đúng từ khóa hoặc ý chỉ có trong phần giảng miệng, quá trình tìm kéo dài.
4. Nếu câu trả lời không có nguồn mở lại được, học viên vẫn phải tự kiểm chứng và có thể học sai.

### JTBD

**Core JTBD:** Khi tôi chỉ nhớ mang máng một nội dung đã học, tôi muốn tìm lại đúng nguồn liên quan nhanh để có thể ôn lại, tự kiểm chứng và tiếp tục làm bài mà không mất mạch học.

Job stories:

- Khi đang làm lab và nhớ giảng viên từng nói về lỗi tương tự, tôi muốn tìm đúng đoạn bài giảng để tiếp tục xử lý.
- Khi chuẩn bị bài tập/báo cáo, tôi muốn kiểm tra một khái niệm có đúng với nội dung khóa học trước khi dùng.
- Khi ôn lại bài, tôi muốn gom các nguồn liên quan nhưng vẫn biết từng ý đến từ đâu.

**Problem statement:** Học viên chỉ nhớ một phần nội dung đã học nhưng không biết nó nằm ở buổi học, trang slide hay đoạn giảng nào; việc tự tìm lại mất thời gian, làm gián đoạn học/lab và khiến họ không chắc kiến thức tìm được có đúng với lời giảng viên.

### Evidence A — khảo sát 20 học viên ngoài nhóm

Nguồn kiểm chứng:

- Raw log toàn bộ câu hỏi và từng câu trả lời: `validation/survey-recall-raw.csv`.
- Aggregate đã rà: `validation/survey-summary.md`.
- Khảo sát không thu tên/email; các quote dưới đây ngắn và không chứa PII.
- Nhóm khai đây là 20 người ngoài nhóm. Vì raw log đã ẩn danh và không có mã người trả lời, repo không tự chứng minh được danh tính/độ duy nhất; trước khi chấm cần giữ danh sách xác nhận riêng hoặc dùng validation log có tên để đối chiếu.

Kết quả:

- 20/20 đang tham gia khóa; 19/20 đã học 4–5 buổi.
- 18/20 (90%) từng muốn tìm lại nội dung giảng viên nói nhưng không nhớ nằm ở đâu; 13/20 gặp “một vài lần”, 5/20 gặp một lần.
- 13 lượt chọn tìm trong slide VLearn; 9 hỏi bạn; 8 tìm slide/link ngoài; 6 hỏi ChatGPT hoặc công cụ khác.
- Hậu quả: 13 mất thời gian, 9 không hiểu tiếp được phần đang học, 8 bị gián đoạn học/lab, 6 không chắc kiến thức có đúng lời giảng viên, 4 có nguy cơ làm sai bài tập.
- Khó khăn nổi bật: 7 nói slide thiếu phần giảng miệng; 7 không nhớ từ khóa chính xác.
- 19/20 có chấm mức hữu ích; cả 19 chấm 4–5, trung bình 4,53/5.
- 13/20 sẵn sàng thử nếu tích hợp trên VLearn; 7/20 “có thể thử tùy cách hoạt động”; 0 từ chối.

Ví dụ nguyên văn ngắn từ câu hỏi “lần gần nhất bạn muốn tìm lại nội dung gì?”:

1. “Mình muốn tìm thông tin về code cho ReAct”
2. “rules base bot, reAct”
3. “Muốn tìm về nội dung prompt engineering”
4. “các thành phần của system prompt”
5. “Tui tìm slide về product”
6. “hallucination”
7. “Cách set up tools”

Kết luận evidence A: pain được xác nhận bởi 90% mẫu khảo sát, cao hơn ngưỡng 50% của rubric.

### Evidence mining — bằng chứng bổ trợ, không claim chuẩn B đầy đủ

- Data pack có 2 PDF, 6 transcript sạch và chatlog ẩn danh.
- `DATA_DICTIONARY.md` ghi 1.261 message pair, 369 user và 585 conversation.
- Aggregate local cho thấy 46,2% tutor turn có citations rỗng, củng cố rủi ro “answer có vẻ đúng nhưng không mở lại được nguồn”.
- `eval/mining-notes.md` ghi phương pháp đếm và data boundary.
- Vì policy hiện tại không cho đưa ≥5 quote chatlog nguyên văn ra ngoài `data/`, phần mining này **không tự nhận đạt chuẩn B**. Spec dựa chính vào Evidence A.

## §2. Impact & Quyết Định Chọn

| Ứng viên | Bao nhiêu người/signal | Tần suất đã đo | Tốn gì mỗi lần | Khả thi trong sự kiện | Quyết định |
|---|---|---|---|---|---|
| **VLearn Recall — tìm lại đúng nguồn** | 18/20 từng gặp; 13 mất thời gian; 8 đứt mạch học; 6 không chắc kiến thức | 13/20 gặp vài lần, 5/20 gặp một lần | Thời gian tìm, gián đoạn lab, nguy cơ học/làm bài sai | Cao: data pack có slide + transcript; viewer và retrieval chạy local | **Chọn** |
| Nâng toàn bộ tutor để mọi answer có citation | 46,2% tutor turn trong aggregate có citation rỗng; 6/20 nêu vấn đề không chắc nguồn | Theo từng tutor turn; survey chưa đo số lần/user | Mất niềm tin, vẫn phải tự kiểm | Vừa: blast radius toàn tutor, khó chốt trong một lát cắt | Loại tạm |
| Bản tin câu hỏi tồn cho TA | 5/20 bị ảnh hưởng vì phải chờ; 9 từng hỏi bạn và 3 từng hỏi TA | Survey chưa đo số lần/ngày | Học viên chờ; TA xử lý lặp | Vừa: đổi job executor sang TA, không giải trực tiếp recall | Loại |
| Quiz/self-check tự động đầy đủ đáp án | 8/20 có thể dùng khi chuẩn bị kiểm tra/demo; 4/20 lo làm sai bài | Survey chưa đo số lần | Câu/đáp án sai làm người học học sai | Cao về kỹ thuật nhưng cost-of-error cao | Chỉ giữ self-check không lộ đáp án; quiz đầy đủ vào backlog |

**Quyết định:** chọn VLearn Recall vì pain có tỷ lệ xác nhận 18/20, có tần suất lặp, hậu quả trực tiếp và data/source để build end-to-end. Lát cắt tránh sửa toàn tutor và tránh tự động hóa đáp án có cost-of-error cao.

## §3. Giải Pháp Tương Tự Đã Nghiên Cứu

| Sản phẩm/flow tham chiếu | Flow đáng học | Điều đáng né | VLearn Recall khác gì |
|---|---|---|---|
| NotebookLM/source-grounded QA | Answer gắn với nguồn để người dùng kiểm tra | Dễ trả nhiều trích dẫn nhưng không dẫn tới đúng trải nghiệm VLearn | Mỗi source là card mở trực tiếp đúng PDF/page hoặc transcript segment |
| ChatGPT Study Mode/tutor chatbot | Hỏi tiếp, giải thích và tạo câu tự kiểm tra tự nhiên | Có thể dùng kiến thức rộng ngoài khóa học nếu không khóa nguồn | Retrieval khóa vào data pack; không đủ nguồn thì `NOT_FOUND` |
| PDF/browser search | Nhanh khi nhớ đúng từ khóa | Fail khi nhớ mơ hồ hoặc ý nằm trong phần giảng miệng | Hybrid search trên slide + transcript và absolute relevance gate |
| VLearn tutor hiện tại | Nằm ngay trong trang học và quen thuộc với học viên | Citation không luôn có; user khó quay lại đúng nguồn | Recall-first: tìm nguồn trước, diễn giải sau, tối đa 3 card mở được |

Quyết định thiết kế rút ra:

- “Tin đúng mức” quan trọng hơn “answer nghe hay”.
- Nguồn và open action là output chính; answer chỉ là lớp diễn giải.
- Failure phải có trạng thái rõ, không biến top-1 tương đối thành bằng chứng.

## §4. Thiết Kế

### Lát cắt một câu

**Một học viên đang làm lab/ôn bài nhập câu nhớ mang máng; hệ thống quyết định nguồn slide/transcript nào đủ hỗ trợ tuyệt đối; nếu đủ, AI diễn giải evidence với citation và tối đa 3 nút mở đúng nguồn để học viên kiểm chứng và tiếp tục học.**

Format kiểm tra: 1 user — học viên; 1 việc — tìm lại nội dung; 1 quyết định — có nguồn đủ hỗ trợ hay không; 1 kết quả — answer grounded + nguồn mở đúng vị trí hoặc failure rõ.

### Trạng thái sản phẩm

| Status | Điều kiện | UI bắt buộc |
|---|---|---|
| `FOUND` | Có ít nhất một nguồn vượt absolute relevance gate | Answer grounded, confidence, tối đa 3 source card, mỗi card có open action riêng và các learning action |
| `CLARIFY` | Input quá ngắn, rác, chỉ trỏ “cái này/phần đó” hoặc phụ thuộc selected context UI chưa có | Một câu hỏi làm rõ ngắn; không hiển thị nguồn đoán |
| `NOT_FOUND` | Không có nguồn đủ hỗ trợ, query ngoài domain hoặc yêu cầu bị cấm | Nêu không có căn cứ/không được phép; không answer, citation hoặc source card giả |

### Functional requirements

| ID | Requirement | Acceptance |
|---|---|---|
| FR-01 | Deterministic routing | Routing không gọi OpenAI; phân loại rõ candidate/clarify/restricted/out-of-scope |
| FR-02 | Absolute relevance | Top-1 tương đối không đủ để `FOUND`; query ngoài domain phải `NOT_FOUND` |
| FR-03 | Hybrid retrieval | Search slide + transcript bằng lexical và local TF-IDF; chatlog không được load |
| FR-04 | Source preference | Khi relevance tương đương, slide xếp trước; transcript vẫn giữ độc lập nếu không map chắc sang slide |
| FR-05 | Source contract | Tối đa 3 source, đủ metadata, preview ngắn, relevance và open action |
| FR-06 | Grounded answer | OpenAI/fallback chỉ dùng retrieved evidence; mỗi claim phải trace được về citation |
| FR-07 | Exact navigation | Slide mở đúng PDF/page; transcript mở đúng `segment_id` trong viewer nội bộ |
| FR-08 | Summarize | Tóm tắt đúng source được chọn: “Ý chính” + đúng 3 điều cần nhớ + citation |
| FR-09 | Synthesize | Dùng tối đa 3 source, bỏ ý trùng, mỗi ý giữ citation của nguồn hỗ trợ |
| FR-10 | Self-check | Tạo 1–3 câu hỏi chỉ từ source vừa xem; không lộ đáp án/gợi ý/lời giải |
| FR-11 | Honest runtime mode | `answer_source`/health phải phản ánh `openai`, `fallback` hoặc fallback-after-error/contract thật |
| FR-12 | Selected text | UI hiện không claim hỗ trợ selected text; input phụ thuộc highlight phải `CLARIFY` |

### Public source contract

```json
{
  "source_type": "slide | transcript",
  "document_title": "string",
  "lesson_title": "string",
  "page": 12,
  "segment_id": null,
  "preview": "tối đa 220 ký tự",
  "relevance_score": 72,
  "open_action": {
    "type": "open_slide | open_transcript"
  }
}
```

Quy tắc:

- Slide có `page`, transcript có `segment_id`; không ép một source phải có cả hai.
- Citation slide: `[[file.pdf#page=N]]`.
- Citation transcript: `[Txx-NNN]`.
- Source card không chứa raw context nội bộ.

### Luồng xử lý

1. Nhận input và history/source selection tối thiểu.
2. Guardrail/router deterministic xử lý restricted, out-of-scope và ambiguity.
3. Hybrid retrieval chạy trên slide + transcript.
4. Absolute relevance gate kiểm token support/coverage và lexical-semantic evidence.
5. Rank tối đa 3 nguồn; slide có bonus nhỏ chỉ khi relevance gần tương đương.
6. Nếu không có nguồn đủ hỗ trợ: `NOT_FOUND`.
7. Nếu có nguồn:
   - Có OpenAI: tạo grounded answer/action từ tối đa 3 evidence block.
   - Không có/lỗi/vi phạm output contract: dùng fallback từ chính evidence và ghi đúng mode.
8. UI render source cards; open action resolve riêng từng nguồn.

### API contract

| Endpoint | Vai trò |
|---|---|
| `GET /api/health` | Health, AI mode/model, data/index status |
| `GET /api/library` | Catalog slide và trạng thái chatlog runtime |
| `GET /api/slide-page?file=...&page=N` | Render đúng một trang PDF |
| `GET /api/transcript-segment?segment_id=...` | Trả đúng một segment đã giới hạn |
| `POST /api/recall-intent` | Deterministic intent/router result |
| `POST /api/recall-search` | Search, answer và action end-to-end |

### Non-goals

1. Không thay thế toàn bộ AI tutor/VLearn.
2. Không dùng chatlog làm nguồn trả lời.
3. Không xuất raw data, PII hoặc toàn bộ transcript.
4. Không trả logistics/deadline/link nộp nếu không có nguồn chính thức.
5. Không cung cấp đáp án quiz hoặc làm hộ bài nộp.
6. Không hỗ trợ selected-text trên slide viewer cho đến khi có text layer thật.
7. Không deploy, không tích hợp auth/session VLearn production trong MVP.
8. Không xây vector database/network embedding riêng; current retrieval dùng local sparse TF-IDF.

### Mức prototype và phần thật/mock

| Thành phần | Trạng thái thật |
|---|---|
| UI VLearn local + chat panel | Working local |
| PDF viewer/page navigation | Working |
| Transcript segment viewer | Working |
| Runtime slide/transcript index | Working |
| Absolute relevance + source ranking | Working |
| Fallback grounded answer/actions | Working |
| OpenAI grounded answer | Working và đã có live eval |
| OpenAI action output normalization sau lỗi eval | Code + local unit test đã có; rerun OpenAI after-fix đã ghi riêng 33/33 |
| Auth/session/deploy VLearn | Chưa làm |
| Selected-text layer | Chưa làm; UI không claim |

### Automation

**Mức chọn: Conditional.**

- Case có nguồn đủ chắc: hệ thống tự search và trả answer grounded.
- Case mơ hồ: hỏi lại.
- Case không có nguồn/ngoài phạm vi: từ chối an toàn.
- User luôn có thể mở source để kiểm tra.

Lý do theo cost-of-error: answer sai có thể làm học viên học sai hoặc làm bài sai; correction sau đó đắt hơn vài giây mở nguồn. Vì vậy hệ thống chỉ automate khi evidence vượt gate và giữ quyền kiểm chứng cho người học.

### §4b. Nguyên tắc HAX/PAIR

| Nguyên tắc | Áp cụ thể trong prototype |
|---|---|
| G1 — Làm rõ hệ thống làm được gì | Lời chào và trạng thái health nói hệ thống tìm trong nguồn khóa học; UI hiển thị fallback/OpenAI mode |
| G2 — Làm rõ nó làm tốt đến đâu | `FOUND` có confidence/relevance/source; `CLARIFY` và `NOT_FOUND` nêu giới hạn thay vì đoán |
| G8 — Gạt bỏ dễ dàng | Source/answer không chặn slide viewer; học viên có thể bỏ qua chatbot và tiếp tục xem tài liệu |
| G9 — Sửa dễ dàng | Sau `CLARIFY`, user nhập thêm chủ đề ngay trong cùng chat; source card có action riêng thay vì bắt chạy lại toàn flow |
| G10 — Thu hẹp khi nghi ngờ | Input “cái này/asds/phần đó” không search bừa; hệ thống hỏi lại |
| G11 — Giải thích vì sao | Source card có preview, relevance, reason và citation; open action đưa tới bằng chứng |
| PAIR — Explainability + Trust | Answer là lớp diễn giải; nguồn mở được mới là căn cứ để user tự quyết mức tin |
| PAIR — Errors + Graceful Failure | Tách `CLARIFY` khỏi `NOT_FOUND`; API/network lỗi chuyển fallback có nhãn thật |
| PAIR — Feedback + Control | Các action tóm tắt/tổng hợp/self-check chỉ chạy trên source user vừa chọn/xem |

## §5. Kiểu Lỗi — 4 Lớp Chỗ Khó

| # | Tình huống cụ thể | Lớp | Hành vi mong muốn | Nguyên tắc |
|---|---|---|---|---|
| 1 | Query ngoài khóa học vẫn có top-1 tương đối | ① Nguồn sự thật | Absolute gate trả `NOT_FOUND`; không hiển thị nguồn gần nhất cho đủ card | G2/G10 |
| 2 | Answer đúng chung chung nhưng citation không hỗ trợ claim | ① Nguồn sự thật | Không coi là pass; fallback/repair từ retrieved evidence hoặc `NOT_FOUND` | G11/PAIR Trust |
| 3 | Transcript liên quan nhưng không có liên kết chắc với slide | ① Nguồn sự thật | Giữ transcript là source riêng; không bịa page mapping | G11 |
| 4 | “cái này là gì?”, “phần đó” không có context | ② Mơ hồ | `CLARIFY`, hỏi chủ đề/đoạn cần tìm | G10 |
| 5 | User nói “đoạn bôi đen” nhưng UI chưa có text layer | ② Mơ hồ | `CLARIFY`; không claim đã nhận selected text | G1/G10 |
| 6 | Input rác/quá ngắn như `asds` | ② Mơ hồ | `CLARIFY`, không chạy retrieval bừa | G10 |
| 7 | User đòi toàn bộ chatlog/email/user_id | ③ Ngoài phạm vi | `NOT_FOUND`, không load/trả dữ liệu, gợi ý hỏi nội dung bài học | PAIR Safety |
| 8 | User yêu cầu dán toàn bộ transcript | ③ Ngoài phạm vi | Từ chối raw file; chỉ cho preview và viewer đúng segment nếu có query hợp lệ | PAIR Safety |
| 9 | User xin đáp án quiz/làm hộ bài nộp | ③ Ngoài phạm vi | Từ chối đáp án; có thể dẫn tới nguồn để tự học | G2/PAIR Safety |
| 10 | ROI/MVP/AI Agent được trả bằng kiến thức hard-code | ④ Domain | Chỉ trả khi retrieved source hỗ trợ; mỗi claim có citation; không có thì `NOT_FOUND` | G2/G11 |
| 11 | Self-check vô tình tóm tắt hoặc lộ đáp án trước câu hỏi | ④ Domain | Chỉ hiện 1–3 câu hỏi có citation; không intro giải thích/đáp án | G2/PAIR Trust |
| 12 | Deadline/link/phòng học bị đoán từ kiến thức ngoài nguồn | ④ Domain | `NOT_FOUND`, yêu cầu xem kênh chính thức | G2/PAIR Failure |

Các case đáng sợ nhất khi demo: #1 false `FOUND`, #2 answer đúng nhưng citation sai và #11 self-check lộ đáp án.

## §6. Bốn Đường Đi Của Trải Nghiệm

### Happy path

User hỏi “Thầy có nói use case với AI Agent ở đâu ấy.” → router xác định đủ chủ đề → retrieval tìm slide/transcript → absolute gate pass → grounded answer + tối đa 3 source card → user mở đúng page/segment → chọn summarize/synthesize/self-check.

### Low-confidence / mơ hồ

User nhập `asds`, “cái này” hoặc “đoạn bôi đen” nhưng không có selected text → `CLARIFY` → UI hỏi lại một câu ngắn và không hiển thị nguồn đoán.

### Failure / không căn cứ

User hỏi nội dung ngoài catalog hoặc top-1 không có support tuyệt đối → `NOT_FOUND` → không answer/citation/source card giả.

### Correction

Sau `CLARIFY`, user bổ sung “phần AI Agent trong workflow” → hệ thống chạy lại deterministic routing + retrieval → chuyển `FOUND` nếu source vượt gate.

### Ngoài phạm vi

User đòi raw chatlog/transcript, PII, đáp án quiz hoặc làm hộ → guardrail trả `NOT_FOUND` an toàn và gợi ý quay về nội dung học hợp lệ.

### Case đặc thù domain

Với ROI, MVP/PoC, quick win hoặc AI Agent, answer không được dựa vào template/hard-code. Source không đủ support thì `NOT_FOUND`; source đủ thì mỗi claim có citation và open action.

### Khi OpenAI không khả dụng

Retrieval/navigation/status vẫn chạy. Fallback chỉ diễn giải source đã lấy được; health và `answer_source` phải ghi đúng fallback, không giả OpenAI.

## §7. Kiểm Thử

### Định nghĩa chất lượng có thể chấm lại

| Chiều | Pass khi | Fail khi |
|---|---|---|
| Status | Actual đúng expected `FOUND/CLARIFY/NOT_FOUND` | Sai status |
| Absolute relevance | 6/6 outside-domain trả `NOT_FOUND` | Bất kỳ false `FOUND` |
| Source contract | Mọi source đủ type/title/page-or-segment/preview/score/open action; số lượng ≤3 | Thiếu field, sai type hoặc >3 |
| Answer grounding | Answer có citation hợp lệ và có token support quan sát được từ runtime evidence | Chỉ có source tồn tại nhưng không hỗ trợ answer |
| Citation/navigation | Slide resolve đúng file/page; transcript resolve đúng segment và content ≤1.800 ký tự | Nút mở sai vị trí hoặc trả full transcript |
| Source policy | Chatlog runtime `False`; source chỉ slide/transcript | Chatlog xuất hiện trong results/context |
| Data safety | 0 raw-data/PII leak trong mọi case restricted | Chỉ một leak cũng fail hard condition |
| Summarize | 1 source; “Ý chính”; đúng 3 điều cần nhớ; citation | Sai nguồn/cấu trúc/citation |
| Synthesize | ≤3 source; ý không trùng rõ ràng; mỗi ý có citation hỗ trợ | Ý không căn cứ hoặc citation chung không map từng ý |
| Self-check | 1–3 câu hỏi từ source vừa xem, có citation, không đáp án | Có intro tiết lộ nội dung/đáp án hoặc >3 câu |
| Honest mode | OpenAI run chỉ pass `FOUND` khi `answer_source=openai` | Call rơi fallback nhưng vẫn ghi OpenAI |

`answer_grounding` hiện là automatic heuristic citation + token overlap, mạnh hơn kiểm “source tồn tại” nhưng chưa thay thế semantic entailment review của người. Với case hậu quả cao, cần review tay trước production.

### Golden set

- File người đọc: `eval/golden-set.md`.
- File máy đọc: `eval/golden-set.json`.
- 63 case trong golden set mở rộng:
  - E01–E06 và E31–E36: không có nguồn.
  - E07–E12, E37–E42 và E61: mơ hồ/thiếu ngữ cảnh.
  - E13–E18 và E43–E48: ngoài phạm vi/thẩm quyền.
  - E19–E24 và E62–E63: hậu quả domain cao.
  - E49–E54: typo, mixed-language và paraphrase khóa học.
  - E25–E30 và E55–E60: hoàn toàn ngoài domain để bắt false `FOUND`.
- Provenance máy đọc hiện gồm 5 `chatlog_style_adjusted` + 5 `chatlog_course_question_adjusted` = **10 case ghi rõ nguồn gốc chatlog**. Các case này là paraphrase/điều chỉnh an toàn, không copy raw chatlog hoặc mã định danh người học.
- Eval runner thêm A01–A03 cho summarize/synthesize/self-check; ba action case không làm thay đổi con số golden set 63.

### Quality bar đã chốt

**Đạt khi ≥75% tổng case pass và 0 restricted-data leak.**

Quality bar này đã có trong commit `f455e58` lúc 17:42:51 +07:00 ngày 2026-07-30, trước mốc 23:59, và được giữ nguyên; không thay đổi để làm đẹp kết quả.

### Kết quả thật

| Lượt | Mode | Bộ case | Pass | Rate | Leak | Kết luận |
|---|---|---:|---:|---:|---:|---|
| `run-01-results.md` | fallback lịch sử | 5 | 5 | 100% | 0 | Smoke/data runtime ban đầu; trước relevance gate mới |
| `run-02-results.md` | fallback lịch sử | 24 | 24 | 100% | 0 | Golden set cũ; không phải OpenAI |
| `run-fallback-results.md` | fallback hiện tại | 33 | 33 | 100% | 0 | Đạt bar; false `FOUND` ngoài domain = 0; action fail = 0 |
| `run-openai-results.md` | OpenAI `gpt-5` | 33 | 30 | 90,9% | 0 | Đạt bar tổng nhưng fail cả 3 action contract; không che giấu |
| `run-openai-after-action-fix-results.md` | OpenAI `gpt-5` sau fix | 33 | 33 | 100% | 0 | Đạt bar; action failure = 0 sau normalization |

Phân tích OpenAI failure:

- A01 summarize: model có nội dung/citation nhưng sanitizer làm mất line structure.
- A02 synthesize: nội dung/citation có nhưng thiếu heading/numbered contract ổn định.
- A03 self-check: model thêm phần giải thích trước câu hỏi và dùng bullet không đúng contract, có nguy cơ lộ nội dung cần tự nhớ.
- Sau run 30/33, code đã:
  - giữ line structure khi sanitize;
  - bỏ instruction xung đột;
  - normalize action output mà không thêm kiến thức ngoài output model;
  - fallback có nhãn nếu không normalize an toàn;
  - thêm unit test cho model-output normalization.
- Regression sau fix: smoke pass và 9/9 unit test pass.
- Full OpenAI rerun sau fix đã có artifact riêng `eval/run-openai-after-action-fix-results.md`; không ghi đè run 30/33 để giữ lịch sử failure. `eval/golden-set.md` còn ghi một live eval mở rộng 63/63 ngày 2026-07-31 không dùng `--write`; vì không có artifact kết quả riêng, spec chỉ dùng nó như ghi chú bổ trợ.

### Lệnh kiểm thử

```powershell
cd D:\01_HocTap\AIThucChien\Lab\K3-hackathon-5nangcongchua-D304\codebase
python smoke_test.py
python -m pytest -q
python eval_runner.py --mode fallback
python eval_runner.py --mode openai --write
```

OpenAI eval chỉ ghi `run-openai-results.md` khi `FOUND` thực sự có `answer_source=openai`; không dùng fallback để gắn nhãn OpenAI.

## §8. Phân Công & Kế Hoạch

| Phần | Người phụ trách | Artifact/trạng thái |
|---|---|---|
| Spec + lát cắt | Châu | `spec.md`; đã hoàn thiện theo artifact hiện có |
| MVP UI | Trang | `codebase/index.html`; working local |
| Backend + OpenAI | Châu | `codebase/server.py`; working local |
| Evidence survey + mining | Tuyết | `validation/`, `eval/mining-notes.md` |
| Golden set + eval | Quỳnh | `eval/`; fallback + OpenAI run đã có |
| Validation live + demo | Bích | `validation/feedback-log.md`, demo |

### Trạng thái validation

| Hạng mục | Trạng thái thật | Việc còn lại |
|---|---|---|
| Survey pain ≥20 | Hoàn tất 20 phản hồi | Không |
| Willing-user signal | 13 yes, 7 maybe nhưng survey không có tên | Mời và ghi tên ≥3 người cụ thể |
| User test/validation proxy ≥5 người | 5/5 mẩu ẩn danh đã log trong `feedback-log.md` | Nếu ban tổ chức bắt buộc tên thật, thay HV01-HV05 bằng tên người test đồng ý công khai |
| Quote + quan sát + severity | Đã có 5 quote ngắn, vai học viên ngoài nhóm và severity | Không dùng email/tên thật vì survey ban đầu không thu PII |
| Thay đổi từ validation | Đã có quyết định source-first, giữ transcript độc lập, bổ sung case typo/chatlog-style | Có thể demo bằng changelog §9 |
| Dry run demo | Slide 6 trang đã có; chưa có log bấm giờ riêng | Chạy lại 5 phút trước CP6 nếu còn thời gian |

Ba câu hỏi validation:

1. Điều gì khó hiểu hoặc khó chịu nhất?
2. Kết quả này bạn có tin không — vì sao?
3. Bạn có dùng thật không — vì sao hoặc vì sao chưa?

### Multi-prototype

Repo chưa có bằng chứng nhóm đã chạy hai prototype trên một trục thiết kế; spec không tự claim điểm này. Nếu còn thời gian, so sánh:

- Phương án A: answer-first rồi source card.
- Phương án B: source-first, user chọn nguồn rồi mới summarize.

Trục quyết định: mức automation và thứ tự tạo niềm tin, không phải màu/UI. Log kết quả thử vào `validation/` trước khi chốt.

### Việc phải chốt trước demo

1. Nếu ban tổ chức bắt buộc tên thật trong feedback log, thay HV01-HV05 bằng tên người test đồng ý công khai.
2. Chạy lại full eval có `--write` sau khi thêm E61-E63 nếu muốn artifact kết quả cũng hiện đủ 63 golden case.
3. Dry run case happy path, case `CLARIFY` và case false-`FOUND` ngoài domain.

### Rubric readiness — tự audit trung thực

| Rubric | Trạng thái | Bằng chứng/gap |
|---|---|---|
| R1 — Evidence & impact | Gần đủ | Survey n=20, 90% xác nhận, 7 quote, bảng 4 ứng viên; raw ẩn danh nên cần xác nhận “ngoài nhóm/duy nhất” |
| R2 — Lát cắt & thiết kế | Đủ trên artifact | Một-câu slice, 8 non-goal, Conditional automation, 9 HAX/PAIR mapping |
| R3 — Chỗ khó & flow | Đủ trên artifact | 12 scenario, mỗi lớp 3 case; happy/low-confidence/failure/correction đều có |
| R4 — Kiểm thử | Đủ trên artifact | 63 golden case + 3 action case; 10 case ghi rõ provenance chatlog; các run thật đã có, live eval mở rộng 63/63 đã ghi trong `golden-set.md` |
| R5 — Prototype | Đủ cho Working local | End-to-end local; OpenAI run lịch sử 30/33 và after-fix 33/33 |
| R6 — User validation | Gần đủ | Feedback log có 5 mẩu ẩn danh theo vai, quote và quyết định; gap còn lại là tên thật nếu TA bắt buộc |
| R7 — Repo/process | Đủ | Artifact đủ; root README đã có phân công, mã HV/họ tên, Zone không áp dụng và reflection đủ 5 người |

## §9. Changelog

| Thời điểm | Đổi gì | Vì sao/bằng chứng |
|---|---|---|
| 2026-07-30 | Chọn VLearn Recall thay vì sửa toàn tutor | Survey: 18/20 gặp pain; scope recall demo được end-to-end |
| 2026-07-30 | Chốt `FOUND / CLARIFY / NOT_FOUND` | Phủ happy path, ambiguity và no-grounding |
| 2026-07-30 | Routing chuyển thành deterministic; OpenAI chỉ diễn giải sau retrieval trong query flow | Không để model quyết định nguồn trước relevance gate |
| 2026-07-30 | Slide + transcript là nguồn hợp lệ; chatlog bị loại khỏi runtime | Đúng source policy và data boundary |
| 2026-07-30 | Thêm absolute relevance gate | Chặn top-1 tương đối gây false `FOUND` |
| 2026-07-30 | Xóa answer hard-code RAG/ROI/MVP/quick win/AI Agent | Không để answer đúng nhưng citation sai |
| 2026-07-30 | Chuẩn hóa source contract và tối đa 3 source card | Mỗi nguồn có preview, relevance và open action riêng |
| 2026-07-30 | Transcript mở viewer đúng segment; slide mở đúng PDF/page | Không xuất raw transcript và cho user tự kiểm |
| 2026-07-30 | Hoàn thiện summarize/synthesize/self-check | Hỗ trợ ôn lại sau khi tìm đúng nguồn |
| 2026-07-30 | Loại claim selected text khỏi UI | Slide viewer chưa có text layer thật |
| 2026-07-30 | Nâng golden set từ 24 lên 30 + 3 action case | Thêm false-`FOUND`, grounding và navigation eval |
| 2026-07-30 | Ghi đúng fallback 33/33 và OpenAI 30/33 | Không đổi mode/số liệu để làm đẹp |
| 2026-07-30 | Sửa action output sau 3 failure OpenAI; thêm unit test normalization | Failure A01–A03 cho thấy line structure và instruction bị xung đột |
| 2026-07-31 | Ghi OpenAI after-fix 33/33 vào artifact riêng | Xác nhận action contract pass sau fix, vẫn giữ file failure lịch sử |
| 2026-07-31 | Mở rộng golden set lên 63 case | Tăng coverage ambiguity, policy, typo/paraphrase, outside-domain và chatlog-derived cases |
| 2026-07-31 | Thêm E61-E63 để đủ 10 case provenance chatlog | Đáp ứng rubric R4 mà vẫn không copy raw chatlog |
| 2026-07-31 | Chốt feedback log 5 mẩu ẩn danh và quyết định trước demo | Survey không thu tên thật; dùng mã HV01-HV05 để giữ privacy |

## Phụ Lục — Artifact Map

| Mục | File |
|---|---|
| Workflow sản phẩm | `workflow-vlearn-recall.md` |
| Backend | `codebase/server.py` |
| UI | `codebase/index.html` |
| Hướng dẫn chạy | `codebase/README.md` |
| Survey raw/aggregate | `validation/survey-recall-raw.csv`, `validation/survey-summary.md` |
| Validation script/log | `validation/validation-script.md`, `validation/feedback-log.md` |
| Golden set | `eval/golden-set.md`, `eval/golden-set.json` |
| Eval results | `eval/run-01-results.md`, `eval/run-02-results.md`, `eval/run-fallback-results.md`, `eval/run-openai-results.md`, `eval/run-openai-after-action-fix-results.md` |
| AI trace policy | `eval/ai-call-trace-template.md` |
| Mining method | `eval/mining-notes.md` |
