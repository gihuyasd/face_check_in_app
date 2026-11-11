import time
from datetime import datetime
from typing import Optional, Set
import numpy as np

import cv2
import customtkinter as ctk
from tkinter import filedialog

from src.services.api_client import ApiClient, ApiError, is_late_status, time_part
from src.utils.async_utils import AsyncRunner
from src.utils.config import (
    CAMERA_VIEW_SIZE,
    CHECKIN_COOLDOWN_SEC,
    CHECKIN_ERROR_BACKOFF_SEC,
    CHECKIN_REQUEST_INTERVAL_SEC,
    COLORS,
    FONT_FAMILY,
    FRAME_DELAY_MS,
)
from src.utils.vision import Camera, FaceDetector, blank_ctkimage, encode_jpeg, frame_to_ctkimage

# Màu vẽ lên khung hình (OpenCV dùng BGR)
BGR_YELLOW = (11, 158, 245)  # trạng thái bình thường / chờ
BGR_GREEN = (94, 197, 34)  # vừa nhận ra


class CheckinView(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, runner: AsyncRunner, detector: FaceDetector):
        super().__init__(master, fg_color="transparent")
        self.api = api
        self.runner = runner
        self.detector = detector
        self.camera = Camera()

        # Vòng lặp camera
        self._running = False
        self._after_id: Optional[str] = None
        self._fail_count = 0
        self._current_image = None
        self._latest_raw_frame = None  # Ảnh đã chụp/chọn, dùng để gửi API
        self._latest_camera_frame = None  # Frame camera mới nhất để chụp lại
        self._captured = False  # Đã có ảnh được chọn để gửi hay chưa

        # Trạng thái gọi API
        self._session = 0  # tăng mỗi lần bật camera -> bỏ qua kết quả của phiên cũ
        self._busy = False  # đang có 1 request chưa trả về
        self._recognized_until = 0.0  # khung xanh hiển thị tới mốc này
        self._last_code = ""
        self._announced: Set[str] = set()  # người đã báo "đã điểm danh" trong phiên
        self._last_error = ""
        self._last_unknown_log = 0.0
        self._session_count = 0

        self._blank = blank_ctkimage(CAMERA_VIEW_SIZE)
        self._build_ui()

    # ------------------------------------------------------------------ #
    # Dựng giao diện
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Điểm danh bằng khuôn mặt",
            font=ctk.CTkFont(FONT_FAMILY, 24, "bold"), text_color=COLORS["text"], anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(24, 12))

        # ---- Cột trái: camera & điều khiển ----
        cam_card = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=14)
        cam_card.grid(row=1, column=0, sticky="nsew", padx=(24, 12), pady=(0, 24))
        cam_card.grid_columnconfigure(0, weight=1)

        self.camera_label = ctk.CTkLabel(
            cam_card, text="Camera đang tắt", image=self._blank, compound="center",
            text_color=COLORS["muted"], font=ctk.CTkFont(FONT_FAMILY, 16),
        )
        self.camera_label.grid(row=0, column=0, padx=16, pady=(16, 8))

        # Nhóm nút: bật/tắt camera, import, chụp lại và gửi điểm danh
        btn_frame = ctk.CTkFrame(cam_card, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 8))
        btn_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.toggle_btn = ctk.CTkButton(
            btn_frame, text="Bật camera", height=38, font=ctk.CTkFont(FONT_FAMILY, 12, "bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._toggle_camera,
        )
        self.toggle_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.import_btn = ctk.CTkButton(
            btn_frame, text="Import ảnh", height=38, font=ctk.CTkFont(FONT_FAMILY, 12, "bold"),
            fg_color="#4b5563", hover_color="#374151",
            command=self._import_image,
        )
        self.import_btn.grid(row=0, column=1, sticky="ew", padx=3)

        self.retake_btn = ctk.CTkButton(
            btn_frame, text="Chụp lại", height=38, font=ctk.CTkFont(FONT_FAMILY, 12, "bold"),
            fg_color="#0f766e", hover_color="#115e59",
            command=self._retake_photo,
        )
        self.retake_btn.grid(row=0, column=2, sticky="ew", padx=3)

        self.checkin_btn = ctk.CTkButton(
            btn_frame, text="Gửi điểm danh", height=38, font=ctk.CTkFont(FONT_FAMILY, 12, "bold"),
            fg_color=COLORS["success"], hover_color="#16a34a",
            command=self._manual_check_in,
        )
        self.checkin_btn.grid(row=0, column=3, sticky="ew", padx=(3, 0))

        self.camera_status = ctk.CTkLabel(
            cam_card, text="Bấm 'Bật camera' hoặc 'Import ảnh' để bắt đầu.", text_color=COLORS["muted"],
            font=ctk.CTkFont(FONT_FAMILY, 13), wraplength=560,
        )
        self.camera_status.grid(row=2, column=0, pady=(0, 14))

        # ---- Cột phải: ảnh chụp gần nhất + kết quả + log ----
        log_card = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=14)
        log_card.grid(row=1, column=1, sticky="nsew", padx=(12, 24), pady=(0, 24))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            log_card, text="Ảnh để gửi điểm danh", font=ctk.CTkFont(FONT_FAMILY, 13),
            text_color=COLORS["muted"], anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 0))

        # Khung nhỏ hiển thị preview ảnh đã chụp/import để gửi
        self.preview_label = ctk.CTkLabel(
            log_card, text="Chưa có ảnh", image=blank_ctkimage((200, 120)), compound="center",
            text_color=COLORS["muted"], font=ctk.CTkFont(FONT_FAMILY, 12),
        )
        self.preview_label.grid(row=1, column=0, padx=16, pady=(4, 8))

        ctk.CTkLabel(
            log_card, text="Kết quả gần nhất", font=ctk.CTkFont(FONT_FAMILY, 13),
            text_color=COLORS["muted"], anchor="w",
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 0))

        self.banner = ctk.CTkLabel(
            log_card, text="—", font=ctk.CTkFont(FONT_FAMILY, 16, "bold"),
            text_color=COLORS["text"], anchor="w", wraplength=320, justify="left",
        )
        self.banner.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 8))

        self.counter_label = ctk.CTkLabel(
            log_card, text="Lượt ghi nhận trong phiên: 0", font=ctk.CTkFont(FONT_FAMILY, 12),
            text_color=COLORS["muted"], anchor="w",
        )
        self.counter_label.grid(row=4, column=0, sticky="ew", padx=16)

        self.log_box = ctk.CTkTextbox(
            log_card, fg_color=COLORS["bg"], text_color=COLORS["text"],
            font=ctk.CTkFont("Consolas", 12), corner_radius=10, wrap="word",
        )
        self.log_box.grid(row=5, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Vòng đời view
    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        """Rời trang -> tắt camera để nhả thiết bị."""
        self._stop_camera()

    # ------------------------------------------------------------------ #
    # Điều khiển camera & Import ảnh
    # ------------------------------------------------------------------ #
    def _toggle_camera(self) -> None:
        if self._running:
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self) -> None:
        if not self.camera.open():
            self._set_status("Không mở được camera. Kiểm tra thiết bị / CAMERA_INDEX.", "danger")
            return
        self._running = True
        self._session += 1
        self._busy = False
        self._fail_count = 0
        self._last_error = ""
        self._latest_raw_frame = None
        self._latest_camera_frame = None
        self._captured = False
        self._announced.clear()
        self.preview_label.configure(image=blank_ctkimage((200, 120)), text="Chưa có ảnh")
        self.toggle_btn.configure(text="Tắt camera", fg_color=COLORS["danger"], hover_color="#dc2626")
        self._set_status("Đưa khuôn mặt vào camera. Hệ thống sẽ tự chụp, chưa gửi API.", "success")
        self._loop()

    def _stop_camera(self) -> None:
        self._running = False
        self._busy = False
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.camera.release()
        self._current_image = None
        self._latest_camera_frame = None
        # Giữ nguyên ảnh đã chụp để người dùng vẫn có thể gửi sau khi tắt camera.
        self.camera_label.configure(image=self._blank, text="Camera đang tắt")
        self.toggle_btn.configure(text="Bật camera", fg_color=COLORS["accent"],
                                  hover_color=COLORS["accent_hover"])
        self._set_status("Camera đã tắt.", "muted")

    def _import_image(self) -> None:
        """Cho phép chọn file ảnh từ máy tính để điểm danh (Hỗ trợ đường dẫn tiếng Việt)."""
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh điểm danh",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")]
        )
        if not file_path:
            return

        try:
            # Sửa lỗi OpenCV không đọc được đường dẫn tiếng Việt / khoảng trắng trên Windows
            n = np.fromfile(file_path, np.uint8)
            img = cv2.imdecode(n, cv2.IMREAD_COLOR)
        except Exception as e:
            img = None

        if img is None:
            self._set_status("Không đọc được file ảnh vừa chọn (Lỗi đường dẫn hoặc file hỏng)!", "danger")
            return

        # Ảnh import trở thành ảnh được chọn để gửi điểm danh.
        self._latest_raw_frame = img.copy()
        self._captured = True

        # Hiển thị ảnh lên khung preview nhỏ bên phải.
        preview_img = frame_to_ctkimage(img, (200, 120))
        self.preview_label.configure(image=preview_img, text="")

        # Copy ảnh để vẽ bounding box hiển thị lên màn hình camera
        display_img = img.copy()
        boxes = self.detector.detect(display_img)
        for x, y, w, h in boxes:
            cv2.rectangle(display_img, (x, y), (x + w, x + h), BGR_GREEN, 2)  # type: ignore

        disp_img = frame_to_ctkimage(display_img, CAMERA_VIEW_SIZE)
        self.camera_label.configure(image=disp_img, text="")

        # Xử lý cắt tên file an toàn với cả dấu gạch chéo ngược (\) trên Windows
        file_name = file_path.replace("\\", "/").split('/')[-1]
        self._set_status(f"Đã import ảnh: {file_name}. Kiểm tra ảnh rồi bấm 'Gửi điểm danh'.", "success")

    def _retake_photo(self) -> None:
        """Xóa ảnh hiện tại trong preview, đặt lại trạng thái để camera tiếp tục tự chụp."""
        if not self._running:
            self._set_status("Hãy bật camera trước khi chụp lại.", "warning")
            return

        # 1. Xóa ảnh hiện tại trong khung preview
        self.preview_label.configure(image=blank_ctkimage((200, 120)), text="Chưa có ảnh")

        # 2. Đặt lại trạng thái _captured = False và xóa frame thô cũ
        self._captured = False
        self._latest_raw_frame = None

        # 3, 4, 5. Camera tiếp tục chạy bình thường qua _loop(), tự động chụp lại khi thấy khuôn mặt mới
        self._set_status("Đã xóa ảnh cũ. Đang chờ phát hiện khuôn mặt mới để tự chụp...", "success")

    def _capture_frame(self, frame, boxes=None) -> None:
        """Lưu ảnh sạch và cập nhật preview; tuyệt đối không gửi API."""
        self._latest_raw_frame = frame.copy()
        self._captured = True

        preview_img = frame_to_ctkimage(self._latest_raw_frame, (200, 120))
        self.preview_label.configure(image=preview_img, text="")

        display_img = frame.copy()
        if boxes is None:
            boxes = self.detector.detect(display_img)
        for x, y, w, h in boxes:
            cv2.rectangle(display_img, (x, y), (x + w, y + h), BGR_GREEN, 2)

        self._current_image = frame_to_ctkimage(display_img, CAMERA_VIEW_SIZE)
        self.camera_label.configure(image=self._current_image, text="")

    def _loop(self) -> None:
        if not self._running:
            return

        frame = self.camera.read()
        if frame is None:
            self._fail_count += 1
            if self._fail_count > 30:  # mất tín hiệu liên tục ~1 giây
                self._stop_camera()
                self._set_status("Mất tín hiệu camera.", "danger")
                return
        else:
            self._fail_count = 0
            self._latest_camera_frame = frame.copy()

            # Phát hiện khuôn mặt hoàn toàn ở máy local, không gọi API.
            display_frame = frame.copy()
            boxes = self.detector.detect(display_frame)

            if boxes:
                color = BGR_GREEN
                label = "Face detected"

                # Tự động chụp đúng một lần khi phát hiện khuôn mặt đầu tiên hoặc sau khi bấm "Chụp lại" (_captured = False).
                if not self._captured:
                    self._capture_frame(frame, boxes)
                    self._set_status(
                        "Đã tự động chụp khuôn mặt. Kiểm tra ảnh rồi bấm 'Gửi điểm danh'.",
                        "success",
                    )
            else:
                color = BGR_YELLOW
                label = "No face"

            for x, y, w, h in boxes:
                cv2.rectangle(
                    display_frame,
                    (x, y),
                    (x + w, y + h),
                    color,
                    2,
                )
                cv2.putText(
                    display_frame,
                    label,
                    (x, max(y - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    color,
                    2,
                )

            self._current_image = frame_to_ctkimage(display_frame, CAMERA_VIEW_SIZE)
            self.camera_label.configure(image=self._current_image, text="")

        self._after_id = self.after(FRAME_DELAY_MS, self._loop)

    # ------------------------------------------------------------------ #
    # Gửi API điểm danh thủ công khi bấm nút
    # ------------------------------------------------------------------ #
    def _manual_check_in(self) -> None:
        if self._latest_raw_frame is None or not self._captured:
            self._set_status("Chưa có ảnh khuôn mặt. Hãy bật camera, chờ tự chụp hoặc import ảnh.", "danger")
            return

        if self._busy:
            self._set_status("Đang xử lý yêu cầu trước, vui lòng đợi...", "warning")
            return

        # Cập nhật hiển thị ảnh preview gửi đi
        preview_img = frame_to_ctkimage(self._latest_raw_frame, (200, 120))
        self.preview_label.configure(image=preview_img, text="")

        try:
            # Mã hoá JPEG ảnh sạch (không dính nét vẽ bounding box)
            jpeg = encode_jpeg(self._latest_raw_frame)
        except RuntimeError as exc:
            self._set_status(str(exc), "danger")
            return

        self._busy = True
        session = self._session
        self._set_status("Đang gửi yêu cầu điểm danh lên server...", "success")

        self.runner.submit(
            lambda: self.api.check_in(jpeg),
            on_success=lambda result: self._on_result(session, result),
            on_error=lambda exc: self._on_error(session, exc),
        )

    # ------------------------------------------------------------------ #
    # Nhận kết quả từ API (chạy ở luồng UI)
    # ------------------------------------------------------------------ #
    def _on_result(self, session: int, result: dict) -> None:
        if session != self._session:
            return

        self._busy = False
        self._last_error = ""
        stamp = datetime.now().strftime("%H:%M:%S")
        now = time.time()

        if not result["recognized"]:
            self._set_status("Không nhận diện được khuôn mặt.", "danger")
            self.banner.configure(text="Không nhận diện được", text_color=COLORS["danger"])
            self._append_log(f"[{stamp}] {result['message'] or 'Không nhận diện được khuôn mặt'}")
            return

        code, name = result["student_code"], result["full_name"]
        self._last_code = code
        self._recognized_until = now + 2.0
        self._set_status("Điểm danh thành công!", "success")

        if not result["already_checked_in"]:
            self._session_count += 1
            color = COLORS["warning"] if is_late_status(result["status"]) else COLORS["success"]
            self.banner.configure(text=f"{name}\n{result['status']}", text_color=color)
            self._append_log(f"[{stamp}] {code} - {name} ({result['status']})")
            self.counter_label.configure(text=f"Lượt ghi nhận trong phiên: {self._session_count}")
        else:
            self.banner.configure(
                text=f"{name}\nĐã điểm danh lúc {time_part(result['checked_at'])}",
                text_color=COLORS["muted"],
            )
            if code not in self._announced:
                self._announced.add(code)
                self._append_log(f"[{stamp}] • {code} - {name} đã điểm danh hôm nay")

    def _on_error(self, session: int, exc: Exception) -> None:
        if session != self._session:
            return
        self._busy = False
        message = exc.message if isinstance(exc, ApiError) else f"Lỗi không xác định: {exc}"
        self._set_status(message, "danger")
        if message != self._last_error:
            self._last_error = message
            self._append_log(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    # ------------------------------------------------------------------ #
    # Tiện ích UI
    # ------------------------------------------------------------------ #
    def _append_log(self, line: str) -> None:
        """Chèn dòng mới lên đầu bảng log (mới nhất ở trên)."""
        self.log_box.configure(state="normal")
        self.log_box.insert("1.0", line + "\n")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str, kind: str = "muted") -> None:
        self.camera_status.configure(text=text, text_color=COLORS.get(kind, COLORS["muted"]))