# Mining Notes - VLearn Recall

## Data Boundary

Không đưa dữ liệu trong `data/` ra bất cứ folder ngoài nào khác.

File này chỉ ghi **phương pháp** mining. Không ghi raw rows, snippets, mã turn, mã đoạn, hoặc số thống kê thật nếu nhóm chưa thống nhất với TA rằng mức tổng hợp đó được phép đưa ra ngoài.

## Nguồn Đọc Tại Chỗ

- `data/vlearn-pack/chatlog/chat_history_anonymized_for_hackathon.csv`
- `data/vlearn-pack/chatlog/DATA_DICTIONARY.md`
- `data/vlearn-pack/transcript/*.md`

## Phương Pháp Mining Đề Xuất

1. Import CSV tại local.
2. Tách message theo role.
3. Đếm các pattern phục vụ VLearn Recall:
   - câu trả lời không có citation;
   - câu trả lời thiếu nguồn/không tìm thấy;
   - câu hỏi quá ngắn hoặc mơ hồ;
   - câu hỏi phụ thuộc selected slide/selected text;
   - phản hồi user nếu có.
4. Đọc transcript tại chỗ để xác định chủ đề học tập và mapping nguồn.
5. Không copy raw/snippet/mã nguồn thật sang `eval/`, `spec.md`, `codebase/` hoặc folder khác.

## Output Được Phép Trong Repo Ngoài Data

Tùy quyết định nhóm/TA:

- Có thể chỉ ghi "đã chạy mining tại chỗ, xem script/log private".
- Nếu được phép ghi aggregate, chỉ ghi số tổng hợp không thể suy ngược nội dung cá nhân.
- Không ghi quote nguyên văn nếu rule strict vẫn giữ.

## Checklist An Toàn

- [ ] Không raw chatlog.
- [ ] Không raw transcript.
- [ ] Không snippet từ học viên/tutor.
- [ ] Không mã turn/mã đoạn thật.
- [ ] Không email, MSSV, phone, địa chỉ, tên thật.
- [ ] Không copy runtime/source index trích xuất từ `data/` ra ngoài.
