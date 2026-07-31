# Reflection - Đinh Thị Diễm Quỳnh

**Mã HV:** 2A202601621  
**Dự án:** VLearn Recall

## 1. Vai Trò Của Mình

Mình phụ trách golden set và eval cho VLearn Recall. Phần của mình giúp nhóm kiểm tra sản phẩm không chỉ chạy được happy path mà còn xử lý được câu mơ hồ, câu ngoài phạm vi, câu dễ gây false `FOUND`, câu có hậu quả domain cao và các action học tập.

## 2. Phần Mình Đã Làm

- Xây và rà `eval/golden-set.md` cùng `eval/golden-set.json`.
- Chia case theo nhóm lỗi: không có nguồn, mơ hồ, ngoài phạm vi, hậu quả domain cao, typo/paraphrase và outside-domain.
- Bổ sung E61-E63 để golden set có đủ 10 case ghi rõ provenance chatlog mà không copy raw chatlog.
- Ghi nhận kết quả các lượt chạy trong `eval/run-*.md`.
- Theo dõi quality bar: đạt khi >=75% tổng case pass và 0 restricted-data leak.
- Giữ lại run OpenAI lịch sử 30/33 thay vì ghi đè, để nhóm phân tích lỗi trung thực.

## 3. AI Đã Hỗ Trợ Như Thế Nào

AI hỗ trợ mình biến các rủi ro trong spec thành case kiểm thử cụ thể, rà lại expected status, và đọc bảng kết quả để phát hiện lỗi action contract. Phần mình cần tự chịu trách nhiệm là không đổi nhãn golden set chỉ để làm đẹp số liệu và không đưa raw chatlog vào artifact.

## 4. Case Fail Mình Học Được

Các case action fail cho thấy eval phải kiểm cả cấu trúc output, không chỉ kiểm API trả `FOUND`. Nếu `self_check` vô tình lộ đáp án hoặc `summarize` mất format, người học vẫn có thể bị dẫn sai dù retrieval đúng.

## 5. Điều Cần Làm Tiếp

- Chạy lại full eval có `--write` sau khi thêm E61-E63 để artifact kết quả hiện đủ 63 golden case.
- Nếu có thêm thời gian, thêm một cột review tay cho các case domain có hậu quả cao.
- Tách rõ trong demo: run lịch sử 30/33 là failure trung thực, run after-fix 33/33 là kết quả sau khi sửa action contract.
