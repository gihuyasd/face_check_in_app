from typing import List
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.student import Student
from app.models.attendance import Attendance
from app.schemas.student import StudentResponse
import os
import shutil
from datetime import datetime
from app.services.vision_service import FaceRegistrationService

DATA_URL = "././data/student_face_data"

router = APIRouter(prefix="/student", tags=["Student"])

@router.post("/", response_model=StudentResponse)
async def register_student(
    full_name: str = Form(..., description="Họ tên sinh viên đăng ký"),
    images: List[UploadFile] = File(..., description="Tập hợp nhiều ảnh khuôn mặt của sinh viên"),
    db: Session = Depends(get_db)
):
    next_id = get_newest_student(db)
    student_folder = os.path.join(DATA_URL, next_id)
    if os.path.exists(student_folder):
        for filename in os.listdir(student_folder):
            file_path = os.path.join(student_folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Không thể dọn dẹp thư mục cũ: {str(e)}")
    else:
        os.makedirs(student_folder, exist_ok=True)
    image_bytes_list = []
    for index, file in enumerate(images):
        contents = await file.read()
        image_bytes_list.append(contents)

        # Đặt tên file ảnh lưu trữ (ví dụ: img_1.jpg, img_2.jpg hoặc giữ nguyên tên gốc)
        file_extension = os.path.splitext(file.filename)[1] or ".jpg"
        save_filename = f"img_{index + 1}{file_extension}"
        save_path = os.path.join(student_folder, save_filename)

        with open(save_path, "wb") as f:
            f.write(contents)

    success, message, embedding_vector = FaceRegistrationService().register_student_face(next_id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail=message
        )

    try:
        new_student = Student(
            student_code=next_id,
            full_name=full_name,
            # student_data có thể chứa chuỗi embedding hoặc vector đã trích xuất từ service
            embedding_vector=str(embedding_vector)
        )
        db.add(new_student)
        db.commit()
        db.refresh(new_student)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi lưu sinh viên vào cơ sở dữ liệu: {str(e)}"
        )

    return {
        "student_code": next_id,
        "full_name": full_name,
        "created_at": datetime.now().isoformat(),
        "message": f"Đăng ký thành công cho sinh viên {full_name}, mssv: {next_id}."
    }


def get_newest_student(db: Session = Depends(get_db)):
    max_id = db.query(func.max(Student.id)).scalar()

    if max_id is None:
        next_id = 1
    else:
        next_id = max_id + 1

    if next_id < 10:
        return f"s0{next_id}"
    return f"s{next_id}"


