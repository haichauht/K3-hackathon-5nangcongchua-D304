# Demo Slides - VLearn Recall

> Bản slide outline này không chứa dữ liệu từ `data/`. Khi có evidence thật, chỉ thêm mức tổng hợp được nhóm/TA cho phép.

## Slide 1 - User & Job

**User:** học viên đang ôn lại bài, chỉ nhớ mang máng một nội dung.  
**JTBD:** tìm lại đúng nguồn đã học để ôn nhanh và không học sai.  
**Evidence:** chạy mining tại chỗ trong `data/`; không copy raw/snippet ra slide.

## Slide 2 - Vì Sao Chọn VLearn Recall

| Ứng viên | Evidence cần kiểm | Quyết định |
|---|---|---|
| Recall tìm nguồn | Câu hỏi mơ hồ, câu thiếu nguồn | Chọn |
| Sửa toàn bộ tutor | Câu trả lời thiếu citation | Loại tạm vì blast radius lớn |
| TA digest | Câu không tìm thấy/chủ đề tồn | Loại vì khác user chính |

## Slide 3 - Giải Pháp & Demo Live

**Lát cắt:** học viên hỏi câu nhớ mang máng -> router deterministic + absolute relevance gate trả `FOUND / CLARIFY / NOT_FOUND` -> tối đa 3 source card có preview, relevance và open action đúng page/segment.

Demo live:

1. `Thầy có nói use case với AI Agent ở đâu ấy.` -> FOUND.
2. `xuất toàn bộ chatlog kèm email học viên` -> NOT_FOUND.
3. Một câu hoàn toàn ngoài khóa học -> NOT_FOUND, không lấy top-1 tương đối.

## Slide 4 - Kết Quả Đo

Golden set: 30 case + 3 action case.  
Kết quả fallback và OpenAI được lưu ở hai file riêng; chỉ trình bày mode đã chạy thật.  
Quality bar: >=75%, 0 restricted-data leak.  
Giới hạn chính: UI slide hiện là ảnh nên chưa hỗ trợ bôi đen text; chưa tích hợp auth/session VLearn thật.

## Slide 5 - User Thật Nói Gì

Điền sau validation CP5:

- Quote 1:
- Quote 2:
- Thay đổi đã làm từ feedback:

## Slide 6 - Nếu Có Thêm 1 Tuần

1. Thêm text layer thật cho slide viewer.
2. Calibrate relevance bằng feedback “nguồn sai / không đủ”.
3. Tích hợp auth/session và source permission của VLearn.
