from tkinter import filedialog
from typing import List, Optional

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image as PILImage

from src.services.api_client import ApiClient, ApiError
from src.utils.async_utils import AsyncRunner
from src.utils.config import (
    CAMERA_VIEW_SIZE,
    CAPTURE_EVERY_N_FRAMES,
    COLORS,
    FONT_FAMILY,
    FRAME_DELAY_MS,
    SAMPLES_PER_USER,
)
from src.utils.vision import (
    Camera,
    FaceDetector,
    blank_ctkimage,
    encode_jpeg,
    frame_to_ctkimage,
)

BGR_GREEN = (94, 197, 34)
BGR_RED = (68, 68, 239)


class RegisterView(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, runner: AsyncRunner, detector: FaceDetector):
        super().__init__(master, fg_color="transparent")
        self.api = api
        self.runner = runner
        self.detector = detector
        self.camera = Camera()

        self._running = False
        self._after_id: Optional[str] = None
        self._fail_count = 0
        self._current_image = None

        # Trạng thái thu thập / upload
        self._capturing = False
        self._uploading = False
        self._attempt = 0  # đánh số lần đăng ký để bỏ qua phản hồi cũ
        self._pending_name = ""
        self._samples: List[bytes] = []  # ảnh JPEG đã thu (từ camera hoặc tải lên)
        self._thumbnail_images: List[ctk.CTkImage] = []  # Lưu giữ tham chiếu ảnh thumbnail hiển thị
        self._frame_counter = 0

        self._thumbnail_count = 0

        self._blank = blank_ctkimage(CAMERA_VIEW_SIZE)
        self._build_ui()

    # ------------------------------------------------------------------ #
    # Dựng giao diện
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="Đăng ký khuôn mặt mới",
            font=ctk.CTkFont(FONT_FAMILY, 24, "bold"), text_color=COLORS["text"], anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(24, 12))

        # ---- Cột trái: form & preview ảnh ----
        form = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=14)
        form.grid(row=1, column=0, sticky="nsew", padx=(24, 12), pady=(0, 24))
        form.grid_columnconfigure(0, weight=1)
        form.grid_rowconfigure(8, weight=1)  # Cho phép khung preview co giãn linh hoạt

        ctk.CTkLabel(form, text="Họ và tên", anchor="w",
                     text_color=COLORS["text"]).grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 2))
        self.name_entry = ctk.CTkEntry(form, height=36, placeholder_text="VD: Nguyễn Văn A")
        self.name_entry.grid(row=1, column=0, sticky="ew", padx=20)

        # Nút chụp mẫu qua camera
        self.start_btn = ctk.CTkButton(
            form, text="Bắt đầu chụp mẫu", height=36, font=ctk.CTkFont(FONT_FAMILY, 13, "bold"),
            fg_color=COLORS["success"], hover_color="#16a34a", command=self._start_capture,
        )
        self.start_btn.grid(row=2, column=0, sticky="ew", padx=20, pady=(14, 4))

        # Nút tải ảnh lên từ máy
        self.upload_file_btn = ctk.CTkButton(
            form, text="Chọn ảnh từ máy tính", height=36, font=ctk.CTkFont(FONT_FAMILY, 13, "bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], command=self._load_images_from_disk,
        )
        self.upload_file_btn.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 4))

        # Nút Đăng ký (Gửi lên server khi đã đủ ảnh)
        self.submit_btn = ctk.CTkButton(
            form, text="Đăng ký", height=38, font=ctk.CTkFont(FONT_FAMILY, 14, "bold"),
            fg_color="#0284c7", hover_color="#0369a1", state="disabled", command=self._submit_registration,
        )
        self.submit_btn.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 4))

        self.cancel_btn = ctk.CTkButton(
            form, text="Huỷ", height=32, fg_color=COLORS["border"], hover_color="#3b4258",
            state="disabled", command=self._cancel_capture,
        )
        self.cancel_btn.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 6))

        self.progress = ctk.CTkProgressBar(form, progress_color=COLORS["success"])
        self.progress.set(0)
        self.progress.grid(row=6, column=0, sticky="ew", padx=20, pady=(4, 2))

        self.progress_label = ctk.CTkLabel(
            form, text=f"0 / {SAMPLES_PER_USER} ảnh", text_color=COLORS["muted"],
            font=ctk.CTkFont(FONT_FAMILY, 12), anchor="w",
        )
        self.progress_label.grid(row=7, column=0, sticky="ew", padx=20)

        # --- KHUNG CHỨA CÁC ẢNH ĐÃ CHỤP / CHỌN (Thumbnail Gallery) ---
        preview_container = ctk.CTkFrame(form, fg_color=COLORS["card_alt"], corner_radius=10)
        preview_container.grid(row=8, column=0, sticky="nsew", padx=20, pady=(6, 8))
        preview_container.grid_columnconfigure(0, weight=1)
        preview_container.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            preview_container, text="Ảnh mẫu đã thu thập:", text_color=COLORS["muted"],
            font=ctk.CTkFont(FONT_FAMILY, 12, "bold"), anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        self.thumbnail_scroll = ctk.CTkScrollableFrame(preview_container, fg_color="transparent")
        self.thumbnail_scroll.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 6))
        for i in range(4):
            self.thumbnail_scroll.grid_columnconfigure(i, weight=1)

        self.status_label = ctk.CTkLabel(
            form, text="Nhập họ tên rồi bấm 'Bắt đầu chụp mẫu' hoặc tải ảnh lên.",
            text_color=COLORS["muted"], wraplength=300, justify="left", anchor="w",
            font=ctk.CTkFont(FONT_FAMILY, 13),
        )
        self.status_label.grid(row=9, column=0, sticky="ew", padx=20, pady=(4, 12))

        # ---- Cột phải: camera ----
        cam_card = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=14)
        cam_card.grid(row=1, column=1, sticky="nsew", padx=(12, 24), pady=(0, 24))
        cam_card.grid_columnconfigure(0, weight=1)

        self.camera_label = ctk.CTkLabel(
            cam_card, text="Camera đang tắt", image=self._blank, compound="center",
            text_color=COLORS["muted"], font=ctk.CTkFont(FONT_FAMILY, 16),
        )
        self.camera_label.grid(row=0, column=0, padx=16, pady=(16, 8))

        self.toggle_btn = ctk.CTkButton(
            cam_card, text="Bật camera", height=42, font=ctk.CTkFont(FONT_FAMILY, 14, "bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._toggle_camera,
        )
        self.toggle_btn.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 16))

    # ------------------------------------------------------------------ #
    # Vòng đời view
    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        self._abort(silent=True)
        self._stop_camera()

    # ------------------------------------------------------------------ #
    # Camera
    # ------------------------------------------------------------------ #
    def _toggle_camera(self) -> None:
        if self._running:
            self._abort(silent=True)
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self) -> bool:
        if self._running:
            return True
        if not self.camera.open():
            self._set_status("Không mở được camera. Kiểm tra thiết bị / CAMERA_INDEX.", "danger")
            return False
        self._running = True
        self._fail_count = 0
        self.toggle_btn.configure(text="Tắt camera", fg_color=COLORS["danger"], hover_color="#dc2626")
        self._loop()
        return True

    def _stop_camera(self) -> None:
        self._running = False
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.camera.release()
        self._current_image = None
        self.camera_label.configure(image=self._blank, text="Camera đang tắt")
        self.toggle_btn.configure(text="Bật camera", fg_color=COLORS["accent"],
                                  hover_color=COLORS["accent_hover"])

    def _loop(self) -> None:
        if not self._running:
            return

        frame = self.camera.read()
        if frame is None:
            self._fail_count += 1
            if self._fail_count > 30:
                self._abort(silent=True)
                self._stop_camera()
                self._set_status("Mất tín hiệu camera.", "danger")
                return
        else:
            self._fail_count = 0
            self._process_frame(frame)
            self._current_image = frame_to_ctkimage(frame, CAMERA_VIEW_SIZE)
            self.camera_label.configure(image=self._current_image, text="")

            # Khi đủ số lượng ảnh, dừng quá trình chụp tự động và bật nút "Đăng ký"
            if self._capturing and len(self._samples) >= SAMPLES_PER_USER:
                self._capturing = False
                self._set_status(f"Đã thu đủ {SAMPLES_PER_USER} ảnh. Bấm 'Đăng ký' để gửi lên hệ thống.", "success")
                self.submit_btn.configure(state="normal")
                self.cancel_btn.configure(state="normal")

        if self._running:
            self._after_id = self.after(FRAME_DELAY_MS, self._loop)

    def _process_frame(self, frame) -> None:
        """Thu mẫu (nếu đang chụp) khi có đúng 1 khuôn mặt, rồi vẽ khung lên ảnh."""
        boxes = self.detector.detect(frame)

        if self._capturing:
            if len(boxes) == 1:
                self._frame_counter += 1
                if self._frame_counter % CAPTURE_EVERY_N_FRAMES == 0:
                    jpeg_bytes = encode_jpeg(frame)
                    self._samples.append(jpeg_bytes)
                    self._add_thumbnail(jpeg_bytes)
                    self._update_progress()
                self._set_status(f"Đang thu mẫu... ({len(self._samples)}/{SAMPLES_PER_USER})", "success")
            elif len(boxes) == 0:
                self._set_status("Không thấy khuôn mặt. Hãy nhìn thẳng vào camera.", "warning")
            else:
                self._set_status("Có nhiều hơn 1 khuôn mặt trong khung hình!", "danger")

        for x, y, w, h in boxes:
            color = BGR_GREEN if len(boxes) == 1 else BGR_RED
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

    # ------------------------------------------------------------------ #
    # Thu mẫu & upload (Camera hoặc Tải file)
    # ------------------------------------------------------------------ #
    def _validate_form(self) -> Optional[str]:
        name = self.name_entry.get().strip()
        if not name:
            self._set_status("Vui lòng nhập họ tên.", "danger")
            return None
        return name

    def _start_capture(self) -> None:
        name = self._validate_form()
        if not name:
            return

        if not self._start_camera():
            return

        self._pending_name = name
        self._samples.clear()
        self._clear_thumbnails()
        self._frame_counter = 0
        self._capturing = True
        self.submit_btn.configure(state="disabled")
        self._update_progress()
        self._set_form_inputs_enabled(False)
        self._set_status("Bắt đầu thu mẫu. Nhìn thẳng vào camera.", "success")

    def _load_images_from_disk(self) -> None:
        """Cho phép người dùng chọn nhiều file ảnh từ máy tính."""
        name = self._validate_form()
        if not name:
            return

        file_paths = filedialog.askopenfilenames(
            title=f"Chọn chính xác {SAMPLES_PER_USER} ảnh khuôn mặt",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.webp")]
        )
        if not file_paths:
            return

        if len(file_paths) != SAMPLES_PER_USER:
            self._set_status(
                f"Bạn chọn {len(file_paths)} ảnh. Hệ thống yêu cầu chính xác {SAMPLES_PER_USER} ảnh!",
                "danger"
            )
            return

        self._samples.clear()
        self._clear_thumbnails()

        loaded_samples = []
        for path in file_paths:
            try:
                with open(path, "rb") as f:
                    chunk = f.read()
                bytes_arr = np.frombuffer(chunk, dtype=np.uint8)
                img = cv2.imdecode(bytes_arr, cv2.IMREAD_COLOR)
                if img is not None:
                    jpeg_bytes = encode_jpeg(img)
                    loaded_samples.append(jpeg_bytes)
            except Exception:
                continue

        if len(loaded_samples) != SAMPLES_PER_USER:
            self._set_status(
                f"Có tệp ảnh bị lỗi hoặc không đọc được. Chỉ nhận được {len(loaded_samples)}/{SAMPLES_PER_USER} ảnh hợp lệ!",
                "danger"
            )
            return

        self._samples = loaded_samples
        for jpeg_bytes in self._samples:
            self._add_thumbnail(jpeg_bytes)

        self._pending_name = name
        self._attempt += 1
        self._update_progress()

        # Bật nút Đăng ký khi đã chọn đủ ảnh từ đĩa thành công
        self._set_form_inputs_enabled(False)
        self.submit_btn.configure(state="normal")
        self.cancel_btn.configure(state="normal")
        self._set_status(f"Đã chọn đủ {SAMPLES_PER_USER} ảnh từ máy. Bấm 'Đăng ký' để tiếp tục.", "success")

    def _submit_registration(self) -> None:
        """Người dùng bấm nút Đăng ký để tiến hành gửi dữ liệu lên server."""
        name = self._validate_form()
        if not name:
            return
        if len(self._samples) != SAMPLES_PER_USER:
            self._set_status(f"Cần đủ {SAMPLES_PER_USER} ảnh trước khi đăng ký!", "danger")
            return

        self._pending_name = name
        self._upload()

    def _cancel_capture(self) -> None:
        self._abort(silent=False)

    def _abort(self, silent: bool = False) -> None:
        """Dừng thu mẫu / bỏ qua kết quả upload đang chờ, trả form về trạng thái ban đầu."""
        if not (self._capturing or self._uploading or len(self._samples) > 0):
            return
        self._attempt += 1  # vô hiệu hoá phản hồi API đang bay
        self._capturing = False
        self._uploading = False
        self._samples.clear()
        self._clear_thumbnails()
        self._reset_progress()
        self._set_form_inputs_enabled(True)
        self.submit_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        if not silent:
            self._set_status("Đã huỷ đăng ký.", "muted")

    def _upload(self) -> None:
        """Gửi dữ liệu lên API ở thread nền (gọi api.register_user chỉ với họ tên và ảnh)."""
        self._capturing = False
        self._uploading = True
        attempt = self._attempt
        name, images = self._pending_name, list(self._samples)

        self._set_form_inputs_enabled(False)
        self.submit_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self._set_status(f"Đang gửi {len(images)} ảnh lên máy chủ...", "warning")

        # Tùy thuộc vào phương thức api.register_user của bạn nhận tham số nào (ví dụ: name, images hoặc code được server tự sinh)
        self.runner.submit(
            lambda: self.api.register_user(name, images),
            on_success=lambda msg: self._on_success(attempt, name, msg),
            on_error=lambda exc: self._on_error(attempt, exc),
        )

    def _on_success(self, attempt: int, name: str, message: str) -> None:
        if attempt != self._attempt:
            return
        self._uploading = False
        self._samples.clear()
        self._clear_thumbnails()
        self._reset_progress()
        self._set_form_inputs_enabled(True)
        self.submit_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.name_entry.delete(0, "end")
        self._set_status(f"{message} ({name})", "success")

    def _on_error(self, attempt: int, exc: Exception) -> None:
        if attempt != self._attempt:
            return
        self._uploading = False
        self._set_form_inputs_enabled(False)
        self.submit_btn.configure(state="normal")  # Cho phép bấm lại nếu lỗi
        self.cancel_btn.configure(state="normal")
        message = exc.message if isinstance(exc, ApiError) else f"Lỗi không xác định: {exc}"
        self._set_status(f"Đăng ký thất bại: {message}", "danger")

    # ------------------------------------------------------------------ #
    # Quản lý Thumbnail (Hiển thị ảnh thu nhỏ)
    # ------------------------------------------------------------------ #
    def _add_thumbnail(self, jpeg_bytes: bytes) -> None:
        """Tạo và hiển thị ảnh thu nhỏ lên khung lưới."""
        try:
            nparr = np.frombuffer(jpeg_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img_cv is None:
                return

            img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
            pil_img = PILImage.fromarray(img_rgb)

            ctk_img = ctk.CTkImage(
                light_image=pil_img,
                dark_image=pil_img,
                size=(55, 55)
            )

            self._thumbnail_images.append(ctk_img)

            idx = self._thumbnail_count
            row = idx // 4
            col = idx % 4

            lbl = ctk.CTkLabel(
                self.thumbnail_scroll,
                text="",
                image=ctk_img
            )

            lbl.grid(
                row=row,
                column=col,
                padx=4,
                pady=4
            )

            self._thumbnail_count += 1

        except Exception as e:
            print(f"Lỗi tạo thumbnail: {e}")

    def _clear_thumbnails(self) -> None:
        """Xóa sạch các widget ảnh thumbnail cũ."""
        for widget in self.thumbnail_scroll.winfo_children():
            widget.destroy()
        self._thumbnail_images.clear()
        self._thumbnail_count = 0

    # ------------------------------------------------------------------ #
    # Tiện ích UI
    # ------------------------------------------------------------------ #
    def _update_progress(self) -> None:
        n = len(self._samples)
        progress_val = min(n / SAMPLES_PER_USER, 1.0) if SAMPLES_PER_USER > 0 else 1.0
        self.progress.set(progress_val)
        self.progress_label.configure(text=f"{n} / {SAMPLES_PER_USER} ảnh")

    def _reset_progress(self) -> None:
        self.progress.set(0)
        self.progress_label.configure(text=f"0 / {SAMPLES_PER_USER} ảnh")

    def _set_form_inputs_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.name_entry.configure(state=state)
        self.start_btn.configure(state=state)
        self.upload_file_btn.configure(state=state)

    def _set_status(self, text: str, kind: str = "muted") -> None:
        self.status_label.configure(text=text, text_color=COLORS.get(kind, COLORS["muted"]))