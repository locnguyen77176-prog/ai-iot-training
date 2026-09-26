"""
Script Weather API Benchmark với SQLite Cache
Thực hiện gọi OpenWeatherMap API, lưu cache vào SQLite và so sánh hiệu năng (Benchmark Metrics).
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Đảm bảo UTF-8 encoding cho console trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Nạp biến môi trường từ file .env ở cùng thư mục với script
load_dotenv(Path(__file__).resolve().with_name(".env"))

# Các hằng số cấu hình
CACHE_DB_PATH = "weather_cache.db"
CACHE_TTL_SECONDS = 600.0  # 10 phút
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()


class WeatherCache:
    """Quản lý lưu trữ và truy vấn dữ liệu thời tiết bằng SQLite."""

    def __init__(self, db_path: str = CACHE_DB_PATH, ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        # Khởi tạo cache và tạo bảng nếu chưa tồn tại
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Mở kết nối đến file database SQLite."""
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        """Tạo bảng cache nếu database chưa có bảng này."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weather_cache (
                    city TEXT PRIMARY KEY,
                    json_data TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()

    def get(self, city: str) -> Optional[Dict[str, Any]]:
        """
        Kiểm tra dữ liệu cache cho một thành phố.
        - Nếu có dữ liệu và còn trong thời gian TTL -> cache hit.
        - Nếu không có hoặc đã quá hạn -> cache miss.
        """
        city_key = city.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT json_data, timestamp FROM weather_cache WHERE city = ?",
                (city_key,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            json_str, timestamp = row
            current_time = time.time()
            if current_time - timestamp <= self.ttl_seconds:
                return json.loads(json_str)
            return None

    def set(self, city: str, data: Dict[str, Any]) -> None:
        """Lưu dữ liệu thời tiết vào SQLite cùng thời gian ghi nhận."""
        city_key = city.strip().lower()
        json_str = json.dumps(data, ensure_ascii=False)
        current_time = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO weather_cache (city, json_data, timestamp) VALUES (?, ?, ?)",
                (city_key, json_str, current_time)
            )
            conn.commit()

    def clear(self) -> None:
        """Xóa toàn bộ dữ liệu cache trong database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM weather_cache")
            conn.commit()


class WeatherFetcher:
    """Lớp lấy dữ liệu thời tiết từ OpenWeatherMap hoặc dùng dữ liệu giả nếu không có key."""

    API_URL = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self, api_key: Optional[str] = None) -> None:
        # Nếu không có key hợp lệ thì chuyển sang chế độ mock data
        is_placeholder = not api_key or api_key == "your_openweather_api_key_here"
        self.api_key = None if is_placeholder else api_key
        self.session = self._create_resilient_session()

    def _create_resilient_session(self) -> requests.Session:
        """Tạo session HTTP có cơ chế thử lại khi gọi API thất bại."""
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch(self, city: str = "Hanoi") -> Dict[str, Any]:
        """
        Lấy dữ liệu thời tiết cho thành phố.
        Nếu có API key thì gọi API thật, nếu không thì dùng dữ liệu giả.
        """
        if not self.api_key:
            # Mock Data Mode: Giả lập delay mạng 300ms
            time.sleep(0.3)
            return {
                "city_name": city.capitalize(),
                "temp": 29.5,
                "description": "mây rải rác (mock)",
                "humidity": 75
            }

        params = {
            "q": city,
            "appid": self.api_key,
            "units": "metric",
            "lang": "vi"
        }

        try:
            response = self.session.get(self.API_URL, params=params, timeout=10)
            response.raise_for_status()
            raw_data = response.json()

            # Trích xuất 4 trường cần thiết
            return {
                "city_name": raw_data.get("name", city.capitalize()),
                "temp": float(raw_data.get("main", {}).get("temp", 0.0)),
                "description": str(raw_data.get("weather", [{}])[0].get("description", "không xác định")),
                "humidity": int(raw_data.get("main", {}).get("humidity", 0))
            }
        except requests.RequestException as exc:
            # Fallback sang Mock khi gặp lỗi mạng/API để Benchmark không crash
            print(f"⚠️ Cảnh báo gọi API gặp lỗi ({exc}). Chuyển sang Mock Data fallback.")
            time.sleep(0.3)
            return {
                "city_name": city.capitalize(),
                "temp": 29.5,
                "description": "mây rải rác (fallback)",
                "humidity": 75
            }


class WeatherService:
    """Lớp điều phối: kiểm tra cache trước, rồi mới gọi fetcher nếu cần."""

    def __init__(self, cache: WeatherCache, fetcher: WeatherFetcher) -> None:
        self.cache = cache
        self.fetcher = fetcher

    def get_weather(self, city: str = "Hanoi", use_cache: bool = True) -> Tuple[Dict[str, Any], bool, float]:
        """
        Lấy thông tin thời tiết cho thành phố.
        Trả về bộ ba: (dữ liệu, có phải cache hit, thời gian phản hồi tính bằng ms).
        """
        start_time = time.perf_counter()

        if use_cache:
            cached_data = self.cache.get(city)
            if cached_data is not None:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return cached_data, True, elapsed_ms

        # Cache Miss hoặc không dùng Cache -> Gọi API/Mock
        api_data = self.fetcher.fetch(city)

        if use_cache:
            self.cache.set(city, api_data)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return api_data, False, elapsed_ms


def run_benchmark(num_requests: int = 100, city: str = "Hanoi") -> None:
    """
    Chạy thử nghiệm benchmark để so sánh hiệu năng:
    - không dùng cache
    - có dùng cache SQLite
    """
    cache = WeatherCache()
    fetcher = WeatherFetcher(api_key=OPENWEATHER_API_KEY)
    service = WeatherService(cache=cache, fetcher=fetcher)

    mode_str = "OpenWeatherMap API" if fetcher.api_key else "Mock Data (Latency 300ms)"
    print(f"\n🚀 ĐANG KHỞI CHẠY BENCHMARK... ({num_requests} Requests, Thành phố: '{city}')")
    print(f"📌 Chế độ dữ liệu: {mode_str}\n")

    # --- ĐỢT 1: KHÔNG DÙNG CACHE ---
    # Gọi mỗi request trực tiếp mà không kiểm tra cache
    print("⏳ Đang chạy Đợt 1: KHÔNG DÙNG CACHE (Force API/Mock)...")
    no_cache_latencies: List[float] = []
    no_cache_hits = 0
    no_cache_start = time.perf_counter()

    for _ in range(num_requests):
        _, is_hit, latency_ms = service.get_weather(city=city, use_cache=False)
        no_cache_latencies.append(latency_ms)
        if is_hit:
            no_cache_hits += 1

    no_cache_total_time = time.perf_counter() - no_cache_start

    # --- ĐỢT 2: CÓ DÙNG CACHE ---
    # Gọi lại cùng một lượng request, nhưng lần này dùng cache SQLite
    print("⏳ Đang chạy Đợt 2: CÓ DÙNG CACHE (SQLite)...")
    cache.clear()  # Xóa cache cũ trước khi bắt đầu thử nghiệm
    cache_latencies: List[float] = []
    cache_hits = 0
    cache_start = time.perf_counter()

    for _ in range(num_requests):
        _, is_hit, latency_ms = service.get_weather(city=city, use_cache=True)
        cache_latencies.append(latency_ms)
        if is_hit:
            cache_hits += 1

    cache_total_time = time.perf_counter() - cache_start

    # --- TÍNH TOÁN METRICS ---
    # Tính trung bình thời gian, tốc độ tăng tốc và số request tiết kiệm được
    no_cache_avg_ms = sum(no_cache_latencies) / num_requests if num_requests > 0 else 0.0
    cache_avg_ms = sum(cache_latencies) / num_requests if num_requests > 0 else 0.0

    no_cache_hit_rate = (no_cache_hits / num_requests) * 100.0
    cache_hit_rate = (cache_hits / num_requests) * 100.0

    speedup = no_cache_total_time / cache_total_time if cache_total_time > 0 else 1.0
    saved_api_requests = cache_hits

    # --- IN BÁO CÁO DẠNG BẢNG CONSOLE ---
    # Xuất kết quả dưới dạng bảng để dễ so sánh
    col_w1, col_w2, col_w3 = 34, 22, 26

    def format_row(c1: str, c2: str, c3: str) -> str:
        return f"| {c1:<{col_w1}} | {c2:<{col_w2}} | {c3:<{col_w3}} |"

    separator = "+" + "-" * (col_w1 + 2) + "+" + "-" * (col_w2 + 2) + "+" + "-" * (col_w3 + 2) + "+"

    print("\n" + "=" * 87)
    print("                       BÁO CÁO KẾT QUẢ BENCHMARK CACHE THỜI TIẾT".center(87))
    print("=" * 87)
    print(separator)
    print(format_row("Tiêu chí Đo Lường", "KHÔNG CACHE", "CÓ CACHE (SQLite)"))
    print(separator)
    print(format_row("Tổng số Requests", f"{num_requests}", f"{num_requests}"))
    print(format_row("Số lượt Cache Hit (🟢)", f"{no_cache_hits} ({no_cache_hit_rate:.1f}%)", f"{cache_hits} ({cache_hit_rate:.1f}%)"))
    print(format_row("Số lượt Cache Miss (🔴)", f"{num_requests - no_cache_hits}", f"{num_requests - cache_hits}"))
    print(format_row("Lượt gọi API thật / Mock", f"{num_requests}", f"{num_requests - cache_hits}"))
    print(format_row("Tổng thời gian thực thi", f"{no_cache_total_time:.3f} s", f"{cache_total_time:.3f} s"))
    print(format_row("Response Time trung bình", f"{no_cache_avg_ms:.2f} ms", f"{cache_avg_ms:.2f} ms"))
    print(format_row("Response Time nhỏ nhất (Min)", f"{min(no_cache_latencies):.2f} ms", f"{min(cache_latencies):.2f} ms"))
    print(format_row("Response Time lớn nhất (Max)", f"{max(no_cache_latencies):.2f} ms", f"{max(cache_latencies):.2f} ms"))
    print(format_row("Tốc độ tăng tốc (Speedup)", "1.00x (Gốc)", f"{speedup:.2f}x Nhanh hơn 🚀"))
    print(format_row("Số API Request tiết kiệm được", "0 (0.0%)", f"{saved_api_requests} ({saved_api_requests/num_requests*100:.1f}%)"))
    print(separator + "\n")


if __name__ == "__main__":
    # Khởi tạo các đối tượng chính của chương trình
    cache = WeatherCache()
    fetcher = WeatherFetcher(api_key=OPENWEATHER_API_KEY)
    service = WeatherService(cache=cache, fetcher=fetcher)

    print("=" * 60)
    print("        HỆ THỐNG TRUY VẤN THỜI TIẾT & BENCHMARK CACHE")
    print("=" * 60)

    # 1. Người dùng nhập tên thành phố
    city_input = input("Nhập tên thành phố muốn kiểm tra (Vi du: Hanoi): ").strip()
    city = city_input if city_input else "Hanoi"

    # 2. Truy vấn và hiển thị thông tin thời tiết
    print(f"\n🔍 Đang truy xuất thông tin thời tiết cho '{city}'...")
    try:
        weather_data, is_hit, elapsed = service.get_weather(city=city, use_cache=True)
        
        status_str = "🟢 CACHE HIT (Lấy từ SQLite)" if is_hit else "🔴 CACHE MISS (Gọi API/Mock)"
        
        print("\n" + "-" * 50)
        print(f"   THÔNG TIN THỜI TIẾT TẠI {weather_data['city_name'].upper()}")
        print("-" * 50)
        print(f"📍 Thành phố:    {weather_data['city_name']}")
        print(f"🌡️ Nhiệt độ:     {weather_data['temp']}°C")
        print(f"☁️ Trạng thái:   {weather_data['description']}")
        print(f"💧 Độ ẩm:        {weather_data['humidity']}%")
        print(f"⏱️ Latency:      {elapsed:.2f} ms ({status_str})")
        print("-" * 50 + "\n")
    except Exception as e:
        print(f"❌ Lỗi khi lấy dữ liệu thời tiết: {e}")

    # 3. Hỏi người dùng có muốn chạy Benchmark không
    run_bench = input("Bạn có muốn chạy thử nghiệm Benchmark (100 Requests) không? (y/N): ").strip().lower()
    if run_bench in ["y", "yes"]:
        run_benchmark(num_requests=100, city=city)
    else:
        print("👋 Cảm ơn bạn đã sử dụng chương trình!")

