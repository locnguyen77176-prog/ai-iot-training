import os
import sqlite3
from datetime import datetime
import cv2


class DatabaseManager:
    """
    Quản lý lưu trữ sự kiện đếm người và nhân khẩu học vào cơ sở dữ liệu SQLite.
    Hỗ trợ lưu ảnh chụp (snapshot) của người khi vượt qua vạch đếm.
    """
    def __init__(self, db_path: str = "database.db", save_snapshots: bool = True, snapshot_dir: str = "captures"):
        self.db_path = db_path
        self.save_snapshots = save_snapshots
        self.snapshot_dir = snapshot_dir

        if self.save_snapshots:
            os.makedirs(self.snapshot_dir, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        """Khởi tạo bảng people_counts nếu chưa tồn tại"""
        query = """
        CREATE TABLE IF NOT EXISTS people_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            track_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            gender TEXT DEFAULT 'Unknown',
            gender_confidence REAL DEFAULT 0.0,
            estimated_age TEXT DEFAULT 'Unknown',
            snapshot_path TEXT
        );
        """
        with self.conn:
            self.conn.execute(query)

    def log_event(self, track_id: int, direction: str, gender: str = "Unknown", 
                  gender_conf: float = 0.0, estimated_age: str = "Unknown", 
                  frame_snapshot=None) -> int:
        """
        Ghi nhận một sự kiện người cắt qua vạch vào SQLite.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        snapshot_path = None

        if self.save_snapshots and frame_snapshot is not None and frame_snapshot.size > 0:
            file_name = f"person_{track_id}_{direction}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:19]}.jpg"
            snapshot_path = os.path.join(self.snapshot_dir, file_name)
            try:
                cv2.imwrite(snapshot_path, frame_snapshot)
            except Exception as e:
                print(f"[DB] Lỗi lưu snapshot: {e}")
                snapshot_path = None

        query = """
        INSERT INTO people_counts (timestamp, track_id, direction, gender, gender_confidence, estimated_age, snapshot_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(query, (now_str, track_id, direction, gender, round(gender_conf, 2), estimated_age, snapshot_path))
            return cursor.lastrowid

    def get_summary(self) -> dict:
        """Lấy số liệu thống kê tổng hợp từ database"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM people_counts WHERE direction = 'IN'")
        total_in = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM people_counts WHERE direction = 'OUT'")
        total_out = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM people_counts WHERE gender IN ('Male', 'Nam')")
        male_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM people_counts WHERE gender IN ('Female', 'Nữ', 'Nu')")
        female_count = cursor.fetchone()[0]

        return {
            "total_in": total_in,
            "total_out": total_out,
            "male_count": male_count,
            "female_count": female_count
        }

    def close(self):
        """Đóng kết nối database an toàn"""
        if self.conn:
            self.conn.close()
