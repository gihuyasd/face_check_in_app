from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import json

# Đường dẫn file SQLite lưu trong thư mục data/database.db
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/database.db"

# Tạo engine kết nối (check_same_thread=False bắt buộc cho SQLite trong môi trường async/multi-thread của FastAPI)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Tạo SessionLocal để tương tác với DB trong các request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class dùng để kế thừa cho các Models sau này
Base = declarative_base()

# Dependency để inject session vào các FastAPI Endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


import json
import os
import random
from datetime import datetime, time
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./data/database.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Tạo bảng, đọc dữ liệu student từ JSON và sinh ngẫu nhiên attendance cho các ngày 6, 7, 8 tháng 11 năm 2026"""
    from app.models.student import Student
    from app.models.attendance import Attendance

    # 1. Tạo các bảng nếu chưa tồn tại
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Kiểm tra nếu bảng students chưa có dữ liệu
        if db.query(Student).count() == 0:
            json_file_path = "./data/seed_data.json"

            if os.path.exists(json_file_path):
                print(f"--> Đang đọc dữ liệu từ {json_file_path}...")

                with open(json_file_path, "r", encoding="utf-8") as f:
                    seed_list = json.load(f)

                students_to_add = []
                for item in seed_list:
                    vector_str = json.dumps(item["embedding_vector"])

                    student = Student(
                        student_code=item["student_code"],
                        full_name=item["full_name"],
                        embedding_vector=vector_str
                    )
                    students_to_add.append(student)

                # Thêm sinh viên vào DB trước để lấy ID tự tăng (autoincrement)
                db.add_all(students_to_add)
                db.commit()
                print(f"--> Đã nạp thành công {len(students_to_add)} sinh viên từ file JSON!")

                # --- PHẦN NẠP SEED DATA CHO BẢNG ATTENDANCE ---
                print("--> Đang tạo lịch sử điểm danh ngẫu nhiên cho ngày 6, 7, 8 tháng 11 năm 2026...")

                # Danh sách các ngày cần seed
                attendance_dates = [
                    datetime(2026, 11, 6),
                    datetime(2026, 11, 7),
                    datetime(2026, 11, 8)
                ]

                attendance_records = []
                # Lấy lại danh sách sinh viên vừa được lưu vào DB (có kèm ID)
                all_students = db.query(Student).all()

                for student in all_students:
                    for base_date in attendance_dates:
                        # Random xác suất 80% sinh viên có đi học vào ngày đó
                        if random.random() < 0.8:
                            # Random giờ điểm danh trong khoảng từ 7:00 sáng đến 9:30 sáng
                            random_hour = random.randint(7, 9)
                            random_minute = random.randint(0, 59)
                            if random_hour == 9 and random_minute > 30:
                                random_minute = 30  # Giới hạn không quá 9:30 sáng

                            check_in_time = base_date.replace(hour=random_hour, minute=random_minute,
                                                              second=random.randint(0, 59))

                            status = "Late" if (
                                        random_hour > 7 or (random_hour == 7 and random_minute > 45)) else "Present"

                            attendance_record = Attendance(
                                student_id=student.id,
                                check_in_time=check_in_time,
                                status=status
                            )
                            attendance_records.append(attendance_record)

                if attendance_records:
                    db.add_all(attendance_records)
                    db.commit()
            else:
                print(f"--> Không tìm thấy file seed tại {json_file_path}, bỏ qua seed data.")
        else:
            print("--> Database đã có dữ liệu sinh viên, bỏ qua bước seed.")
    except Exception as e:
        db.rollback()
        print(f"Lỗi khi đọc file seed_data.json hoặc tạo attendance: {e}")
    finally:
        db.close()