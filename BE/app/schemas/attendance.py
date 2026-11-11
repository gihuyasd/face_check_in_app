from pydantic import BaseModel
from datetime import datetime
from typing import List

class AttendanceItem(BaseModel):
    attendance_id: int
    student_code: str
    full_name: str
    check_in_time: datetime
    status: str

    class Config:
        from_attributes = True

class AttendanceDayResponse(BaseModel):
    date: str
    total_checked_in: int
    data: List[AttendanceItem]

    class Config:
        from_attributes = True

class AttendanceItemAdd(BaseModel):
    attendance_id: int
    student_code: str
    full_name: str
    check_in_time: datetime
    status: str
    message: str

    class Config:
        from_attributes = True