"""
vision.py
=========
Tiện ích camera phía client. KHÔNG nhận diện danh tính (việc đó do máy chủ làm qua API);
ở đây chỉ có:

  - Camera           : bọc cv2.VideoCapture (mở / đọc / đóng an toàn).
  - FaceDetector     : phát hiện "có khuôn mặt hay không" bằng Haar Cascade để
                       (1) vẽ khung lên video, (2) chỉ gửi ảnh lên API khi thật sự có mặt.
  - encode_jpeg      : mã hoá khung hình thành JPEG bytes để upload.
  - frame_to_ctkimage / blank_ctkimage : hiển thị khung hình lên CTkLabel.
"""

from typing import List, Optional, Tuple

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image

from src.utils.config import CAMERA_INDEX, FACE_MIN_SIZE, JPEG_QUALITY

Box = Tuple[int, int, int, int]  # (x, y, w, h)


class Camera:
    def __init__(self, index: int = CAMERA_INDEX):
        self.index = index
        self._cap: Optional[cv2.VideoCapture] = None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> bool:
        """Mở camera. Trả về False nếu không mở được (không có / đang bị chiếm)."""
        self.release()
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap = cap
        return True

    def read(self) -> Optional[np.ndarray]:
        if not self.is_open:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        return cv2.flip(frame, 1)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class FaceDetector:

    def __init__(self):
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(path)
        if self._cascade.empty():
            raise RuntimeError(f"Không nạp được Haar Cascade: {path}")

    def detect(self, frame_bgr: np.ndarray) -> List[Box]:
        """Trả về danh sách khung mặt, lớn nhất trước."""
        gray = cv2.equalizeHist(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY))
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.2, minNeighbors=5,
            minSize=(FACE_MIN_SIZE, FACE_MIN_SIZE),
        )
        boxes = [tuple(int(v) for v in f) for f in faces]
        boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        return boxes


def encode_jpeg(frame_bgr: np.ndarray, quality: int = JPEG_QUALITY) -> bytes:
    """Mã hoá khung hình BGR thành JPEG bytes. Gọi TRƯỚC khi vẽ khung lên ảnh."""
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("Không mã hoá được ảnh JPEG.")
    return buf.tobytes()

def _fit_frame(frame_bgr: np.ndarray, size: Tuple[int, int], cover: bool = False) -> np.ndarray:
    tw, th = size
    h, w = frame_bgr.shape[:2]
    scale = max(tw / w, th / h) if cover else min(tw / w, th / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(frame_bgr, (nw, nh), interpolation=interp)

    if cover:  # cắt phần thừa ở giữa
        x0, y0 = (nw - tw) // 2, (nh - th) // 2
        return resized[y0:y0 + th, x0:x0 + tw]

    canvas = np.zeros((th, tw, 3), dtype=np.uint8)
    x0, y0 = (tw - nw) // 2, (th - nh) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = resized
    return canvas


def frame_to_ctkimage(frame_bgr: np.ndarray, size: Tuple[int, int], cover: bool = False) -> ctk.CTkImage:
    rgb = cv2.cvtColor(_fit_frame(frame_bgr, size, cover), cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)


def blank_ctkimage(size: Tuple[int, int], color: str = "#0b0d12") -> ctk.CTkImage:
    """Ảnh nền đặc, dùng làm placeholder khi camera tắt."""
    pil_img = Image.new("RGB", size, color)
    return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
