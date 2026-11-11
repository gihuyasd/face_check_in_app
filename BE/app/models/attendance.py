from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey
from datetime import datetime
from app.database import Base
from sqlalchemy.orm import relationship

class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)  # Khóa ngoại liên kết tới student
    check_in_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="Present")

    student = relationship("Student", back_populates="attendances")