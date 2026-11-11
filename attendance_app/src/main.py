"""
main.py
=======
Điểm khởi chạy (entry point) của ứng dụng front-end.

Chạy từ thư mục gốc attendance_app/:
    python -m src.main
    python src/main.py

Đổi địa chỉ API bằng biến môi trường (không cần sửa code):
    ATTENDANCE_API_URL=https://api.example.com/api python -m src.main
"""

import sys
from pathlib import Path

# Đảm bảo thư mục gốc dự án nằm trong sys.path để `from src...` luôn hoạt động,
# kể cả khi chạy trực tiếp `python src/main.py`.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import customtkinter as ctk  # noqa: E402

from src.services.api_client import ApiClient  # noqa: E402
from src.utils.config import APPEARANCE_MODE, COLOR_THEME  # noqa: E402
from src.utils.vision import FaceDetector  # noqa: E402
from src.views.main_window import MainWindow  # noqa: E402


def main() -> None:
    ctk.set_appearance_mode(APPEARANCE_MODE)
    ctk.set_default_color_theme(COLOR_THEME)

    api = ApiClient()          # client duy nhất giao tiếp với máy chủ
    detector = FaceDetector()  # phát hiện khuôn mặt cục bộ (chỉ để vẽ khung / quyết định khi nào gửi ảnh)

    app = MainWindow(api, detector)
    app.mainloop()


if __name__ == "__main__":
    main()
