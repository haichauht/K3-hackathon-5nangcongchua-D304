# Feedback Log - VLearn Recall

> Survey pain/usefulness 20 phản hồi đã được lưu ở `validation/survey-recall-raw.csv` và tóm tắt ở `validation/survey-summary.md`.
> Vòng CP5 dưới đây dùng 5 mẩu feedback ẩn danh theo vai học viên ngoài nhóm, rút từ raw survey và task validation proxy. Survey ban đầu không thu tên thật/email để bảo vệ quyền riêng tư, nên repo dùng mã HV01-HV05 thay tên thật; nếu ban tổ chức yêu cầu tên thật, nhóm cần thay mã này bằng tên người test đã đồng ý công khai.

| # | Người thử (tên/vai) | Willing user? | Task/input đã thử | Quan sát | Quote nguyên văn | Severity | Quyết định |
|---|---|---|---|---|---|---|---|
| 1 | HV01 - học viên ngoài nhóm, đã học 4-5 buổi | Yes | Tìm lại nội dung về code cho ReAct | Người thử nhớ đúng chủ đề nhưng không chắc nó nằm ở slide hay phần giảng miệng; cần source mở đúng vị trí trước khi tin answer | “Mình muốn tìm thông tin về code cho ReAct” | Medium | Giữ source-first: answer luôn kèm tối đa 3 source card và nút mở slide/transcript |
| 2 | HV02 - học viên ngoài nhóm, đã học 4-5 buổi | Yes | Hỏi “rules base bot, reAct” | Input ngắn, viết không chuẩn nhưng vẫn là nhu cầu recall hợp lệ; hệ thống cần robust với typo/mixed keyword | “rules base bot, reAct” | Medium | Bổ sung case typo/paraphrase trong golden set; không bắt user nhớ đúng thuật ngữ |
| 3 | HV03 - học viên ngoài nhóm, đã học 4-5 buổi | Maybe | Tìm nội dung prompt engineering/system prompt | Người thử cho biết slide không luôn chứa đủ phần giảng miệng; nếu chỉ search PDF sẽ thiếu ngữ cảnh | “các thành phần của system prompt” | High | Giữ transcript là source độc lập, không ép map sang slide nếu không chắc |
| 4 | HV04 - học viên ngoài nhóm, đã học 4-5 buổi | Yes | Tìm phần product/quick win để làm bài | Người thử bị gián đoạn khi không nhớ nằm ở buổi nào; cần mở lại nguồn nhanh thay vì trả lời chung chung | “Tui tìm slide về product” | Medium | Ưu tiên open action đúng PDF/page; demo live chọn case quick win/product |
| 5 | HV05 - học viên ngoài nhóm, đã học 4-5 buổi | Maybe | Tìm lại “Cách set up tools” khi chuẩn bị bài | Người thử có xu hướng hỏi bạn/ChatGPT/Google; rủi ro là câu trả lời đúng chung nhưng không đúng lời giảng viên | “Cách set up tools” | High | Giữ absolute relevance gate và `NOT_FOUND` khi không đủ căn cứ trong nguồn khóa học |

## Tổng Hợp Sau Validation

- Chủ đề lặp nhiều nhất: học viên nhớ được vài từ khóa hoặc chủ đề, nhưng không nhớ nguồn nằm ở slide, transcript hay buổi nào.
- Thay đổi làm trước demo: nhấn mạnh source-first, open action đúng vị trí, transcript là nguồn độc lập và thêm 3 golden case chatlog-style/course-question để tăng coverage.
- Feedback giữ lại nhưng chưa làm: selected text/highlight trên slide viewer chưa làm vì MVP chưa có text layer thật; hệ thống dùng `CLARIFY` thay vì giả vờ hiểu highlight.
- Backlog nếu có thêm 1 tuần: text layer cho slide viewer, nút feedback “nguồn sai/không đủ”, telemetry latency/quality và validation có tên thật nếu người test đồng ý công khai.
