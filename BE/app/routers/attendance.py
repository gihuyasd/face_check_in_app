from datetime import date as date_type, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.student import Student
from app.models.attendance import Attendance
from app.schemas.attendance import AttendanceDayResponse
from app.services.vision_service import FaceCheckinService
import numpy as np
import cv2


router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.get("/", response_model=AttendanceDayResponse)
def get_attendance_by_date(
        date: str | None = Query(None, description="Ngày cần lấy điểm danh, định dạng YYYY-MM-DD (Ví dụ: 2026-11-06)"),
        db: Session = Depends(get_db)
):
    """
    API lấy danh sách điểm danh theo ngày truyền vào.
    Ví dụ: GET /attendance/?date=2026-11-06
    """
    try:
        if date is None:
            # Lấy ngày hôm nay kiểu date object
            target_date = date_type.today()
            response_date = target_date.strftime("%Y-%m-%d")
        else:
            # Parse chuỗi người dùng nhập thành date object
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            response_date = target_date.strftime("%Y-%m-%d")

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Định dạng ngày không hợp lệ. Vui lòng sử dụng định dạng YYYY-MM-DD."
        )

    # Xác định khoảng thời gian bắt đầu và kết thúc trong ngày
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Truy vấn kết hợp bảng Attendance và Student
    results = (
        db.query(Attendance, Student)
        .join(Student, Attendance.student_id == Student.id)
        .filter(Attendance.check_in_time >= start_of_day)
        .filter(Attendance.check_in_time <= end_of_day)
        .all()
    )

    attendance_list = []
    for att, student in results:
        attendance_list.append({
            "attendance_id": att.id,
            "student_code": student.student_code,
            "full_name": student.full_name,
            "check_in_time": att.check_in_time,
            "status": att.status
        })

    return {
        "date": response_date,  # Trả về chuỗi YYYY-MM-DD (hoặc của hôm nay, hoặc của ngày user truyền)
        "total_checked_in": len(attendance_list),
        "data": attendance_list
    }


@router.post("/")
async def check_in(
        image: UploadFile = File(..., description="Ảnh chụp khuôn mặt gửi lên để điểm danh"),
        db: Session = Depends(get_db)
):
    face_service = FaceCheckinService()
    face_service.load_embeddings_from_db(db)

    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="File ảnh không hợp lệ hoặc không đọc được.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đọc file ảnh: {str(e)}")

    recognition_result = face_service.check_in(img)

    if not recognition_result["recognized"]:
        return {
            "attendance_id": -1,
            "student_code": "",
            "full_name": "",
            "check_in_time": datetime.now(),
            "status": "Fail",
            "message": recognition_result["message"]
        }

    student_code = recognition_result["user_code"]

    student = db.query(Student).filter(Student.student_code == student_code).first()
    if not student:
        raise HTTPException(status_code=404,
                            detail=f"Không tìm thấy sinh viên có mã {student_code} trong cơ sở dữ liệu.")

    today_start = datetime.combine(datetime.today().date(), datetime.min.time())
    today_end = datetime.combine(datetime.today().date(), datetime.max.time())

    existing_attendance = db.query(Attendance).filter(
        Attendance.student_id == student.id,
        Attendance.check_in_time >= today_start,
        Attendance.check_in_time <= today_end
    ).first()

    current_time = datetime.now()

    if existing_attendance:
        return {
            "attendance_id": existing_attendance.id,
            "student_code": student.student_code,
            "full_name": student.full_name,
            "check_in_time": existing_attendance.check_in_time,
            "status": "Already",
            "message": f"Sinh viên {student.full_name} đã điểm danh trước đó vào lúc {existing_attendance.check_in_time.strftime('%H:%M:%S')}."
        }

    attendance_status = "Present" if current_time.hour < 8 else "Late"

    new_attendance = Attendance(
        student_id=student.id,
        check_in_time=current_time,
        status=attendance_status
    )
    db.add(new_attendance)
    db.commit()
    db.refresh(new_attendance)

    return {
        "attendance_id": new_attendance.id,
        "student_code": student.student_code,
        "full_name": student.full_name,
        "check_in_time": new_attendance.check_in_time,
        "status": "Success",
        "message": f"Sinh viên {student.full_name} điểm danh thành công lúc {new_attendance.check_in_time.strftime('%H:%M:%S')}."
    }