from pydantic import BaseModel

class StudentResponse(BaseModel):
    student_code: str
    full_name: str
    created_at: str
    message: str