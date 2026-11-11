from contextlib import asynccontextmanager
from sys import prefix

from fastapi import FastAPI
from app.database import init_db
from app.routers import attendance, student


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Face Attendance API", lifespan=lifespan)
app.include_router(attendance.router, prefix = "/api")
app.include_router(student.router, prefix = "/api")


@app.get("/")
def root():
    return {"message": "Attendance API with Students & Attendance tables is ready!"}

@app.get("/api/health")
def health_check():
    """API kiểm tra trạng thái sức khỏe của server cho Frontend."""
    return {"status": "ok", "message": "Server is running smoothly"}