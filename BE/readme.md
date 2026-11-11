# Ứng dụng Điểm danh bằng Khuôn mặt - Backend (FastAPI)

Hệ thống máy chủ API xử lý backend cho ứng dụng điểm danh khuôn mặt, được xây dựng bằng **FastAPI** và **OpenCV / DeepFace** (hoặc thư viện nhận diện tương đương).

## 1. Cài đặt & Chạy nhanh

**Yêu cầu hệ thống:** Python 3.9+

Mở terminal tại thư mục chứa source code backend và chạy lần lượt các lệnh sau:

```bash
# 1. Tạo và kích hoạt môi trường ảo
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\activate
# Linux/macOS:          source .venv/bin/activate

# 2. Cài đặt các thư viện cần thiết
pip install -r requirements.txt

# 3. Khởi chạy máy chủ phát triển (Development Server)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Sau khi chạy thành công, bạn có thể truy cập tài liệu API tự động tại:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## 2. Hợp đồng API (API Endpoints)

Các endpoint tiêu chuẩn mà ứng dụng Front-end mong đợi giao tiếp:

| Chức năng | Method & Endpoint | Mô tả chi tiết |
|---|---|---|
| **Kiểm tra kết nối** | `GET /health` | Trả về HTTP 200 để xác nhận server đang hoạt động. |
| **Điểm danh** | `POST /attendance` | Nhận file ảnh multipart (`image`), xử lý nhận diện khuôn mặt và ghi nhận chấm công. |
| **Xem danh sách** | `GET /attendance` | Lấy danh sách điểm danh, hỗ trợ lọc theo ngày (`?date=YYYY-MM-DD`). |
| **Đăng ký khuôn mặt** | `POST /student` | Đăng ký sinh viên mới với mã (`user_code`), họ tên (`full_name`) và các ảnh mẫu (`images`). |

---