# Workflow Hoàn Chỉnh - VLearn Recall

Mục tiêu: người học chỉ nhớ mang máng một nội dung đã học; hệ thống tìm đúng nguồn và hỗ trợ ôn lại nhanh.

## Data Boundary

Bản repo này không copy dữ liệu từ `data/` sang folder khác. MVP đọc `data/vlearn-pack` trực tiếp tại runtime qua backend Python, nhưng không ghi raw/snippet/index trích xuất ra ngoài `data/`.

## 1. User Input

Người học nhập câu hỏi tự nhiên, ví dụ:

```text
Thầy có nói use case với AI Agent ở đâu ấy.
```

## 2. Hiểu Câu Hỏi Và Routing

Router deterministic xác định:

- Chủ đề chính.
- Entity/khái niệm.
- Ý định: tìm lại nguồn đã học, không phải hỏi ngoài phạm vi.

OpenAI không tham gia bước routing hiện tại. Nó chỉ được gọi sau retrieval để diễn giải evidence hoặc thực hiện action học tập.

## 3. Gate: Câu Hỏi Đã Đủ Rõ Chưa?

| Điều kiện | Trạng thái | Hành vi |
|---|---|---|
| Có chủ đề/keyword đủ tìm nguồn | FOUND candidate | Chuyển sang search |
| Quá mơ hồ hoặc phụ thuộc selected context chưa có | CLARIFY | Hỏi lại 1 câu, đưa lựa chọn |
| Đòi raw data, thông tin định danh, hoặc ngoài phạm vi | NOT_FOUND | Từ chối an toàn, gợi ý hỏi lại hợp lệ |

## 4. Semantic / Hybrid Search

MVP search trên slide PDF và transcript `.md` bằng lexical + local TF-IDF. Absolute relevance gate yêu cầu nguồn có hỗ trợ quan sát được; không lấy top-1 tương đối nếu query ngoài domain. Khi slide và transcript có relevance tương đương, slide được ưu tiên nhẹ. Chatlog không được load vào runtime answer.

## 5. Chọn Top Kết Quả Phù Hợp

Tối đa 3 kết quả:

- `source_type`.
- `document_title` hoặc `lesson_title`.
- `page` hoặc `segment_id`.
- Preview ngắn.
- Relevance score.
- Open action riêng.

Slide mở đúng PDF/page. Transcript mở viewer nội bộ tới đúng segment; endpoint không trả toàn bộ transcript.

## 6. AI Hỏi User Muốn Tiếp Tục Thế Nào

Ba lựa chọn:

1. Tóm tắt nguồn phù hợp nhất.
2. Tổng hợp các nguồn liên quan.
3. Tạo 1-3 câu tự kiểm tra từ các nguồn vừa xem.

Mở nguồn được đặt trực tiếp trên từng source card, không dùng một nút mở chung.

## 7A. Tóm Tắt 1 Nguồn

Output:

- Ý chính.
- Đúng 3 điều cần nhớ.
- Citation nguồn được chọn.
- Không output nguyên văn dài.

## 7B. Tổng Hợp Theo Vấn Đề

Output:

- Mỗi ý gắn với một source ID.
- Loại bỏ trùng lặp.
- Không trộn ý không có căn cứ.

## 7C. Mở Nguồn

User tự xem slide page hoặc transcript segment trong viewer nội bộ.

## 8. Kiểm Tra Nhanh Đã Hiểu Chưa

Tạo 1-3 câu hỏi chỉ từ tối đa 3 nguồn vừa xem. Không tiết lộ đáp án ngay.

## 9. Kết Quả Cuối

Người học:

- Tìm đúng nội dung.
- Hiểu lại chủ đề.
- Tiết kiệm thời gian ôn tập.
- Tin đúng mức vì có nguồn.

## Ba Trạng Thái Hệ Thống

| Status | Meaning | UI behavior |
|---|---|---|
| FOUND | Có nguồn vượt absolute relevance gate | Hiện top 1-3 source card + preview + open action |
| CLARIFY | Cần hỏi lại | Hiện các lựa chọn làm rõ |
| NOT_FOUND | Không có căn cứ hoặc không được phép | Từ chối an toàn + gợi ý hỏi lại |
