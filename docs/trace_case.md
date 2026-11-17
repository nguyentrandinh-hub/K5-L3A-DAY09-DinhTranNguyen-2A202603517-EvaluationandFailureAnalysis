# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (chạy trực tiếp bằng `lab9.trace_case` / `eval_seeded_regression.json`) |
| Triệu chứng | `lab8 grader: FAIL (status resolved != denied)`; reply nói *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* và ledger ghi `refund_vnd=20000`, `refund_count=1`, trong khi nhãn mong đợi `refund_vnd=0`, `refund_count=0`, `status=denied`. |
| Bước sai đầu tiên | Event `3` · `model_override` · `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event `1` (`handoff` đúng `claim_id: C-002`, `allowed_tools` chỉ gồm tool đọc/tính) và Event `2` (`investigator` gọi `lookup_order` trả về `order_id: O-202`, `visible: true`) đều đúng contract; đến Event `3` model mới ghi đè `delay_days: 5` từ ticket. |
| Failure mode | `FM-03` (`ticket_trust` — tin ticket hơn DB) |
| Đối chứng | Trên `fixed C-002@11`, không có event `model_override` sau Event `2`; Event `3` là `quote` tính `amount_vnd: 0` (`no_entitlement`), Event `4` trả `status=denied` và `ledger=0`. |
| Regression test | `DbFactKept` & `RefundAmountCorrect` (`src/tests/test_lab9_graders.py` — `test_override_event_breaks_db_fact`, `test_wrong_amount_in_ledger`): bắt được `model_override` trên `seeded_regression` và pass trên `fixed`. |
| Chưa chắc chắn | Trace không ghi lại prompt thô hoặc reasoning nội bộ của model giải thích vì sao model chọn tin con số `5` trong ticket thay vì kết quả `lookup_order`. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
