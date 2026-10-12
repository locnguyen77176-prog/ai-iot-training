import sqlite3
from datetime import datetime


class DatabaseManager:
    """Quản lý lưu trữ sự kiện đếm người trong cơ sở dữ liệu SQLite."""

    def __init__(self, db_path: str = "database.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        """Khởi tạo bảng people_counts nếu chưa tồn tại và tự động bổ sung các cột mới nếu thiếu."""
        query = """
        CREATE TABLE IF NOT EXISTS people_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            track_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            gender TEXT DEFAULT 'Unknown',
            gender_confidence REAL DEFAULT 0.0,
            estimated_age TEXT DEFAULT 'Unknown'
        );
        """
        with self.conn:
            self.conn.execute(query)
            # Tự động migrate schema nếu database được tạo từ phiên bản cũ
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(people_counts)")
            existing_cols = [col[1] for col in cursor.fetchall()]
            
            if "gender" not in existing_cols:
                cursor.execute("ALTER TABLE people_counts ADD COLUMN gender TEXT DEFAULT 'Unknown'")
            if "gender_confidence" not in existing_cols:
                cursor.execute("ALTER TABLE people_counts ADD COLUMN gender_confidence REAL DEFAULT 0.0")
            if "estimated_age" not in existing_cols:
                cursor.execute("ALTER TABLE people_counts ADD COLUMN estimated_age TEXT DEFAULT 'Unknown'")
    def log_event(self, track_id: int, direction: str, gender: str = "Unknown",
                  gender_conf: float = 0.0, estimated_age: str = "Unknown") -> int:
        """Ghi nhận một sự kiện người đi qua vùng đếm vào SQLite."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        query = """
        INSERT INTO people_counts (timestamp, track_id, direction, gender, gender_confidence, estimated_age)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(query, (
                now_str, track_id, direction, gender,
                round(gender_conf, 2), estimated_age,
            ))
            return cursor.lastrowid

    def close(self):
        """Đóng kết nối database an toàn"""
        if self.conn:
            self.conn.close()
