"""
===============================================================================
Enterprise Gemini Chatbot CLI
-------------------------------------------------------------------------------
File: gemini_chatbot.py
Mục đích: Chatbot tương tác CLI chuẩn Production, kết nối với Gemini API
           thông qua SDK chính thức `google-genai` kết hợp giao diện Rich CLI,
           tích hợp nhận biết thời gian thực và dữ liệu thời tiết sống (Open-Meteo).
Tính năng:
  - Tự động nạp Thời Gian Thực (Ngày/Tháng/Năm, Thứ, Giờ) vào System Context.
  - Xử lý chuẩn hóa Tiếng Việt (chống lỗi chính tả/dấu) khi nhận diện địa điểm.
  - Tự động truy vấn Dữ liệu Thời tiết Thời gian thực từ Open-Meteo API (Free).
  - Sử dụng model `gemini-3.5-flash-lite` tối ưu quota free tier, phản hồi cực nhanh.
  - Giao diện CLI chuyên nghiệp render Markdown bằng thư viện `rich`.
  - Tích hợp Spinner hoạt họa sinh động khi chờ phản hồi từ Gemini API.
  - Nạp API Key an toàn từ file .env bằng `python-dotenv`.
  - Tích hợp Retry tự động với Exponential Backoff qua thư viện `tenacity`.
  - Đo thời gian phản hồi (Latency ms) chính xác bằng `time.perf_counter()`.
===============================================================================
"""

import os
import sys
import re
import time
import datetime
import json
import urllib.request
import logging
from typing import Optional
from dotenv import load_dotenv

# Tự động điều chỉnh Encoding trên Windows Terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thư viện Rich Render Giao diện CLI Chuyên nghiệp
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.logging import RichHandler

# Thư viện Google GenAI SDK chính thức
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types
# pyrefly: ignore [missing-import]
from google.genai.errors import APIError

# Thư viện Tenacity quản lý Retry
from tenacity import (
    retry,
    stop_after_attempt,
    wait_chain,
    wait_fixed,
    retry_if_exception,
    RetryCallState,
)

# -----------------------------------------------------------------------------
# 1. Khởi tạo Rich Console & Cấu hình Logging Hệ thống
# -----------------------------------------------------------------------------
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger("GeminiChatbot")


# -----------------------------------------------------------------------------
# 2. Tiện ích Chuẩn hóa Tiếng Việt & Dữ liệu Thời tiết (Open-Meteo API)
# -----------------------------------------------------------------------------
def remove_vn_accent(s: str) -> str:
    """Loại bỏ dấu tiếng Việt để so sánh khớp từ khóa địa điểm linh hoạt."""
    s = s.lower()
    s = re.sub(r'[àáảãạăằắẳẵặâầấẩẫậ]', 'a', s)
    s = re.sub(r'[èéẻẽẹêềếểễệ]', 'e', s)
    s = re.sub(r'[ìíỉĩị]', 'i', s)
    s = re.sub(r'[òóỏõọôồốổỗộơờớởỡợ]', 'o', s)
    s = re.sub(r'[ùúủũụưừứửữự]', 'u', s)
    s = re.sub(r'[ỳýỷỹỵ]', 'y', s)
    s = re.sub(r'[đ]', 'd', s)
    return s


CITIES_GEO = {
    "ha noi": {"name": "Hà Nội", "lat": 21.0285, "lon": 105.8542},
    "hanoi": {"name": "Hà Nội", "lat": 21.0285, "lon": 105.8542},
    "hcm": {"name": "TP. Hồ Chí Minh", "lat": 10.8231, "lon": 106.6297},
    "sai gon": {"name": "TP. Hồ Chí Minh", "lat": 10.8231, "lon": 106.6297},
    "ho chi minh": {"name": "TP. Hồ Chí Minh", "lat": 10.8231, "lon": 106.6297},
    "da nang": {"name": "Đà Nẵng", "lat": 16.0544, "lon": 108.2022},
    "danang": {"name": "Đà Nẵng", "lat": 16.0544, "lon": 108.2022},
    "can tho": {"name": "Cần Thơ", "lat": 10.0452, "lon": 105.7469},
    "hai phong": {"name": "Hải Phòng", "lat": 20.8449, "lon": 106.6881},
    "nha trang": {"name": "Nha Trang", "lat": 12.2388, "lon": 109.1967},
    "da lat": {"name": "Đà Lạt", "lat": 11.9404, "lon": 108.4583},
    "dalat": {"name": "Đà Lạt", "lat": 11.9404, "lon": 108.4583},
    "hue": {"name": "Huế", "lat": 16.4637, "lon": 107.5909},
    "vung tau": {"name": "Vũng Tàu", "lat": 10.3460, "lon": 107.0843},
}

WEATHER_CODES = {
    0: "Trời quang, nắng đẹp",
    1: "Ít mây, nắng nhẹ",
    2: "Mây rải rác",
    3: "Nhiều mây, u ám",
    45: "Có sương mù",
    48: "Sương mù đóng băng",
    51: "Mưa phùn nhẹ",
    53: "Mưa phùn vừa",
    55: "Mưa phùn hạt to",
    61: "Mưa rào nhẹ",
    63: "Mưa vừa",
    65: "Mưa to, mưa rào nặng hạt",
    80: "Mưa rào rải rác",
    81: "Mưa rào vừa",
    82: "Mưa rào rất to",
    95: "Có dông bão, sấm sét",
    96: "Có dông kèm mưa đá nhỏ",
    99: "Có dông bão kèm mưa đá lớn",
}


def get_realtime_weather(city_key: str = "ha noi") -> str:
    """Lấy dữ liệu thời tiết thời gian thực từ Open-Meteo API (Miễn phí, không cần API Key)."""
    city = CITIES_GEO.get(city_key, CITIES_GEO["ha noi"])
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={city['lat']}&longitude={city['lon']}&"
            f"current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&"
            f"timezone=Asia%2FHo_Chi_Minh"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("current", {})

        temp = data.get("temperature_2m", "N/A")
        app_temp = data.get("apparent_temperature", "N/A")
        humidity = data.get("relative_humidity_2m", "N/A")
        precip = data.get("precipitation", 0.0)
        code = data.get("weather_code", 0)
        wind = data.get("wind_speed_10m", "N/A")
        status = WEATHER_CODES.get(code, "Thời tiết bình thường")

        return (
            f"Dữ liệu thời tiết thời gian thực tại {city['name']}:\n"
            f"- Trạng thái: {status}\n"
            f"- Nhiệt độ: {temp}°C (Cảm giác thực tế: {app_temp}°C)\n"
            f"- Độ ẩm: {humidity}%\n"
            f"- Lượng mưa: {precip} mm\n"
            f"- Tốc độ gió: {wind} km/h"
        )
    except Exception as e:
        logger.warning(f"Không thể truy vấn thời tiết thời gian thực: {e}")
        return f"Dữ liệu thời tiết thời gian thực: Hiện không thể tải từ máy chủ thời tiết tại {city['name']}."


# -----------------------------------------------------------------------------
# 3. Định nghĩa hàm kiểm tra Lỗi Transient (Để làm điều kiện Retry)
# -----------------------------------------------------------------------------
def is_transient_error(exception: BaseException) -> bool:
    """
    Xác định xem ngoại lệ có phải là lỗi tạm thời (transient) để Retry hay không.
    - Lỗi mạng: ConnectionError, TimeoutError, OSError -> Retry
    - Lỗi API (APIError): Retry nếu không phải lỗi 401/403 (Invalid Key) hoặc 404 (Not Found)
    """
    if isinstance(exception, (ConnectionError, TimeoutError, OSError)):
        return True

    if isinstance(exception, APIError):
        status_code = getattr(exception, "code", None)
        if status_code in (401, 403, 404):
            logger.error(f"❌ Lỗi API [Status {status_code}]: {exception}. Không thực hiện Retry.")
            return False
        return True

    return False


def log_retry_attempt(retry_state: RetryCallState) -> None:
    """Callback được gọi trước mỗi lần chờ Retry để ghi log cảnh báo (Warning)."""
    attempt = retry_state.attempt_number
    exception = retry_state.outcome.exception() if retry_state.outcome else "Unknown error"
    
    next_action = retry_state.next_action
    sleep_seconds = next_action.sleep if next_action else 0.0

    logger.warning(
        f"⚠️ [RETRY WARNING] Phát hiện lỗi transient ({exception.__class__.__name__}: {exception}). "
        f"Đang thử lại lần {attempt}/4 sau {sleep_seconds:.1f}s..."
    )


# -----------------------------------------------------------------------------
# 4. Lớp Chatbot Doanh Nghiệp (GeminiChatbot Class)
# -----------------------------------------------------------------------------
class GeminiChatbot:
    """Lớp quản lý kết nối và giao tiếp với Google Gemini API."""

    # Sử dụng model gemini-3.5-flash-lite có dung lượng quota miễn phí cao nhất
    MODEL_NAME = "gemini-3.5-flash-lite"
    
    BASE_SYSTEM_INSTRUCTION = (
        "Bạn là AIOT Assistant, một trợ lý AI chuyên nghiệp, thông minh và thân thiện. "
        "Hãy đưa ra câu trả lời ngắn gọn, cô đọng, đi thẳng vào trọng tâm (tối đa 300 từ) "
        "và luôn trình bày bằng định dạng Markdown đẹp mắt."
    )

    def __init__(self) -> None:
        """Khởi tạo Client kết nối API với API Key từ môi trường."""
        self.api_key = self._load_api_key()
        
        try:
            self.client = genai.Client(api_key=self.api_key)
            logger.info("✅ Khởi tạo Gemini API Client thành công!")
        except Exception as e:
            logger.critical(f"💥 Lỗi không thể khởi tạo GenAI Client: {e}")
            sys.exit(1)

    @staticmethod
    def _load_api_key() -> str:
        """Tải API Key từ file .env hoặc môi trường. Dừng chương trình nếu thiếu."""
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key or not api_key.strip():
            logger.critical(
                "❌ KHÔNG TÌM THẤY GEMINI_API_KEY!\n"
                "   Vui lòng tạo file '.env' trong thư mục gốc và thêm dòng:\n"
                "   GEMINI_API_KEY=your_actual_api_key_here"
            )
            sys.exit(1)
            
        return api_key.strip()

    def _build_dynamic_config(self, prompt: str) -> types.GenerateContentConfig:
        """
        Tạo cấu hình động chứa mốc Thời Gian Thực và Dữ liệu Thời Tiết sống (Open-Meteo).
        """
        now = datetime.datetime.now()
        days_vn = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        day_str = days_vn[now.weekday()]
        
        time_context = (
            f"MỐC THỜI GIAN THỰC HIỆN TẠI HỆ THỐNG:\n"
            f"- Thứ trong tuần: {day_str}\n"
            f"- Ngày/Tháng/Năm: {now.strftime('%d/%m/%Y')}\n"
            f"- Giờ hệ thống: {now.strftime('%H:%M:%S')} (Múi giờ Asia/Ho_Chi_Minh - UTC+7)\n"
            f"Bạn PHẢI nhận biết chính xác mốc thời gian thực này để trả lời các câu hỏi liên quan đến ngày tháng, thời gian hoặc hôm nay."
        )

        weather_context = ""
        clean_prompt = remove_vn_accent(prompt)
        weather_keywords = ["thoi tiet", "thuoi tiet", "thoi", "mua", "nhiet do", "nang", "du bao", "khi hau"]

        if any(kw in clean_prompt for kw in weather_keywords):
            target_city_key = "ha noi"
            # Tìm kiếm thành phố trùng khớp trong prompt đã bỏ dấu
            for city_k in CITIES_GEO:
                if city_k in clean_prompt:
                    target_city_key = city_k
                    break
            
            weather_data = get_realtime_weather(target_city_key)
            weather_context = f"\n\n[CẬP NHẬT THỜI TIẾT THỜI GIAN THỰC VỆ TINH]\n{weather_data}"

        full_system_instruction = (
            f"{self.BASE_SYSTEM_INSTRUCTION}\n\n"
            f"[NGƯỜI CUNG CẤP BỐI CẢNH HỆ THỐNG]\n"
            f"{time_context}"
            f"{weather_context}"
        )

        return types.GenerateContentConfig(
            system_instruction=full_system_instruction,
            temperature=0.7,
        )

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_chain(
            wait_fixed(2.0),
            wait_fixed(4.0),
            wait_fixed(8.0),
            wait_fixed(10.0),
        ),
        retry=retry_if_exception(is_transient_error),
        before_sleep=log_retry_attempt,
        reraise=True,
    )
    def _call_api_with_retry(self, prompt: str) -> str:
        """Thực hiện gọi API tới Gemini với cơ chế Retry tự động của Tenacity."""
        config = self._build_dynamic_config(prompt)
        response = self.client.models.generate_content(
            model=self.MODEL_NAME,
            contents=prompt,
            config=config,
        )

        if not response or not hasattr(response, "text") or not response.text:
            raise ValueError("API trả về phản hồi rỗng (Empty Response) hoặc bị chặn bởi Safety Filters.")

        return response.text.strip()

    def ask_gemini_api(self, prompt: str) -> Optional[str]:
        """Hàm bao gói public cho phép gọi prompt, bắt lỗi chi tiết và trả về kết quả."""
        try:
            return self._call_api_with_retry(prompt)

        except APIError as e:
            code = getattr(e, 'code', None)
            if code == 429:
                logger.error("⚠️ Hạn ngạch API (Quota/Rate Limit) bị giới hạn. Vui lòng đợi 30-60 giây rồi thử lại.")
            else:
                logger.error(f"❌ Lỗi Gemini API [Code {code}]: {e.message if hasattr(e, 'message') else e}")
            return None

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"🌐 Lỗi kết nối mạng: Không thể kết nối tới máy chủ Gemini. Chi tiết: {e}")
            return None

        except ValueError as e:
            logger.error(f"⚠️ Lỗi dữ liệu phản hồi: {e}")
            return None

        except Exception as e:
            logger.error(f"💥 Lỗi không xác định: {e}", exc_info=True)
            return None


# -----------------------------------------------------------------------------
# 5. Luồng Chạy Main CLI Interface Với Rich Terminal UI
# -----------------------------------------------------------------------------
def main() -> None:
    """Luồng điều khiển Terminal CLI chính của ứng dụng Chatbot với Rich UI."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]🤖 GEMINI API CHATBOT - AIOT ASSISTANT[/bold cyan]\n"
            "[dim]Real-time Time Context & Live Open-Meteo Weather Integration[/dim]\n\n"
            "👉 [yellow]Mẹo:[/yellow] Gõ [bold green]'exit'[/bold green] hoặc [bold green]'quit'[/bold green] để thoát.",
            title="[bold magenta]AIOT Platform[/bold magenta]",
            border_style="cyan",
            padding=(1, 3),
        )
    )
    console.print()

    chatbot = GeminiChatbot()

    while True:
        try:
            user_input = Prompt.ask("\n[bold yellow]👤 Bạn[/bold yellow]").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                console.print("\n[bold blue]👋 Cảm ơn bạn đã sử dụng AIOT Assistant. Tạm biệt![/bold blue]\n")
                break

            answer: Optional[str] = None
            latency_ms: float = 0.0

            # Sử dụng Rich Status Spinner hoạt họa khi chờ API
            with console.status("[bold cyan]🔄 AIOT Assistant đang truy vấn & xử lý...[/bold cyan]", spinner="dots"):
                start_time = time.perf_counter()
                answer = chatbot.ask_gemini_api(user_input)
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000

            if answer:
                md_content = Markdown(answer)
                console.print()
                console.print(
                    Panel(
                        md_content,
                        title="[bold green]🤖 AIOT Assistant[/bold green]",
                        subtitle=f"[dim cyan]⏱️ Latency: {latency_ms:.2f} ms | Model: {GeminiChatbot.MODEL_NAME}[/dim cyan]",
                        border_style="green",
                        padding=(1, 2),
                    )
                )
            else:
                console.print()
                console.print(
                    Panel(
                        "[bold red]❌ Không thể lấy phản hồi từ AIOT Assistant.[/bold red]\nVui lòng kiểm tra log hệ thống hoặc thử lại sau.",
                        title="[bold red]Lỗi Phản Hồi[/bold red]",
                        border_style="red",
                    )
                )

        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[bold yellow]👋 Nhận tín hiệu ngắt (Ctrl+C). Tạm biệt![/bold yellow]\n")
            break


if __name__ == "__main__":
    main()
