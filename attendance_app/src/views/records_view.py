from datetime import datetime
from tkinter import ttk
from typing import List, Optional

import customtkinter as ctk

from src.services.api_client import ApiClient, ApiError, is_late_status
from src.utils.async_utils import AsyncRunner
from src.utils.config import COLORS, FONT_FAMILY


class RecordsView(ctk.CTkFrame):
    COLUMNS = (
        ("student_code", "Mã ID", 140, "center"),
        ("full_name", "Họ tên", 260, "w"),
        ("check_in_time", "Thời gian điểm danh", 200, "center"),
        ("status", "Trạng thái", 140, "center"),
    )

    def __init__(self, master, api: ApiClient, runner: AsyncRunner):
        super().__init__(master, fg_color="transparent")
        self.api = api
        self.runner = runner
        self._request_id = 0  # đánh số request để bỏ qua phản hồi cũ khi người dùng bấm liên tiếp

        self._current_records: List[dict] = []

        self._build_ui()

    # ------------------------------------------------------------------ #
    # Dựng giao diện
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Thanh tiêu đề + điều khiển ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Lịch sử điểm danh", font=ctk.CTkFont(FONT_FAMILY, 24, "bold"),
            text_color=COLORS["text"], anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # Khung chứa bộ lọc và tìm kiếm bên phải header
        right_control_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_control_frame.grid(row=0, column=1, padx=12, sticky="e")

        # --- Thêm ô nhập tìm kiếm theo họ tên ---
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._filter_and_render())

        ctk.CTkLabel(
            right_control_frame, text="Tìm họ tên:", font=ctk.CTkFont(FONT_FAMILY, 12),
            text_color=COLORS["muted"]
        ).pack(side="left", padx=(0, 4))
        self.search_entry = ctk.CTkEntry(
            right_control_frame, textvariable=self.search_var, width=180, height=32,
            placeholder_text="Tìm theo họ tên...",
            placeholder_text_color="gray"
        )
        self.search_entry.pack(side="left", padx=(0, 8))

        self.filter_var = ctk.StringVar(value="Hôm nay")
        self.filter_segment = ctk.CTkSegmentedButton(
            right_control_frame, values=["Hôm nay", "Chọn ngày"], variable=self.filter_var,
            command=self._on_filter_changed,
        )
        self.filter_segment.pack(side="left", padx=(0, 8))

        # Khung chứa ô nhập 1 ngày cụ thể (ẩn mặc định, chỉ hiện khi chọn "Chọn ngày")
        self.date_picker_frame = ctk.CTkFrame(right_control_frame, fg_color="transparent")

        today_str = datetime.now().strftime("%Y-%m-%d")
        self.date_var = ctk.StringVar(value=today_str)
        self.date_entry = ctk.CTkEntry(
            self.date_picker_frame, textvariable=self.date_var, width=110, height=32,
            placeholder_text="YYYY-MM-DD",
        )
        self.date_entry.pack(side="left", padx=(0, 4))

        # Nút làm mới chung
        self.refresh_btn = ctk.CTkButton(
            header, text="Làm mới", width=100, height=34,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self.refresh,
        )
        self.refresh_btn.grid(row=0, column=2, padx=(8, 0))

        # --- Bảng dữ liệu ---
        table_card = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=14)
        table_card.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 8))
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(0, weight=1)

        self._style_treeview()
        self.tree = ttk.Treeview(
            table_card, style="Records.Treeview", show="headings",
            columns=[c[0] for c in self.COLUMNS], selectmode="browse",
        )
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "full_name"))

        self.tree.tag_configure("odd", background=COLORS["card"])
        self.tree.tag_configure("even", background=COLORS["card_alt"])
        self.tree.tag_configure("late", foreground=COLORS["warning"])

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scrollbar = ctk.CTkScrollbar(table_card, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=10)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.summary_label = ctk.CTkLabel(
            self, text="", text_color=COLORS["muted"], anchor="w",
            font=ctk.CTkFont(FONT_FAMILY, 13),
        )
        self.summary_label.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 20))

    def _style_treeview(self) -> None:
        """Style ttk.Treeview cho khớp theme tối của CustomTkinter."""
        style = ttk.Style(self)
        style.theme_use("clam")  # theme 'clam' cho phép đổi màu nền đầy đủ
        style.configure(
            "Records.Treeview",
            background=COLORS["card"], foreground=COLORS["text"],
            fieldbackground=COLORS["card"], borderwidth=0, rowheight=34,
            font=(FONT_FAMILY, 11),
        )
        style.configure(
            "Records.Treeview.Heading",
            background=COLORS["sidebar"], foreground=COLORS["text"],
            relief="flat", font=(FONT_FAMILY, 11, "bold"), padding=8,
        )
        style.map("Records.Treeview",
                  background=[("selected", COLORS["accent"])],
                  foreground=[("selected", "#ffffff")])
        style.map("Records.Treeview.Heading",
                  background=[("active", COLORS["border"])])

    def _on_filter_changed(self, value: str) -> None:
        """Xử lý khi người dùng đổi chế độ giữa 'Hôm nay' và 'Chọn ngày'."""
        if value == "Chọn ngày":
            self.date_picker_frame.pack(side="left", padx=(0, 8))
        else:
            self.date_picker_frame.pack_forget()
        self.refresh()

    # ------------------------------------------------------------------ #
    # Vòng đời view
    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.refresh()

    def on_hide(self) -> None:
        self._request_id += 1  # huỷ hiệu lực mọi request đang bay

    # ------------------------------------------------------------------ #
    # Nạp dữ liệu từ API
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Gọi API ở thread nền rồi hiển thị kết quả lên bảng."""
        self._request_id += 1
        request_id = self._request_id

        mode = self.filter_var.get()
        selected_date: Optional[str] = None

        if mode == "Hôm nay":
            selected_date = datetime.now().strftime("%Y-%m-%d")
        elif mode == "Chọn ngày":
            selected_date = self.date_var.get().strip()
            try:
                datetime.strptime(selected_date, "%Y-%m-%d")
            except ValueError:
                self.summary_label.configure(
                    text="Sai định dạng ngày! Vူ lòng dùng định dạng YYYY-MM-DD",
                    text_color=COLORS["danger"]
                )
                return

        self.refresh_btn.configure(state="disabled", text="Đang tải...")
        self.summary_label.configure(text="Đang tải dữ liệu từ máy chủ...", text_color=COLORS["muted"])

        def fetch_data():
            return self.api.get_records(date=selected_date)

        self.runner.submit(
            fetch_data,
            on_success=lambda records: self._on_loaded(request_id, records, mode, selected_date),
            on_error=lambda exc: self._on_failed(request_id, exc),
        )

    def _on_loaded(self, request_id: int, records: List[dict], mode: str, selected_date: Optional[str]) -> None:
        if request_id != self._request_id:
            return  # phản hồi cũ -> bỏ qua
        self.refresh_btn.configure(state="normal", text="Làm mới")

        # Lưu lại danh sách gốc để dùng khi người dùng gõ tìm kiếm
        self._current_records = records
        self._filter_and_render()

    def _filter_and_render(self) -> None:
        keyword = self.search_var.get().strip().lower()

        filtered = []
        for rec in self._current_records:
            full_name = rec.get("full_name", "").lower()
            if keyword in full_name:
                filtered.append(rec)

        self.tree.delete(*self.tree.get_children())
        for index, rec in enumerate(filtered, start=1):
            tags = ["even" if index % 2 == 0 else "odd"]
            if is_late_status(rec["status"]):
                tags.append("late")
            self.tree.insert(
                "", "end",
                values=(
                    rec.get("student_code", ""),
                    rec.get("full_name", ""),
                    rec.get("check_in_time", ""),
                    rec.get("status", "")
                ),
                tags=tags,
            )

        mode = self.filter_var.get()
        selected_date = self.date_var.get().strip() if mode == "Chọn ngày" else datetime.now().strftime("%Y-%m-%d")
        scope = "hôm nay" if mode == "Hôm nay" else f"ngày {selected_date}"

        summary_text = f"Tổng cộng {len(filtered)} lượt điểm danh ({scope})"
        if keyword:
            summary_text += f" [Tìm kiếm: '{keyword}']"

        self.summary_label.configure(text=summary_text, text_color=COLORS["muted"])

    def _on_failed(self, request_id: int, exc: Exception) -> None:
        if request_id != self._request_id:
            return
        self.refresh_btn.configure(state="normal", text="Làm mới")
        message = exc.message if isinstance(exc, ApiError) else f"Lỗi không xác định: {exc}"
        self.summary_label.configure(text=f"Không tải được dữ liệu: {message}", text_color=COLORS["danger"])