import os
import cv2
import numpy as np
from deepface import DeepFace
from typing import Optional, Tuple, Any, List, Dict
from sqlalchemy.orm import Session
from app.models.student import Student
import json
from sklearn.metrics.pairwise import cosine_similarity
import re

DATA_URL = "././data/student_face_data"

class FaceRegistrationService:
    def __init__(self, train_base_dir: str = DATA_URL, model: str = "ArcFace", detector: str = "yunet"):
        self.train_base_dir = train_base_dir
        self.model = model
        self.detector = detector

    def register_student_face(self, student_code: str) -> Tuple[bool, str, Optional[np.ndarray]]:

        person_folder_path = os.path.join(self.train_base_dir, student_code)
        print(person_folder_path)
        if not os.path.exists(person_folder_path) or not os.path.isdir(person_folder_path):
            return False, f"Không tìm thấy thư mục dữ liệu ảnh của sinh viên: {student_code}", None

        # Lấy danh sách file ảnh hợp lệ
        image_files = [
            f for f in os.listdir(person_folder_path)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))
        ]

        if len(image_files) == 0:
            return False, f"Thư mục của sinh viên '{student_code}' không chứa file ảnh hợp lệ nào!", None

        database_embeddings = []

        print(f"\nĐang xử lý đăng ký khuôn mặt cho sinh viên: [{student_code}]")

        for img_name in image_files:
            img_path = os.path.join(person_folder_path, img_name)
            img = cv2.imread(img_path)
            if img is None:
                print("THẤT BẠI (Không đọc được file ảnh, file có thể bị hỏng)")
                continue

            try:
                results = DeepFace.represent(
                    img,
                    model_name=self.model,
                    detector_backend=self.detector,
                    align=True,
                    enforce_detection=True
                )

                if len(results) > 0:
                    embedding = np.array(results[0]["embedding"], dtype=np.float32)
                    database_embeddings.append(embedding)
            except ValueError as ve:
                print(f"LỖI DETECT: Không tìm thấy khuôn mặt nào trong ảnh này.")
            except Exception as e:
                print(f"LỖI KHÁC: {str(e)}")

        if len(database_embeddings) < 5:
            return False, f"Không thể trích xuất vector khuôn mặt của sinh viên {student_code}.", None

        embeddings_np = np.array(database_embeddings)

        # 1. Tính vector trung bình tạm thời để làm tâm cụm (centroid)
        temp_mean = np.mean(embeddings_np, axis=0)
        temp_mean = temp_mean / np.linalg.norm(temp_mean)  # Chuẩn hóa tâm

        # 2. Tính độ tương đồng cosine giữa mỗi embedding với tâm tạm thời
        # Vì các vector đều đã chuẩn hóa unit norm, dot product chính là cosine similarity
        similarities_to_center = np.dot(embeddings_np, temp_mean)

        # 3. Đặt ngưỡng lọc rác (Outlier Threshold)
        # Các vector có độ tương đồng thấp hơn ngưỡng này so với phần lớn các ảnh khác sẽ bị loại bỏ
        OUTLIER_THRESHOLD = 0.45

        valid_indices = np.where(similarities_to_center >= OUTLIER_THRESHOLD)[0]

        if len(valid_indices) < 3:
            return False, f"Quá nhiều ảnh nhiễu/rác. Chỉ giữ lại được {len(valid_indices)} ảnh hợp lệ sau khi lọc.", None

        filtered_embeddings = embeddings_np[valid_indices]
        print(f"Đã lọc: Giữ lại {len(filtered_embeddings)} / {len(embeddings_np)} vector sạch.")

        # ==========================================
        # TÍNH TRUNG BÌNH & CHUẨN HÓA CHÍNH THỨC
        # ==========================================
        mean_embedding = np.mean(filtered_embeddings, axis=0)
        norm = np.linalg.norm(mean_embedding)
        if norm > 0:
            mean_embedding = mean_embedding / norm

        print(f"Đăng ký thành công sinh viên {student_code} với {len(database_embeddings)} ảnh hợp lệ.")
        return True, "Đăng ký khuôn mặt thành công.", mean_embedding


class FaceCheckinService:
    def __init__(self, model_name: str = "ArcFace", detector_backend: str = "yunet", threshold: float = 0.55):
        self.model_name = model_name
        self.detector_backend = detector_backend
        self.threshold = threshold

        self.final_db_student_code: List[str] = []
        self.final_db_embeddings: Optional[np.ndarray] = None

    def load_embeddings_from_db(self, db: Session):
        students = db.query(Student).all()

        names = []
        embeddings = []

        for student in students:
            if student.embedding_vector:
                try:
                    emb_list = None
                    raw_emb = student.embedding_vector

                    if isinstance(raw_emb, str) and raw_emb.strip() != '':
                        raw_emb = raw_emb.strip()
                        try:
                            emb_list = json.loads(raw_emb)
                        except json.JSONDecodeError:
                            cleaned_str = raw_emb.replace("[", "").replace("]", "").strip()
                            emb_list = [float(x) for x in re.split(r'\s+', cleaned_str) if x]
                    elif isinstance(raw_emb, (list, tuple)):
                        emb_list = raw_emb

                    if emb_list:
                        emb = np.array(emb_list, dtype=np.float32)
                        emb = emb / np.linalg.norm(emb)

                        names.append(student.student_code)
                        embeddings.append(emb)
                except Exception as e:
                    print(f"Lỗi đọc embedding của sinh viên {student.student_code}: {e}")

        self.final_db_student_code = names
        if len(embeddings) > 0:
            self.final_db_embeddings = np.array(embeddings, dtype=np.float32)
        else:
            self.final_db_embeddings = np.zeros((0, 512), dtype=np.float32)

        print(f"Đã tải thành công {len(names)} vector embedding từ SQLite.")

    def check_in(self, img: np.ndarray) -> Dict[str, Any]:
        if self.final_db_embeddings is None or len(self.final_db_student_code) == 0:
            return {
                "recognized": False,
                "already_checked_in": False,
                "user_code": "",
                "full_name": "",
                "status": "error",
                "message": "Chưa nạp dữ liệu cơ sở dữ liệu khuôn mặt vào hệ thống."
            }

        try:
            results = DeepFace.represent(
                img,
                model_name=self.model_name,
                detector_backend=self.detector_backend,
                align=True,
                enforce_detection=True
            )

            if not results or len(results) == 0:
                return {
                    "recognized": False,
                    "already_checked_in": False,
                    "user_code": "",
                    "full_name": "",
                    "status": "not_found",
                    "message": "Không tìm thấy khuôn mặt trong ảnh."
                }

            test_embedding = np.array(results[0]["embedding"], dtype=np.float32)
            test_embedding = test_embedding / np.linalg.norm(test_embedding)

            similarities = cosine_similarity([test_embedding], self.final_db_embeddings)[0]

            best_match_idx = np.argmax(similarities)
            max_score = float(similarities[best_match_idx])
            predicted_name = self.final_db_student_code[best_match_idx]

            if max_score >= self.threshold:
                return {
                    "recognized": True,
                    "already_checked_in": False,
                    "user_code": predicted_name,
                    "full_name": predicted_name,
                    "status": "success",
                    "message": f"Nhận diện thành công {predicted_name} với độ tương đồng {max_score:.4f}"
                }
            else:
                return {
                    "recognized": False,
                    "already_checked_in": False,
                    "user_code": "",
                    "full_name": "",
                    "status": "rejected",
                    "message": f"Khuôn mặt không khớp vui lòng thử lại."
                }

        except ValueError:
            return {
                "recognized": False,
                "already_checked_in": False,
                "user_code": "",
                "full_name": "",
                "status": "no_face",
                "message": "Không tìm thấy khuôn mặt trong ảnh."
            }
        except Exception as e:
            return {
                "recognized": False,
                "already_checked_in": False,
                "user_code": "",
                "full_name": "",
                "status": "error",
                "message": f"Lỗi xử lý hệ thống: {str(e)}"
            }