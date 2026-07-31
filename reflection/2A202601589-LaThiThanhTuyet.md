# Reflection - La Thị Thanh Tuyết

**Mã HV:** 2A202601589  
**Dự án:** VLearn Recall

## 1. Vai Trò Của Mình

Mình phụ trách phần evidence survey, mining notes và data boundary cho VLearn Recall. Phần của mình giúp nhóm chứng minh pain recall là vấn đề thật, đồng thời giữ ranh giới dữ liệu để không đưa chatlog hoặc raw transcript vào phần trả lời của prototype.

## 2. Phần Mình Đã Làm

- Rà câu hỏi khảo sát và tổng hợp survey pain n=20 trong `validation/survey-summary.md`.
- Kiểm tra raw survey ẩn danh tại `validation/survey-recall-raw.csv`.
- Ghi lại các số chính: 18/20 từng gặp pain, 13/20 mất thời gian, 8/20 bị gián đoạn học/lab.
- Phối hợp viết `eval/mining-notes.md` để mô tả cách dùng chatlog cho mining/eval local.
- Rà lại data boundary trong `spec.md`: slide/transcript là nguồn trả lời; chatlog không được load vào retrieval/runtime answer.

## 3. AI Đã Hỗ Trợ Như Thế Nào

AI hỗ trợ mình gom dữ liệu khảo sát thành bảng số liệu, chọn quote ngắn không chứa thông tin nhạy cảm, và phát hiện chỗ nào trong spec dễ claim quá mức so với bằng chứng đang có. Mình vẫn phải kiểm tra lại raw survey để đảm bảo số liệu đưa vào spec và slide không bị phóng đại.

## 4. Case Fail Mình Học Được

Điểm dễ sai nhất là trộn “dữ liệu dùng để hiểu pain” với “nguồn để AI trả lời học viên”. Nếu chatlog được dùng làm source trả lời, sản phẩm có thể lộ dữ liệu hoặc tạo cảm giác đang suy ngược danh tính. Vì vậy mình học được rằng data boundary phải được viết rõ ngay từ spec, không để tới lúc demo mới giải thích.

## 5. Điều Cần Làm Tiếp

- Nếu có thêm dữ liệu validation thật có tên, cập nhật lại feedback log theo yêu cầu CP5.
- Bổ sung thêm vài case chatlog-style nhưng không copy raw chatlog.
- Kiểm tra lại các slide/spec trước demo để mọi con số đều trỏ về file nguồn trong repo.
