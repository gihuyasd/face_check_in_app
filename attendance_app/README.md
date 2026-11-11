Ứng dụng Điểm danh bằng Khuôn mặt (CustomTkinter + OpenCV)

Ứng dụng desktop thuần front-end giao tiếp với máy chủ API để thực hiện điểm danh, quản lý danh sách và đăng ký khuôn mặt học sinh/nhân viên.

1. Cài đặt & Chạy nhanh

Yêu cầu hệ thống: Python 3.9+ (Người dùng Linux cần cài thêm thư viện Tkinter: sudo apt install python3-tk).

Mở terminal tại thư mục attendance_app và chạy lần lượt các lệnh sau:

# 1. Tạo và kích hoạt môi trường ảo
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\activate
# Linux/macOS:          source .venv/bin/activate

# 2. Cài đặt các thư viện cần thiết
pip install -r requirements.txt

# 3. Thiết lập địa chỉ API (tùy chọn, mặc định: http://localhost:8000/api)
# Windows PowerShell:
$env:ATTENDANCE_API_URL="https://api.example.com/api"
# Linux/macOS:
# export ATTENDANCE_API_URL="https://api.example.com/api"

# 4. Khởi chạy ứng dụng
python -m src.main hoặc chạy file main.py


2. Cấu hình ứng dụng

Toàn bộ thông số như địa chỉ API, endpoint, thời gian trễ, chất lượng ảnh hay chỉ số camera (CAMERA_INDEX) được quản lý tập trung tại tệp:
src/utils/config.py

3. Khắc phục sự cố thường gặp

Lỗi không kết nối được máy chủ: Kiểm tra lại biến môi trường ATTENDANCE_API_URL hoặc đảm bảo server API của bạn đã được khởi động.

Không mở được camera: Tắt các ứng dụng đang chiếm quyền camera (như Zoom, Teams, Camera app của Windows) hoặc thay đổi CAMERA_INDEX trong config.py.