# VLearn Recall - Nhóm 5 Nàng Công Chúa

VLearn Recall là prototype Working local cho hướng A - VLearn. Sản phẩm giúp học viên tìm lại đúng nguồn trong slide và transcript khóa học khi chỉ nhớ mang máng một nội dung đã học; nếu không đủ căn cứ, hệ thống hỏi lại hoặc trả `NOT_FOUND` thay vì đoán.

## Trạng Thái Nộp Bài

| Hạng mục | Trạng thái | Bằng chứng / ghi chú |
|---|---|---|
| `README.md` | Đã cập nhật | Có thành viên, mã HV và phân công có tên |
| `spec.md` | Đã có theo template AI Spec | Zone: không có/không áp dụng |
| `demo-slides.pdf` | Có | 6 trang theo `02-guide.md` §5.1 |
| `codebase/` | Có | Prototype Working local; xem `codebase/README.md` |
| `eval/` | Có | Golden set, bảng kết quả các lượt chạy và 3 case chatlog bổ sung |
| `validation/` | Có | Survey pain n=20 và feedback log 5 mẩu ẩn danh theo vai học viên ngoài nhóm |
| `reflection/` | Có | Mỗi thành viên 1 file |

## Thành Viên

**Zone:** không có/không áp dụng.  
**Trưởng nhóm:** Huỳnh Thị Hải Châu.

| Mã HV | Họ tên | Tên gọi trong artifact | Reflection |
|---|---|---|---|
| 2A202601621 | Đinh Thị Diễm Quỳnh | Quỳnh | `reflection/2A202601621-DinhThiDiemQuynh.md` |
| 2A202601311 | Hoàng Huyền Trang | Trang | `reflection/2A202601311-HoangHuyenTrang.md` |
| 2A202601029 | Đỗ Ngọc Bích | Bích | `reflection/2A202601029-DoNgocBich.md` |
| 2A202601912 | Huỳnh Thị Hải Châu | Châu | `reflection/2A202601912-HuynhThiHaiChau.md` |
| 2A202601589 | La Thị Thanh Tuyết | Tuyết | `reflection/2A202601589-LaThiThanhTuyet.md` |

## Phân Công Có Tên

| Phần | Người phụ trách | File/thư mục liên quan | Trạng thái |
|---|---|---|---|
| Product spec, lát cắt, automation, source policy | Châu | `spec.md`, `workflow-vlearn-recall.md`, `canvas.md` | Đã có |
| Backend recall, guardrail, OpenAI generation | Châu | `codebase/backend/`, `codebase/server.py` | Working local |
| MVP UI VLearn + chat panel | Trang | `codebase/index.html`, `codebase/assets/` | Đã có prototype |
| Evidence survey, mining notes, data boundary | Tuyết | `validation/survey-recall-raw.csv`, `validation/survey-summary.md`, `eval/mining-notes.md` | Đã có |
| Golden set + eval runner/results | Quỳnh | `eval/golden-set.*`, `eval/run-*.md`, `codebase/eval_runner.py` | Đã có; đã bổ sung đủ 10 case provenance chatlog |
| Validation live + demo story | Bích | `validation/feedback-log.md`, `validation/validation-script.md`, `demo-slides.pdf` | Đã có feedback log 5 mẩu |
| Repo polish + final consistency check | Cả nhóm | `README.md`, `spec.md`, `reflection/` | Đang chốt |

## Prototype

### Mức Working local

Prototype chạy local với HTML/CSS/JavaScript thuần và backend Python. Luồng chính:

1. User nhập câu hỏi nhớ mang máng.
2. Router deterministic phân loại `FOUND / CLARIFY / NOT_FOUND`.
3. Retrieval chỉ dùng slide và transcript trong `data/vlearn-pack/`.
4. Absolute relevance gate chặn top-1 tương đối khi không đủ căn cứ.
5. Nếu có nguồn, OpenAI hoặc fallback diễn giải từ tối đa 3 evidence block đã giới hạn, kèm citation và open action.

### Phần thật và mock/chưa làm

| Thành phần | Trạng thái |
|---|---|
| UI VLearn local + chatbot | Thật, working local |
| PDF viewer/page navigation | Thật, working local |
| Transcript segment viewer | Thật, giới hạn đúng một segment |
| Slide/transcript index | Thật, runtime local |
| Recall search + absolute relevance | Thật |
| OpenAI grounded answer/actions | Thật, có run OpenAI |
| Auth/session VLearn production | Chưa làm/mock ngoài scope |
| Deploy production | Chưa làm |
| Selected-text/highlight trên slide viewer | Chưa làm; hệ thống không claim đã hỗ trợ |
| Chatlog làm source trả lời | Không được dùng; chỉ mining/eval local |

## Cách Chạy

```powershell
cd D:\01_HocTap\AIThucChien\Lab\K3-hackathon-5nangcongchua-D304\codebase
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python server.py
```

Mở `http://127.0.0.1:8011`.

`OPENAI_API_KEY` chỉ để trong `.env` local, không commit. Nếu không có key, hệ thống chạy fallback có nhãn rõ mode.

## Kiểm Thử Và Eval

```powershell
cd D:\01_HocTap\AIThucChien\Lab\K3-hackathon-5nangcongchua-D304\codebase
python -m pytest -q
python smoke_test.py
python eval_runner.py --mode fallback
python eval_runner.py --mode openai
```

Kết quả đã ghi trong repo:

| File | Mode | Kết quả |
|---|---|---|
| `eval/run-fallback-results.md` | fallback | 33/33, 0 leak |
| `eval/run-openai-results.md` | OpenAI `gpt-5` lịch sử | 30/33, fail 3 action contract |
| `eval/run-openai-after-action-fix-results.md` | OpenAI `gpt-5` sau fix | 33/33, 0 leak |
| `eval/golden-set.md` | golden set mở rộng | 63 case + 3 action case; 10/63 case provenance chatlog |

## Validation

Đã có survey pain 20 phản hồi:

- 18/20 học viên từng muốn tìm lại nội dung giảng viên nói nhưng không nhớ nằm ở đâu.
- 13/20 mất thời gian tìm.
- 8/20 bị gián đoạn học/lab.
- Điểm hữu ích trung bình 4,53/5 trên 19 phản hồi hợp lệ.

Feedback log CP5 được ghi trong `validation/feedback-log.md` với 5 mẩu ẩn danh theo vai học viên ngoài nhóm, quote ngắn lấy từ raw survey/validation proxy và quyết định xử lý trước demo. Vì survey ban đầu không thu tên thật để bảo vệ quyền riêng tư, repo dùng mã HV01-HV05 thay cho tên thật.

## Việc Còn Lại Nếu Có Thêm Thời Gian

1. Chạy lại full eval có `--write` sau khi thêm E61-E63 để tạo artifact kết quả 63 case.
2. Nếu ban tổ chức bắt buộc tên thật trong feedback log, thay HV01-HV05 bằng tên người test đã đồng ý công khai.
3. Thêm text layer thật cho slide viewer để hỗ trợ selected text.
