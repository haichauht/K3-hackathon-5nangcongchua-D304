# AI SPEC - VLearn Recall · Nhóm 5 nang cong chua · Zone TBD

Hướng: [x] A - VLearn  [ ] B - Trợ lý Học viên  [ ] C - Làn mở  
Loại: [ ] Tối ưu tính năng có sẵn  [x] Tính năng mới

## Data Boundary

Nhóm áp dụng rule strict: **không đưa dữ liệu trong folder `data/` ra bất cứ folder ngoài nào khác**.

Spec này không ghi raw transcript, raw chatlog, snippet thật, mã đoạn/mã turn thật hoặc safe index trích xuất từ `data/`. MVP được phép đọc `data/vlearn-pack` tại runtime; output cho người học chỉ hiện câu trả lời ngắn và đường dẫn tới trang slide. Survey người học được lưu riêng tại `validation/survey-recall-raw.csv`; spec chỉ dùng số tổng hợp từ `validation/survey-summary.md`.

## §1. User & Job

- **Job executor + workflow:** Học viên khóa AI Thực Chiến đang làm lab, ôn lại bài, chuẩn bị bài tập/báo cáo/quiz hoặc quay lại một khái niệm đã nghe trong lớp nhưng chỉ nhớ mơ hồ.
- **Workflow hiện tại:**
  1. Nhớ một mảnh nội dung, ví dụ "hình như thầy có nói phần này".
  2. Tự lục slide trên VLearn, tìm link tài liệu ngoài, hỏi bạn/TA, hỏi ChatGPT hoặc xem ghi chú cá nhân.
  3. Nếu slide không có đủ phần giảng miệng hoặc không nhớ đúng từ khóa, việc tìm lại bị kéo dài.
  4. Nếu câu trả lời không có nguồn để mở lại, học viên vẫn phải tự kiểm chứng.
- **Core JTBD:** Khi tôi chỉ nhớ mang máng một nội dung đã học, tôi muốn tìm lại đúng trang nguồn liên quan nhanh, để có thể ôn lại và tiếp tục làm bài mà không học sai hoặc mất nhiều thời gian.
- **Problem statement:** Học viên chỉ nhớ một phần nội dung đã học nhưng không biết nó nằm ở buổi học hoặc trang slide nào; việc tự tìm lại mất thời gian, làm gián đoạn học/lab và khiến họ không chắc kiến thức tìm được có đúng với lời giảng viên không.
- **Evidence khảo sát:** `validation/survey-summary.md` tổng hợp 20 phản hồi.
  - 20/20 người trả lời đang tham gia khóa; 19/20 đã tham gia 4-5 buổi.
  - 18/20 từng muốn tìm lại nội dung giảng viên nói nhưng không nhớ nằm ở buổi/slide/tài liệu nào; 13/20 gặp một vài lần.
  - 13 lượt chọn "tìm trong slide trên VLearn", 9 hỏi bạn bè, 8 tìm slide/link bên ngoài, 6 hỏi ChatGPT hoặc công cụ AI khác.
  - Tác động lớn nhất: 13 mất thời gian tìm kiếm, 9 không hiểu tiếp được phần đang học, 8 bị gián đoạn học/lab, 6 không chắc kiến thức có đúng với lời giảng viên.
  - Khó khăn chính: 7 chọn "slide không chứa đầy đủ phần giảng miệng", 7 chọn "không nhớ từ khóa chính xác".
  - 19/20 có chấm mức hữu ích; cả 19 đều chấm 4-5, điểm trung bình 4.53/5. 13/20 sẵn sàng thử nếu tích hợp trên VLearn, 7/20 có thể thử tùy cách hoạt động.
- **Evidence data pack:** `data/vlearn-pack/README.md` cho biết pack có 2 slide PDF, 6 transcript sạch và 2,522 dòng chatlog đã ẩn danh. `data/vlearn-pack/chatlog/DATA_DICTIONARY.md` ghi 1,261 message pair, 369 user, 585 hội thoại; 46.2% tutor turn có citations rỗng, cho thấy nhu cầu grounding/nguồn mở lại là có thật. `eval/mining-notes.md` ghi phương pháp mining tại chỗ và luật không copy raw data.

## §2. Impact & Quyết Định Chọn

| Ứng viên | Bằng chứng & quy mô | Tốn gì mỗi lần | Khả thi | Quyết định |
|---|---|---|---|---|
| VLearn Recall - tìm lại đúng trang slide | 18/20 người khảo sát từng gặp; 13 mất thời gian; 8 bị gián đoạn học/lab; 15 nói sẽ dùng khi đang làm lab và nhớ giảng viên từng nói về lỗi đang gặp | Mất thời gian, đứt mạch học, không chắc nguồn, có nguy cơ học sai | Cao: build được bằng viewer + Python backend + OpenAI + data pack tại runtime | **Chọn** |
| Tối ưu toàn bộ AI tutor hiện tại để luôn trả lời có citation | Chatlog có 46.2% tutor turn citations rỗng; pain liên quan niềm tin xuất hiện ở 6/20 survey | Giảm niềm tin vào tutor, vẫn phải tự kiểm | Vừa: đụng toàn bộ hành vi tutor, blast radius lớn hơn 1 lát cắt recall | Loại tạm |
| Bản tin câu hỏi tồn cho TA | 5/20 bị ảnh hưởng vì phải chờ bạn bè/TA; 3 từng hỏi TA/giảng viên để tìm lại | TA xử lý lặp, học viên chờ | Vừa: user chính chuyển sang TA, không trực tiếp giải job của học viên | Loại |
| Quiz/kiểm tra hiểu bài tự động | 8/20 sẽ dùng khi chuẩn bị kiểm tra/demo; 4/20 nêu nguy cơ làm sai bài tập | Nếu sai câu hỏi/đáp án có thể làm học viên học sai | Cao nhưng cost-of-error lớn hơn; phù hợp bước phụ sau khi đã tìm đúng nguồn | Backlog |

## §3. Giải Pháp Tương Tự Đã Nghiên Cứu

| Sản phẩm/flow tham chiếu | Đáng học | Đáng né | VLearn Recall khác gì |
|---|---|---|---|
| Source-grounded QA | Gắn câu trả lời với nguồn để user tự kiểm | Dễ thành chat dài nếu output quá nhiều nguồn | Chỉ trả tóm tắt ngắn + tối đa 3 trang slide có thể mở ngay |
| Study/tutor chatbot | Có thể hỏi lại và giải thích theo ngữ cảnh học | Nếu không grounding, câu trả lời có vẻ đúng nhưng không biết mở lại ở đâu | Recall trước, giải thích sau; trạng thái rõ `FOUND / CLARIFY / NOT_FOUND` |
| Search trong PDF/browser | Nhanh khi nhớ đúng từ khóa | Fail khi user nhớ mơ hồ hoặc slide thiếu phần giảng miệng | AI rewrite câu hỏi mơ hồ, dùng transcript/chatlog làm bằng chứng nội bộ, nhưng dẫn người học về slide |
| VLearn tutor hiện tại | Nằm đúng nơi học viên đang đọc tài liệu | Chatlog cho thấy citation không luôn có; user khó quay lại nguồn nếu chỉ hỏi chat | Bổ sung panel VLearn Recall bên cạnh slide viewer thật |

## §4. Thiết Kế

- **Lát cắt một câu:** Một học viên đang ôn/làm lab nhập câu nhớ mang máng; AI quyết định `FOUND / CLARIFY / NOT_FOUND`; nếu `FOUND` thì trả câu trả lời ngắn kèm tối đa 3 nút mở trang slide trong VLearn viewer; học viên nhảy tới đúng trang để tự kiểm và ôn lại.
- **Non-goals:**
  1. Không build tutor thay thế toàn bộ VLearn.
  2. Không hiển thị transcript/chatlog như nguồn cho người học; hai nguồn này chỉ dùng nội bộ để hỗ trợ grounding/retrieval.
  3. Không xuất raw chatlog, raw transcript, PII, mã định danh hoặc dữ liệu có thể suy ngược danh tính.
  4. Không trả lời logistics/deadline/link nộp nếu không có nguồn chính thức trong bài học.
  5. Không cho đáp án quiz, làm hộ bài nộp hoặc tự sinh kiến thức mới khi không tìm được nguồn.
- **Mức MVP:** [x] Working. `codebase/index.html` mô phỏng giao diện học VLearn với sidebar Day01/Day02 từ PDF thật, slide viewer render từng trang PDF thật, và chat panel VLearn Recall. `codebase/server.py` là backend Python đọc `data/vlearn-pack` tại runtime, gọi OpenAI khi có `OPENAI_API_KEY`, search slide page + evidence nội bộ, và trả payload public chỉ gồm answer, confidence, source map slide, file/page/url. Phần chưa phải production: chưa tích hợp auth/session thật của VLearn, chưa deploy, chưa có vector database riêng.
- **Automation:** Conditional. AI tự trả lời khi có slide đủ chắc; hỏi lại khi input quá mơ hồ; từ chối khi ngoài phạm vi, đòi dữ liệu bị hạn chế hoặc câu trả lời có nguy cơ bịa. Lý do: sai nguồn/sai kiến thức có thể làm học viên học sai hoặc làm bài sai, nên hệ thống phải ưu tiên dẫn về nguồn mở được thay vì trả lời chắc quá mức.

### §4b. Nguyên Tắc Áp Dụng

| Nguyên tắc | Áp cụ thể vào MVP |
|---|---|
| G1 - Làm rõ hệ thống làm được gì | Lời chào trong chat nói chatbot tìm trong nguồn bài học thật và dẫn tới đúng trang slide để mở lại. |
| G2 - Làm rõ nó làm tốt đến đâu | `FOUND` hiển thị confidence và top trang slide; `CLARIFY`/`NOT_FOUND` nói rõ giới hạn thay vì trả lời lấp lửng. |
| G10 - Thu hẹp phạm vi khi nghi ngờ | Input kiểu "cái này", "phần đó", hoặc rác ngắn vào `CLARIFY` và hỏi thêm từ khóa/chủ đề. |
| G11 - Giải thích vì sao | Mỗi source map public chỉ ra trang slide nào liên quan và lý do khớp ở mức ngắn. |
| PAIR - Trust đúng mức | User có nút `Mở slide trang N` để tự kiểm trên slide thật; không bị buộc tin câu trả lời của AI. |
| PAIR - Graceful failure | Raw data/PII/out-of-scope/đáp án kiểm tra vào `NOT_FOUND` với gợi ý hỏi lại hợp lệ. |

## §5. Kiểu Lỗi - 4 Lớp Chỗ Khó

| # | Tình huống cụ thể | Lớp | Hành vi mong muốn | Nguyên tắc |
|---|---|---|---|---|
| 1 | User hỏi chủ đề học tập đủ rõ, ví dụ nhớ về AI Agent/use case | ① nguồn sự thật | `FOUND`, trả câu trả lời ngắn và tối đa 3 trang slide mở được | G2/G11 |
| 2 | User hỏi kiểu "hình như thầy có nói phần AI Agent ở đâu ta" | ① nguồn sự thật + ② mơ hồ nhẹ | Nếu có keyword học tập đủ rõ thì vẫn tìm và dẫn trang slide; không trả lời bằng tên transcript/chatlog | G10/G11 |
| 3 | User hỏi slide/trang không tồn tại, ví dụ trang 999 | ① nguồn sự thật | `NOT_FOUND`, không đoán nội dung trang | G2 |
| 4 | User gõ "cái này là gì" nhưng không có selected text/context | ② mơ hồ | `CLARIFY`, hỏi thêm chủ đề hoặc đoạn cần tìm | G10 |
| 5 | User gõ rác/quá ngắn | ② mơ hồ | `CLARIFY`, không search bừa | G10 |
| 6 | User đòi raw chatlog/transcript hoặc toàn bộ file | ③ ngoài phạm vi | `NOT_FOUND`, nêu luật không xuất raw data | PAIR safety |
| 7 | User hỏi danh tính/email/user_id thật | ③ ngoài phạm vi | Từ chối, không suy ngược danh tính | PAIR safety |
| 8 | User đòi đáp án quiz/làm hộ bài nộp | ③ ngoài phạm vi | Từ chối làm hộ; có thể gợi ý mở nguồn học để tự làm | PAIR safety |
| 9 | User hỏi deadline/link nộp/phòng học | ① không có nguồn + ④ hậu quả thật | `NOT_FOUND`, yêu cầu kiểm kênh chính thức, không bịa logistics | G2/PAIR |
| 10 | User hỏi kiến thức dễ học sai như ROI, MVP vs PoC, khi nào dùng AI Agent | ④ domain | Chỉ trả khi có slide phù hợp; câu trả lời phải có nút mở nguồn | G2/G11 |

## §6. Bốn Đường Đi Của Trải Nghiệm

- **Happy path:** User hỏi chủ đề đủ rõ; backend gọi OpenAI để phân loại/rewrite, search slide page trong `data/vlearn-pack/slides` và evidence nội bộ trong transcript/chatlog; UI trả `FOUND`, câu trả lời ngắn, tối đa 3 nút `Mở slide trang N`; user bấm để viewer nhảy tới đúng trang.
- **Low-confidence / mơ hồ:** User gõ `asds`, "cái này", "phần đó" mà không có context; hệ thống `CLARIFY` và hỏi thêm chủ đề/từ khóa/slide.
- **Failure / không căn cứ:** User hỏi chủ đề ngoài catalog hoặc trang không tồn tại; hệ thống `NOT_FOUND`, không bịa.
- **Correction:** User bổ sung từ khóa sau `CLARIFY`; hệ thống chạy lại intent/search và chuyển sang `FOUND` nếu có trang slide đủ chắc.
- **Ngoài phạm vi:** User đòi email, danh tính, raw chatlog/transcript, đáp án quiz hoặc logistics không có nguồn; hệ thống từ chối an toàn.
- **Case đặc thù domain:** Với nội dung có thể ảnh hưởng điểm/lab/bài nộp, output phải gắn với trang slide mở được; không có nguồn thì không trả lời chắc.

## §7. Kiểm Thử

| Chiều | Định nghĩa pass/fail |
|---|---|
| Grounding public | Case `FOUND` pass khi public result chỉ là slide, có `file`, `page`, `url` hợp lệ và nút mở đúng trang; không hiển thị transcript/chatlog cho người học. |
| Không leak data | Case restricted pass khi không xuất raw data, PII, mã định danh, raw transcript/chatlog hoặc snippet dài. Điều kiện cứng: 0 lỗi. |
| Status đúng | Expected `FOUND / CLARIFY / NOT_FOUND` phải khớp golden set. |
| Clarify đúng lúc | Case mơ hồ phải hỏi lại bằng câu ngắn, không đoán chủ đề. |
| Not-found đúng lúc | Case ngoài phạm vi/không có nguồn phải `NOT_FOUND`. |
| Output vừa đủ | Tóm tắt ngắn, nêu giới hạn, không dán nội dung dài. |
| Navigation | Nút mở nguồn đưa viewer tới đúng PDF/page; số trang trên viewer và chip "Trang slide" cập nhật theo click/scroll. |

- **Golden set:** `eval/golden-set.md` - 24 câu, phủ 4 nhóm tình huống rủi ro, mỗi nhóm 6 câu. 18/24 câu bắt nguồn từ quan sát thực tế/chatlog style/team self-use adjusted.
- **Quality bar chốt:** đạt khi >=75% case pass và 0 restricted-data leak.
- **Run 01:** `eval/run-01-results.md` - fallback local smoke 5/5 pass, phát hiện 2 PDF thật, mỗi PDF 29 trang, không leak.
- **Run 02:** `eval/run-02-results.md` - mode `openai`, model `gpt-5`, 24/24 pass, pass rate 100.0%, restricted-data leak 0.
- **AI trace:** `eval/ai-call-trace-template.md` ghi decision trung tâm và format trace không chứa API key/raw data.

## §8. Phân Công & Kế Hoạch

| Phần | Người phụ trách |
|---|---|
| Spec + lát cắt | Châu |
| MVP UI | Trang |
| Backend Python + OpenAI call | Châu |
| Evidence survey + mining tại chỗ | Tuyết |
| Golden set + eval | Quỳnh |
| Validation live + demo | Bích |

- **Survey:** đã có 20 phản hồi ẩn danh trong `validation/survey-recall-raw.csv`.
- **Validation CP5 còn cần:** ít nhất 5 người ngoài nhóm dùng MVP thật, ghi vào `validation/feedback-log.md` với tên/vai, task/input, quan sát, quote ngắn, severity và quyết định.
- **Willing user signal:** 13/20 survey trả lời sẵn sàng thử; 7/20 có thể thử tùy cách hoạt động. Nhóm cần chuyển signal này thành danh sách người test có tên trước CP5.

## §9. Changelog

| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
| 2026-07-30 | Đổi chatbot thành VLearn Recall, giữ web là VLearn | Feature hỗ trợ VLearn thật, không đổi brand web chính |
| 2026-07-30 | Thêm `FOUND / CLARIFY / NOT_FOUND` | Phủ happy path, mơ hồ, không căn cứ |
| 2026-07-30 | Thêm backend Python `codebase/server.py` gọi OpenAI cho intent classification/query rewrite/grounded answer | Đáp ứng yêu cầu có AI thật nhưng không lộ API key trong frontend |
| 2026-07-30 | Nối MVP với PDF, transcript và chatlog thật tại runtime | Dùng data thật nhưng không copy dữ liệu ra ngoài `data/` |
| 2026-07-30 | Chỉnh public output thành slide-only; transcript/chatlog chỉ dùng làm evidence nội bộ | Người học cần câu trả lời + đường dẫn mở slide, không cần thấy nguồn raw |
| 2026-07-30 | Thêm custom slide viewer render từng trang và sync số trang khi scroll/click | Đáp ứng flow giống VLearn thật, mở được đúng trang nguồn |
| 2026-07-30 | Import survey raw vào `validation/survey-recall-raw.csv` và thêm summary | Bổ sung bằng chứng pain/impact theo rubric |
