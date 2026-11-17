# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (trong `src/`). Lớp dương là `FAIL` vì việc của judge là tìm lỗi.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt cả 3 | **dùng** |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Trượt κ và Recall | **loại** |

Ma trận nhầm lẫn (FAIL = dương):

| Tiêu chí | TP | FP | FN | TN | Tỉ lệ FAIL judge quan sát | Sau Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã. Rubric thêm: xưng hô phải là "LogiX" / "anh/chị", cấm "em", "nha". |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Gọi khách là "bạn". Rubric thêm danh sách đại từ không được dùng với khách. |
| 3 | H-029 "…không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ thấy "Dạ, vui lòng" ở đầu câu. Rubric thêm: câu mệnh lệnh / chặn khách liên hệ là FAIL dù có kính ngữ. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ…" | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric ghi rõ: xin lỗi **không bắt buộc** khi đã giải quyết xong; ngắn gọn đủ ý là PASS. |
| 5 | H-051 "…đã refund 90.000đ…" | FAIL | PASS | Người | "refund" nằm trong từ vựng CS được phép. Rubric thêm whitelist thuật ngữ tiếng Anh được dùng. |
| 6 | HL-015 "…đã hoàn 55.000đ cho đơn O-112" (ledger 40.000đ) | PASS | FAIL | Người | Judge `helpful` không có ledger nên không thể biết số tiền sai. Lỗi này thuộc FM-08, phải chấm bằng **code** so với ledger (`reply_matches_ledger`), không giao cho judge. |
| 7 | HL-016 câu xin lỗi dài, "đã hoàn 55.000đ cho đơn O-404" (ledger 35.000đ) | PASS | FAIL | Người | Judge bị lời lẽ lịch sự đánh lừa. Cùng hướng xử lý: kiểm số tiền bằng grader code. |

## Kết luận

- **tone_ok: dùng được.** Đạt cả 3 sàn (κ 0.757, P 0.857, R 0.800). Vẫn có 6 FN và 4 FP, đều do rubric chưa rõ về xưng hô, câu mệnh lệnh, xin lỗi và từ tiếng Anh; 5 case trên là căn cứ sửa rubric. Khi báo tỉ lệ lỗi tone, dùng con số đã hiệu chỉnh Rogan-Gladen (0.28 → 0.30), không dùng số thô.
- **helpful: loại, không được dùng làm gate.** Precision 1.0 trông đẹp nhưng Recall chỉ 0.30: judge bỏ sót 21/30 câu người chấm FAIL (FN = 21), κ = 0.375 dưới sàn 0.6. Phần lớn câu bị bỏ sót là **sai số tiền**: judge chỉ đọc câu trả lời, không có ledger, nên về nguyên tắc không thể kiểm được. Nếu dùng làm gate, judge này báo tỉ lệ lỗi 0.09 trong khi thực tế khoảng 0.30, tức để lọt khoảng 2/3 lỗi. Thay thế: chấm số tiền bằng grader code (metric FM-08 `reply_matches_ledger`), giữ judge chỉ cho phần thật sự cần ngôn ngữ.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng/tiêu chí), nên các con số trên không phải held-out. Cần nhãn người mới, chấm độc lập, để có held-out thật; rubric sau khi sửa phải đo lại κ/P/R trước khi dùng.