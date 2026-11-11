"""
async_utils.py
==============
Chạy tác vụ chậm (gọi API) ở luồng nền, rồi trả kết quả về LUỒNG GIAO DIỆN một cách an toàn.

Tkinter KHÔNG an toàn khi cập nhật widget từ thread khác, nên:
  - worker thread chỉ chạy hàm và đặt kết quả vào hàng đợi (queue),
  - luồng chính định kỳ (bằng `after`) lấy kết quả ra và gọi callback.
Nhờ vậy UI không bao giờ bị đơ khi mạng chậm.
"""

import queue
import threading
import traceback
from typing import Any, Callable, Optional


class AsyncRunner:
    def __init__(self, root, poll_ms: int = 50):
        self._root = root
        self._poll_ms = poll_ms
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._after_id: Optional[str] = None
        self._closed = False
        self._poll()

    def submit(
        self,
        fn: Callable[[], Any],
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """Chạy `fn()` ở thread nền; gọi on_success(kết quả) hoặc on_error(lỗi) ở luồng UI."""

        def worker():
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 - chuyển mọi lỗi về UI
                self._queue.put((on_error, exc))
            else:
                self._queue.put((on_success, result))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            while True:
                callback, payload = self._queue.get_nowait()
                if callback is not None:
                    try:
                        callback(payload)
                    except Exception:  # lỗi trong callback không được làm chết vòng poll
                        traceback.print_exc()
        except queue.Empty:
            pass
        self._after_id = self._root.after(self._poll_ms, self._poll)

    def close(self) -> None:
        self._closed = True
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
