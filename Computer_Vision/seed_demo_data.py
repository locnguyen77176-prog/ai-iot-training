import sys
import sqlite3
import random
from datetime import datetime, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def seed_data(db_path="database.db", target_in=158, target_out=89):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS people_counts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        track_id INTEGER NOT NULL,
        direction TEXT NOT NULL,
        gender TEXT DEFAULT 'Unknown',
        gender_confidence REAL DEFAULT 0.0,
        estimated_age TEXT DEFAULT 'Unknown'
    );
    """)

    cursor.execute("SELECT COUNT(*) FROM people_counts")
    existing = cursor.fetchone()[0]

    if existing >= (target_in + target_out):
        print(f"[Seed] Đã có {existing} bản ghi trong database.")
        conn.close()
        return

    now = datetime.now()
    print(f"[Seed] Đang tạo dữ liệu mẫu thực tế ({target_in} IN, {target_out} OUT)...")

    # Tạo các lượt IN
    for i in range(target_in):
        delta_minutes = random.randint(1, 480)
        t = now - timedelta(minutes=delta_minutes)
        cursor.execute("""
            INSERT INTO people_counts (timestamp, track_id, direction, gender, gender_confidence, estimated_age)
            VALUES (?, ?, ?, 'Unknown', 0.0, 'Unknown')
        """, (t.strftime("%Y-%m-%d %H:%M:%S"), i + 1, "IN"))

    # Tạo các lượt OUT
    for i in range(target_out):
        delta_minutes = random.randint(1, 400)
        t = now - timedelta(minutes=delta_minutes)
        cursor.execute("""
            INSERT INTO people_counts (timestamp, track_id, direction, gender, gender_confidence, estimated_age)
            VALUES (?, ?, ?, 'Unknown', 0.0, 'Unknown')
        """, (t.strftime("%Y-%m-%d %H:%M:%S"), target_in + i + 1, "OUT"))

    conn.commit()
    conn.close()
    print("[Seed] Khởi tạo dữ liệu mẫu thành công!")


if __name__ == "__main__":
    seed_data()
