"""
config.py
=========
Toàn bộ hằng số cấu hình của ứng dụng (front-end thuần, mọi dữ liệu đi qua API):
  - Địa chỉ API, các endpoint, token, timeout
  - Màu sắc, kích thước cửa sổ, font
  - Thông số camera và tần suất gửi ảnh lên máy chủ

Có thể ghi đè địa chỉ/token bằng biến môi trường mà không cần sửa code:
    ATTENDANCE_API_URL=https://api.example.com/api
    ATTENDANCE_API_TOKEN=xxxxx
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# 1. ĐƯỜNG DẪN
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = BASE_DIR / "src" / "assets"   # ảnh / icon (nếu có)

# --------------------------------------------------------------------------- #
# 2. API
# --------------------------------------------------------------------------- #
API_BASE_URL = os.getenv("ATTENDANCE_API_URL", "http://localhost:8000/api").rstrip("/")
API_TOKEN = os.getenv("ATTENDANCE_API_TOKEN", "")   # nếu có -> gửi "Authorization: Bearer <token>"
API_TIMEOUT = 15                                     # giây, cho mỗi request

# Các endpoint (nối vào API_BASE_URL)
EP_HEALTH = "/health"                 # GET   - kiểm tra kết nối
EP_CHECKIN = "/attendance"   # POST  - gửi ảnh để nhận diện + điểm danh
EP_RECORDS = "/attendance"            # GET   - danh sách lịch sử điểm danh
EP_REGISTER = "/student"       # POST  - đăng ký người dùng + ảnh khuôn mặt

HEALTH_CHECK_INTERVAL_MS = 20_000     # chu kỳ kiểm tra kết nối API

# --------------------------------------------------------------------------- #
# 3. CỬA SỔ & GIAO DIỆN
# --------------------------------------------------------------------------- #
APP_NAME = "Hệ thống Điểm danh Khuôn mặt"
WINDOW_SIZE = "1200x720"
WINDOW_MIN_SIZE = (1000, 640)
SIDEBAR_WIDTH = 230
APPEARANCE_MODE = "dark"
COLOR_THEME = "blue"

COLORS = {
    "bg": "#12141a",
    "sidebar": "#1b1e27",
    "card": "#232734",
    "card_alt": "#1d212c",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "text": "#e5e7eb",
    "muted": "#9ca3af",
    "border": "#2f3547",
}

FONT_FAMILY = "Segoe UI"

# --------------------------------------------------------------------------- #
# 4. CAMERA & GỬI ẢNH
# --------------------------------------------------------------------------- #
CAMERA_INDEX = 0
CAMERA_VIEW_SIZE = (640, 480)
FRAME_DELAY_MS = 30                  # ~33 FPS hiển thị

FACE_MIN_SIZE = 80                   # khuôn mặt nhỏ hơn số px này bị bỏ qua (phát hiện cục bộ)
JPEG_QUALITY = 85                    # chất lượng JPEG khi gửi lên API

# Điểm danh: chỉ gửi ảnh khi cục bộ thấy có khuôn mặt, và giãn cách giữa 2 request
CHECKIN_REQUEST_INTERVAL_SEC = 1.0   # tối thiểu giữa 2 lần gửi
CHECKIN_COOLDOWN_SEC = 5.0           # nghỉ sau khi nhận ra 1 người (tránh spam)
CHECKIN_ERROR_BACKOFF_SEC = 3.0      # nghỉ sau khi gọi API lỗi

# Đăng ký: số ảnh mẫu gửi lên
SAMPLES_PER_USER = 15
CAPTURE_EVERY_N_FRAMES = 5           # cứ N khung hình mới lấy 1 ảnh (đa dạng góc mặt)

# --------------------------------------------------------------------------- #
# 5. HIỂN THỊ TRẠNG THÁI
# --------------------------------------------------------------------------- #
# Trạng thái chứa 1 trong các từ khoá này (không phân biệt hoa/thường) -> tô màu cam "đi muộn"
LATE_KEYWORDS = ("muộn", "late")
