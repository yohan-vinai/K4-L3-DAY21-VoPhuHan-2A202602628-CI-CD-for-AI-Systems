# Báo Cáo Lab Day 21 - CI/CD cho AI Systems

| | |
|---|---|
| Họ và tên | Võ Phú Hãn |
| MSSV | 2A202602628 |
| Lớp / Khóa | K4 |
| Repo GitHub | https://github.com/yohan-vinai/K4-L3-DAY21-VoPhuHan-2A202602628-CI-CD-for-AI-Systems |
| Ngày nộp | 2026-10-07 |

---

## 1. Bộ Siêu Tham Số Đã Chọn và Lý Do

| Lần chạy | n_estimators | learning_rate | max_depth | f1_score | accuracy |
|---|---|---|---|---|---|
| 1 | 100 | 0.1 | 3 | 0.7109 | 0.8780 |
| 2 | 50 | 0.05 | 2 | 0.6051 | 0.8460 |
| 3 | 200 | 0.1 | 5 | 0.7149 | 0.8740 |

**Chọn:** `n_estimators=200`, `learning_rate=0.1`, `max_depth=5`, vì lần chạy 3 có F1 lớp dương cao nhất (0.7149) và vượt quality gate 0.65. Lần chạy 1 có accuracy cao nhất (0.8780), cho thấy accuracy và F1 xếp hạng khác nhau. Lần chạy 2 có F1 thấp nhất (0.6051). Vì mỗi lần đổi nhiều tham số cùng lúc, chưa thể kết luận tác động riêng của từng tham số.

---

## 2. Vì Sao Ngưỡng Chất Lượng Đặt Trên F1 Chứ Không Phải Accuracy

Lớp thu nhập trên 50K chiếm 24,8%. Trên holdout, mô hình luôn đoán thu nhập thấp vẫn đạt accuracy 0.752 nhưng bỏ sót cả lớp thu nhập cao (F1 lớp dương bằng 0). F1 với `target=1` cân bằng precision và recall nên phản ánh khả năng tìm nhóm này. Bài dùng `f1_score(y_eval, preds)` mặc định; `average="weighted"` và `average="macro"` gộp hai lớp, không khớp với ngưỡng 0.65 dành cho lớp dương.

---

## 3. Khó Khăn Gặp Phải và Cách Giải Quyết

| Khó khăn | Nguyên nhân | Cách giải quyết |
|---|---|---|
| Tải UCI trực tiếp lỗi `RemoteDisconnected`. | Kết nối bị ngắt. | Tải archive Adult chính thức và dùng file local, không sửa script gốc. |
| Pipeline lỗi OIDC và job Release thiếu script. | Trust subject dùng owner/repo ID; job chưa checkout. | Cập nhật trust policy và checkout; pipeline chạy thành công. |
| Push commit dữ liệu không tạo Actions run. | Workflow active và path filter khớp, nhưng không có push event run. | Dispatch thủ công trên đúng commit để xác minh train, gate và deploy; trigger tự động Bước 3 chưa được chứng minh. |

---

## 4. So Sánh Bước 2 và Bước 3

| | f1_score | accuracy |
|---|---|---|
| Bước 2 (`train_batch1`, 22.361 mẫu) | 0.7149 | 0.8740 |
| Bước 3 (`train_batch1` sau khi ghép, 44.722 mẫu) | 0.7354 | 0.8820 |

**Nhận xét:** Lần chạy này tăng F1 0.0205 và accuracy 0.0080; cả hai đều qua gate. Dữ liệu cùng nguồn, chia ngẫu nhiên nên không thể kết luận thêm dữ liệu luôn tốt hơn. Train, gate và deploy đã chạy trên commit dữ liệu bằng dispatch thủ công; tự động kích hoạt sau push chưa được chứng minh.
