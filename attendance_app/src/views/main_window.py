"""
main_window.py
==============
Cửa sổ chính: Sidebar điều hướng bên trái (3 trang) + Content Frame bên phải.

MainWindow là "bộ điều phối" của tầng UI:
  - nhận ApiClient và FaceDetector từ main.py (Dependency Injection),
  - tạo AsyncRunner để mọi view gọi API ở thread nền,
  - chuyển trang bằng show_page(), gọi on_hide() / on_show() đúng lúc
    (tắt camera khi rời trang, tải lại dữ liệu khi vào trang),
  - hiển thị trạng thái kết nối API ở cuối Sidebar (tự kiểm tra định kỳ).
"""

import customtkinter as ctk

from src.services.api_client import ApiClient
from src.utils.async_utils import AsyncRunner
from src.utils.config import (
    API_BASE_URL,
    APP_NAME,
    COLORS,
    FONT_FAMILY,
    HEALTH_CHECK_INTERVAL_MS,
    SIDEBAR_WIDTH,
    WINDOW_MIN_SIZE,
    WINDOW_SIZE,
)
from src.utils.vision import FaceDetector
from src.views.checkin_view import CheckinView
from src.views.records_view import RecordsView
from src.views.register_view import RegisterView


class MainWindow(ctk.CTk):
    # (khoá trang, nhãn hiển thị trên nút)
    NAV_ITEMS = [
        ("checkin", "Điểm danh"),
        ("records", "Danh sách điểm danh"),
        ("register", "Đăng ký khuôn mặt"),
    ]

    def __init__(self, api: ApiClient, detector: FaceDetector):
        super().__init__()
        self.api = api
        self.detector = detector
        self.runner = AsyncRunner(self)

        self.title(APP_NAME)
        self.geometry(WINDOW_SIZE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.configure(fg_color=COLORS["bg"])

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._nav_buttons = {}
        self._pages = {}
        self._current_key = None
        self._health_after_id = None

        self._build_sidebar()
        self._build_content()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_page("checkin")
        self._check_health()

    # ------------------------------------------------------------------ #
    # Sidebar
    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=SIDEBAR_WIDTH, corner_radius=0, fg_color=COLORS["sidebar"])
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar, text="ĐIỂM DANH", font=ctk.CTkFont(FONT_FAMILY, 22, "bold"),
            text_color=COLORS["accent"],
        ).pack(padx=20, pady=(28, 0), anchor="w")
        ctk.CTkLabel(
            sidebar, text="Nhận diện khuôn mặt", font=ctk.CTkFont(FONT_FAMILY, 12),
            text_color=COLORS["muted"],
        ).pack(padx=20, pady=(0, 28), anchor="w")

        for key, label in self.NAV_ITEMS:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w", height=44, corner_radius=10,
                font=ctk.CTkFont(FONT_FAMILY, 14),
                fg_color="transparent", hover_color=COLORS["card"], text_color=COLORS["text"],
                command=lambda k=key: self.show_page(k),
            )
            btn.pack(fill="x", padx=14, pady=3)
            self._nav_buttons[key] = btn

        # --- Trạng thái kết nối API (đáy sidebar) ---
        status_box = ctk.CTkFrame(sidebar, fg_color="transparent")
        status_box.pack(side="bottom", fill="x", padx=18, pady=16)
        self.api_status = ctk.CTkLabel(
            status_box, text="● Đang kiểm tra API...", anchor="w",
            font=ctk.CTkFont(FONT_FAMILY, 12, "bold"), text_color=COLORS["muted"],
        )
        self.api_status.pack(fill="x")
        ctk.CTkLabel(
            status_box, text=API_BASE_URL, anchor="w", wraplength=SIDEBAR_WIDTH - 36,
            justify="left", font=ctk.CTkFont(FONT_FAMILY, 10), text_color=COLORS["muted"],
        ).pack(fill="x")

    # ------------------------------------------------------------------ #
    # Content
    # ------------------------------------------------------------------ #
    def _build_content(self) -> None:
        self.content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._pages = {
            "checkin": CheckinView(self.content, self.api, self.runner, self.detector),
            "records": RecordsView(self.content, self.api, self.runner),
            "register": RegisterView(self.content, self.api, self.runner, self.detector),
        }

    # ------------------------------------------------------------------ #
    # Điều hướng
    # ------------------------------------------------------------------ #
    def show_page(self, key: str) -> None:
        """Chuyển sang trang `key`: ẩn trang cũ (on_hide) -> hiện trang mới (on_show)."""
        if key == self._current_key:
            return

        if self._current_key is not None:
            old = self._pages[self._current_key]
            old.on_hide()
            old.grid_forget()

        page = self._pages[key]
        page.grid(row=0, column=0, sticky="nsew")
        page.on_show()
        self._current_key = key

        for k, btn in self._nav_buttons.items():
            active = k == key
            btn.configure(
                fg_color=COLORS["accent"] if active else "transparent",
                font=ctk.CTkFont(FONT_FAMILY, 14, "bold" if active else "normal"),
            )

    # ------------------------------------------------------------------ #
    # Kiểm tra kết nối API định kỳ
    # ------------------------------------------------------------------ #
    def _check_health(self) -> None:
        self.runner.submit(
            self.api.ping,
            on_success=lambda _ok: self._set_api_status(True),
            on_error=lambda _exc: self._set_api_status(False),
        )
        self._health_after_id = self.after(HEALTH_CHECK_INTERVAL_MS, self._check_health)

    def _set_api_status(self, online: bool) -> None:
        if online:
            self.api_status.configure(text="● API: đã kết nối", text_color=COLORS["success"])
        else:
            self.api_status.configure(text="● API: mất kết nối", text_color=COLORS["danger"])

    # ------------------------------------------------------------------ #
    def _on_close(self) -> None:
        """Nhả camera của mọi trang và dừng các tác vụ nền trước khi thoát."""
        if self._health_after_id is not None:
            self.after_cancel(self._health_after_id)
        for page in self._pages.values():
            page.on_hide()
        self.runner.close()
        self.destroy()
