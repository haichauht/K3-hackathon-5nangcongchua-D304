# Reflection - Huỳnh Thị Hải Châu

**Mã HV:** 2A202601912  
**Dự án:** VLearn Recall

## 1. Vai Trò Của Mình

Mình phụ trách product spec, lát cắt sản phẩm, source policy và phần backend/AI chính của VLearn Recall. Phần của mình tập trung vào quyết định quan trọng nhất của sản phẩm: khi nào hệ thống được trả lời, khi nào phải hỏi lại, và khi nào phải từ chối vì không có căn cứ.

## 2. Phần Mình Đã Làm

- Đọc đề bài, guide, rubric và template spec để chốt hướng A - VLearn.
- Viết và cập nhật `spec.md` theo workflow `FOUND / CLARIFY / NOT_FOUND`.
- Thiết kế data boundary: slide/transcript là nguồn trả lời, chatlog chỉ dùng cho mining/eval local.
- Phối hợp xây backend recall, guardrail, retrieval, source contract và OpenAI grounded answer/action.
- Rà soát kết quả eval, ghi trung thực run OpenAI fail 30/33 và after-fix 33/33.

## 3. AI Đã Hỗ Trợ Như Thế Nào

AI hỗ trợ mình hệ thống hóa yêu cầu từ guide/rubric, gợi ý cấu trúc spec, rà các chỗ mâu thuẫn giữa spec và artifact, và hỗ trợ viết/kiểm tra code backend. Mình vẫn phải tự nắm logic sản phẩm, đặc biệt là vì sao VLearn Recall chọn conditional automation thay vì tự động trả lời mọi câu.

## 4. Case Fail Mình Học Được

Run OpenAI đầu đạt 30/33 nhưng fail cả ba action `summarize / synthesize / self_check` vì output nghe đúng nhưng không giữ contract ổn định. Mình học được rằng với AI product, “câu trả lời có vẻ hay” chưa đủ; output contract, citation và failure mode phải kiểm thử được bằng eval.

## 5. Điều Cần Làm Tiếp

- Chốt Zone trong README/spec.
- Cùng nhóm hoàn thiện validation 5 user test thật.
- Nếu có thêm thời gian, bổ sung semantic review cho các case hậu quả cao thay vì chỉ dựa vào heuristic grounding.
