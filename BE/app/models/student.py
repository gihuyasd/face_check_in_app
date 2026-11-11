from sqlalchemy import Column, String, DateTime, Text, Integer
from datetime import datetime
from app.database import Base
from sqlalchemy.orm import relationship

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_code = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    embedding_vector = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    attendances = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")