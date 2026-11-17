# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: seeded_regression C-002@11

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID trong report: `E-seeded_regression-20261117-d9a3` (`src/reports/eval_seeded_regression.json`, item E-002, seed 11) |
| Triệu chứng | Lab 8 grader FAIL: `status resolved != denied`. Ledger ghi **20.000đ, 1 refund** trong khi nhãn là **0đ, 0 refund**. `RefundAmountCorrect` = False, `DbFactKept` = False. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." khớp ledger, nên `ReplyMatchesLedger` không bắt: reply trôi chảy và "đúng với ledger" nhưng chính khoản hoàn là sai. |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` chỉ chứa yêu cầu đã sanitize. Event 2 `investigator` đọc order O-202 từ DB đúng (`delay_days` = 2, visible ok). Đến event 3, agent lấy "trễ 5 ngày" trong ticket đè lên dữ kiện DB. Event 4 `quote` (20.000đ theo `SHIP-LATE-03`) chỉ là hệ quả: tính đúng công thức trên dữ kiện đã sai. Event 5 `refund_history`, event 6 `reply` tiếp tục từ quote đó. |
| Failure mode | **FM-03** ticket_trust (xem `docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: event 1 `handoff`, event 2 `investigator` giống hệt; **không có event `model_override`**; event 3 `quote` = 0đ, `no_entitlement`; reply "chưa đủ điều kiện hoàn"; ledger 0đ; Lab 8 grader PASS. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_c002_override_is_caught` (có `model_override` trước `quote`; `DbFactKept` và `RefundAmountCorrect` đều False trên `seeded_regression`) và `test_lab9_trace_case_c002_fixed_stays_green` (không override; hai grader True trên `fixed`). Đã chạy: 2 passed. Item E-002 trong eval set mang `FM-03`. |
| Chưa chắc chắn | Trace chỉ ghi kết quả override, không ghi vì sao model chọn tin ticket (MockLLM không có lập luận thật). Với một LLM thật, cùng claim có thể override ở seed khác; 5 seed không đủ để ước lượng tần suất. Trace cũng không chứng minh `quote` sẽ đúng nếu delay đúng ở mọi clause, chỉ đúng với C-002. |

## Quy tắc

- Đọc **ledger trước reply**: ca này là ví dụ. Reply khớp ledger nên nhìn reply thì tưởng ổn, nhưng ledger sai so với nhãn.
- "Bước sai đầu tiên" dẫn số event cụ thể (event 3), không phải "agent bị nhầm".
- Case hoàn thành vì đã có regression test chạy được trong `tests/` (`test_lab9_trace_case.py`).