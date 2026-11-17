# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (`PASS floors`, observed fail 0.28 -> RG corrected 0.30) | **dùng** |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (`FAIL floors`: κ < 0.6, R < 0.7; observed fail 0.09 -> RG corrected 0.30) | **loại** |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | `H-008` (`tone_ok`) | `PASS` | `FAIL` | Người | Dùng từ xưng hô thân mật quá mức ("anh/em", "nha") thay vì chuẩn CSKH LogiX ("anh/chị", "ạ"). |
| 2 | `H-029` (`tone_ok`) | `PASS` | `FAIL` | Người | Giọng văn cộc lốc, thiếu giải thích và mang tính ra lệnh ("không cần nhắn thêm"). |
| 3 | `H-042` (`tone_ok`) | `PASS` (nhầm: Judge `FAIL`) | `PASS` | Người | Câu trả lời lịch sự, rõ thông tin 3–5 ngày; judge bắt nhầm do không có câu xin lỗi. |
| 4 | `HL-015` (`helpful`) | `PASS` | `FAIL` | Người | Chỉ báo đã hoàn 55.000đ nhưng thiếu giải thích lý do/đối chiếu số tiền và bước tiếp theo khi cần. |
| 5 | `HL-016` (`helpful`) | `PASS` | `FAIL` | Người | Xin lỗi chung chung, sáo rỗng ("thành thật xin lỗi... trân trọng sự kiên nhẫn"), không giải quyết vấn đề hay nêu hướng xử lý. |
| 6 | `HL-028` (`helpful`) | `PASS` | `FAIL` | Người | Tương tự `HL-016`, lặp mẫu câu xin lỗi lịch sự ("Dạ, ..."), đánh lừa judge dựa trên từ khóa lịch sự. |

## Kết luận
- **Tiêu chí bị loại:** `helpful` (`judge_helpful_public.csv`) bị loại, **không được dùng làm CI gate** vì `κ = 0.375 < 0.6` và `Recall = 0.300 < 0.7`. Ma trận nhầm lẫn (`tp=9, fp=0, fn=21, tn=70`) cho thấy judge bỏ sót 21/30 ca lỗi (`FN=21`), làm tỉ lệ lỗi quan sát bị giảm giả tạo xuống `0.09` dù tỉ lệ lỗi thực (hiệu chỉnh Rogan-Gladen) là `0.30`.
- **Hành động sửa rubric:** Sửa rubric chấm `helpful` thành checklist có kiểm chứng hành động (yêu cầu nêu rõ kết quả xử lý/số tiền/lý do cụ thể và bước tiếp theo; coi các câu xin lỗi sáo rỗng không có thông tin hành động là `FAIL`), sau đó hiệu chuẩn lại trên mẫu mới trước khi cân nhắc dùng.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
