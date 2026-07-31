# Reflection - Huỳnh Thị Hải Châu

**Mã HV:** 2A202601912  
**Dự án:** VLearn Recall

## 1. Vai Trò Của Mình

Mình phụ trách phần product spec, prototype UI và logic demo cho tính năng VLearn Recall. Phần mình làm tập trung vào lát cắt: học viên hỏi một câu nhớ mang máng, hệ thống tìm nguồn phù hợp hoặc hỏi lại/từ chối khi không đủ căn cứ.

## 2. Phần Mình Đã Làm

- Đọc đề bài, guide, rubric và template spec.
- Thiết kế workflow `FOUND / CLARIFY / NOT_FOUND`.
- Xây prototype `codebase/index.html` với chatbot VLearn Recall nằm trong giao diện VLearn.
- Chỉnh prototype theo rule: không copy dữ liệu trong `data/` ra folder ngoài; source catalog hiện là mock.
- Draft `spec.md`, `eval/`, `validation/`, `demo-slides.md`.

## 3. AI Đã Hỗ Trợ Như Thế Nào

AI hỗ trợ mình tổ chức yêu cầu từ các file `.md`, gợi ý cấu trúc spec theo rubric, viết prototype HTML/CSS/JS, và tạo bộ golden set mock ban đầu. Mình vẫn cần hiểu rõ logic `FOUND / CLARIFY / NOT_FOUND` và rule data boundary để giải thích khi CP5/CP6.

## 4. Case Fail Mình Học Được

Prototype ban đầu dễ trộn giữa "dùng data để hiểu bài toán" và "copy dữ liệu ra artifact". Sau khi siết rule, mình học được rằng với data nhạy cảm, prototype nên đọc dữ liệu tại runtime hoặc dùng mock catalog, không commit dữ liệu dẫn xuất nếu nhóm chưa cho phép.

## 5. Điều Cần Làm Tiếp

- Thêm AI call thật cho bước phân loại intent hoặc rewrite query.
- Nếu cần dùng data thật, thiết kế runtime đọc trực tiếp trong `data/` và không ghi bản sao ra ngoài.
- Test với người học thật và ghi feedback log.
