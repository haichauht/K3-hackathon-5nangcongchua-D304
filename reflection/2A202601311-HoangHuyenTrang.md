# Reflection - Hoàng Huyền Trang

**Mã HV:** 2A202601311  
**Dự án:** VLearn Recall

## 1. Vai Trò Của Mình

Mình phụ trách MVP UI VLearn local và trải nghiệm chat panel. Phần của mình tập trung vào việc để học viên có thể nhập câu hỏi, nhìn thấy trạng thái trả lời, mở đúng source card và tiếp tục học mà không bị chatbot che mất flow chính.

## 2. Phần Mình Đã Làm

- Xây giao diện chính trong `codebase/index.html`.
- Tách CSS/JS trong `codebase/assets/` để UI dễ đọc và dễ kiểm tra.
- Thiết kế chat panel hiển thị rõ `FOUND / CLARIFY / NOT_FOUND`.
- Hiển thị source card, confidence/relevance và action mở slide/transcript.
- Giữ selected-text/highlight ngoài scope vì viewer chưa có text layer thật.

## 3. AI Đã Hỗ Trợ Như Thế Nào

AI hỗ trợ mình dựng cấu trúc HTML/CSS/JS, gợi ý cách chia module frontend và kiểm tra contract payload giữa frontend và backend. Mình vẫn cần hiểu rõ UI đang gửi gì cho API và vì sao không được giả lập dữ liệu khi backend chưa trả về.

## 4. Case Fail Mình Học Được

Ban đầu UI rất dễ làm người dùng tưởng hệ thống hiểu “đoạn bôi đen” hoặc “phần này” dù prototype chưa có selected text thật. Mình học được rằng UI không nên hứa nhiều hơn năng lực hệ thống; khi thiếu context, trạng thái đúng là `CLARIFY`.

## 5. Điều Cần Làm Tiếp

- Test UI với người ngoài nhóm để xem source card và action có dễ hiểu không.
- Cải thiện trạng thái loading/error nếu backend hoặc OpenAI chậm.
- Nếu có thêm thời gian, thêm text layer thật cho slide viewer để hỗ trợ selected text.
