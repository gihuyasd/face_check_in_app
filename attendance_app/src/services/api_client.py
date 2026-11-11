"""
api_client.py
=============
Tầng DỊCH VỤ (Service) - nơi DUY NHẤT trong app nói chuyện với máy chủ.
Views không dùng `requests` trực tiếp, chỉ gọi các phương thức của `ApiClient`.

Hợp đồng API mà client mong đợi (chi tiết xem README.md):

  GET  /health
  POST /attendance/check-in   multipart: image
        -> {"recognized": bool, "already_checked_in": bool,
            "user": {"user_code", "full_name"}, "status", "checked_at", "message"}
  GET  /attendance?date=YYYY-MM-DD   (không có date = tất cả)
        -> {"items": [{"user_code","full_name","checked_at","status"}, ...]}  hoặc mảng trực tiếp
  POST /users/register        multipart: user_code, full_name, images (nhiều file)
        -> 2xx {"message": "..."}   | 4xx/5xx {"message"|"detail"|"error": "..."}

Mọi lỗi (mất mạng, timeout, HTTP lỗi) đều được quy về `ApiError` với thông điệp tiếng Việt
dễ hiểu để View hiển thị trực tiếp.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from src.utils.config import (
    API_BASE_URL,
    API_TIMEOUT,
    API_TOKEN,
    EP_CHECKIN,
    EP_HEALTH,
    EP_RECORDS,
    EP_REGISTER,
    LATE_KEYWORDS,
)


class ApiError(Exception):
    """Lỗi khi gọi API. `status_code` = None nếu lỗi mạng / timeout."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --------------------------------------------------------------------------- #
# Hàm tiện ích dùng chung cho views
# --------------------------------------------------------------------------- #
def is_late_status(status: str) -> bool:
    """True nếu chuỗi trạng thái cho thấy là 'đi muộn'."""
    s = (status or "").lower()
    return any(k in s for k in LATE_KEYWORDS)


def time_part(timestamp: str) -> str:
    """Lấy phần giờ HH:MM:SS từ chuỗi 'YYYY-MM-DD HH:MM:SS' hoặc ISO 'YYYY-MM-DDTHH:MM:SS'."""
    ts = str(timestamp or "")
    return ts[11:19] if len(ts) >= 19 else ts


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL, token: str = API_TOKEN,
                 timeout: float = API_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Session giữ kết nối TCP, nhanh hơn khi gọi liên tục (điểm danh real-time).
        # requests.Session dùng đa luồng ở mức đọc/gửi đơn giản như ở đây là chấp nhận được.
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    # ----------------------------- nội bộ ---------------------------------- #
    @staticmethod
    def _extract_message(resp: requests.Response) -> str:
        """Lấy thông điệp lỗi từ body JSON (message / detail / error), nếu không có thì dùng mã HTTP."""
        try:
            data = resp.json()
            if isinstance(data, dict):
                for key in ("message", "detail", "error"):
                    value = data.get(key)
                    if isinstance(value, str) and value:
                        return value
                    if isinstance(value, list) and value:  # kiểu lỗi validation của FastAPI
                        first = value[0]
                        if isinstance(first, dict) and "msg" in first:
                            return str(first["msg"])
        except ValueError:
            pass
        return f"Máy chủ trả về lỗi {resp.status_code}."

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.Timeout as exc:
            raise ApiError("Máy chủ phản hồi quá lâu (timeout).") from exc
        except requests.ConnectionError as exc:
            raise ApiError(f"Không kết nối được tới máy chủ ({self.base_url}).") from exc
        except requests.RequestException as exc:
            raise ApiError(f"Lỗi mạng: {exc}") from exc

        if not resp.ok:
            raise ApiError(self._extract_message(resp), resp.status_code)
        try:
            return resp.json()
        except ValueError:
            return {}

    # ----------------------------- public API ------------------------------ #
    def ping(self) -> bool:
        """
        Kiểm tra máy chủ có phản hồi hay không. Chỉ cần nhận được 1 phản hồi HTTP (< 500)
        là coi như 'đã kết nối' (kể cả khi server không có endpoint /health).
        Ném ApiError nếu không liên lạc được.
        """
        try:
            resp = self.session.get(f"{self.base_url}{EP_HEALTH}", timeout=5)
        except requests.RequestException as exc:
            raise ApiError("Không kết nối được tới máy chủ.") from exc
        if resp.status_code >= 500:
            raise ApiError(f"Máy chủ lỗi {resp.status_code}.", resp.status_code)
        return True

    def check_in(self, image_jpeg: bytes) -> Dict[str, Any]:
        data = self._request(
            "POST", EP_CHECKIN,
            files={"image": ("frame.jpg", image_jpeg, "image/jpeg")},
        )
        data = data if isinstance(data, dict) else {}
        student_code = data.get("student_code") or ""
        full_name = data.get("full_name") or ""

        return {
            "recognized": True if data.get("status") != "Fail" else False,
            "already_checked_in": True if data.get("status") == "Already" else False,
            "student_code": str(student_code),
            "full_name": str(full_name),
            "status": str(data.get("status") or ""),
            "checked_at": str(data.get("check_in_time") or ""),
            "message": str(data.get("message")),
        }

    def get_records(self, date: Optional[str] = None) -> List[Dict[str, str]]:
        """Lấy lịch sử điểm danh (mới nhất trước)."""
        params = {}
        if date is not None:
            params["date"] = date
        data = self._request("GET", EP_RECORDS, params=params)

        if isinstance(data, dict):
            items = data.get("data") or []
        else:
            items = data
        if not isinstance(items, list):
            raise ApiError("Dữ liệu danh sách điểm danh không đúng định dạng.")
        records = []
        for it in items:
            if not isinstance(it, dict):
                continue
            raw_time = it.get("check_in_time") or ""

            time_only = raw_time[11:19] if len(raw_time) >= 19 else raw_time

            records.append({
                "student_code": str(it.get("student_code") or ""),
                "full_name": str(it.get("full_name") or ""),
                "check_in_time": str(time_only),
                "status": str(it.get("status") or ""),
            })
        records.sort(key=lambda r: r["check_in_time"], reverse=True)
        return records

    def register_user(self, full_name: str, images: List[bytes]) -> str:
        """Đăng ký người dùng mới kèm các ảnh khuôn mặt (JPEG). Trả về thông điệp từ server."""
        files = [("images", (f"face_{i:02d}.jpg", img, "image/jpeg"))
                 for i, img in enumerate(images, start=1)]
        data = self._request(
            "POST", EP_REGISTER,
            data={"full_name": full_name},
            files=files,
        )
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])
        return "Đăng ký thành công."
