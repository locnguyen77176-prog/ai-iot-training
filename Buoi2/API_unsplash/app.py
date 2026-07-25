"""
╔══════════════════════════════════════════════════════════════════╗
║         Unsplash Image Search  —  Streamlit App                 ║
║  Quy trình: Gọi API → Parse JSON → Lưu SQLite → Cache & Bench  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import random
import sqlite3
import logging
import requests
import streamlit as st
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# ─────────────────────────────────────────────────────────────────
# CẤU HÌNH
# ─────────────────────────────────────────────────────────────────
load_dotenv()

DB_PATH        = "unsplash_cache.db"   # File SQLite
CACHE_TTL      = 600                   # 10 phút (giây)
UNSPLASH_URL   = "https://api.unsplash.com/search/photos"
MAX_RETRIES    = 3                     # Số lần retry
RETRY_DELAYS   = [1, 2, 4]            # Exponential backoff (giây)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# PHẦN 1 — DATABASE HELPERS
# ─────────────────────────────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    """Khởi tạo database SQLite và bảng image_cache nếu chưa tồn tại."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS image_cache (
            query_key  TEXT PRIMARY KEY,
            json_data  TEXT NOT NULL,
            timestamp  REAL NOT NULL
        )
    """)
    conn.commit()
    log.info("SQLite DB khởi tạo tại: %s", DB_PATH)
    return conn


def get_cache(conn: sqlite3.Connection, query_key: str) -> dict | None:
    """
    Kiểm tra cache trong SQLite.
    Trả về dict JSON nếu Cache Hit (chưa quá TTL), None nếu Cache Miss.
    """
    row = conn.execute(
        "SELECT json_data, timestamp FROM image_cache WHERE query_key = ?",
        (query_key,)
    ).fetchone()

    if row is None:
        log.info("Cache MISS — query_key='%s'", query_key)
        return None

    json_data, ts = row
    age = time.time() - ts

    if age > CACHE_TTL:
        log.info("Cache EXPIRED (%.1fs > %ds) — query_key='%s'",
                 age, CACHE_TTL, query_key)
        return None

    log.info("Cache HIT (%.1fs tuổi) — query_key='%s'", age, query_key)
    return json.loads(json_data)


def save_cache(conn: sqlite3.Connection, query_key: str, data: list) -> None:
    """Lưu (hoặc cập nhật) kết quả vào SQLite cache."""
    conn.execute(
        """
        INSERT OR REPLACE INTO image_cache (query_key, json_data, timestamp)
        VALUES (?, ?, ?)
        """,
        (query_key, json.dumps(data, ensure_ascii=False), time.time())
    )
    conn.commit()
    log.info("Đã lưu %d ảnh vào cache — query_key='%s'",
             len(data), query_key)


def get_search_history(conn: sqlite3.Connection) -> list:
    """Lấy danh sách từ khóa đã tìm kiếm từ SQLite cache."""
    cursor = conn.execute("SELECT query_key FROM image_cache ORDER BY timestamp DESC")
    history = []
    for (q_key,) in cursor.fetchall():
        kw = q_key.split("::")[0].strip()
        if kw and kw not in history:
            history.append(kw)
    return history


# ─────────────────────────────────────────────────────────────────
# PHẦN 2 — API & PARSE
# ─────────────────────────────────────────────────────────────────

def fetch_api(access_key: str, query: str, per_page: int = 12) -> list:
    """
    Gọi Unsplash API với retry logic (exponential backoff).
    Trả về raw JSON results list hoặc raise Exception.
    """
    headers = {"Authorization": f"Client-ID {access_key}"}
    params  = {"query": query, "per_page": per_page, "orientation": "squarish"}

    for attempt in range(MAX_RETRIES):
        try:
            log.info("Gọi Unsplash API (lần %d/%d) — query='%s', per_page=%d",
                     attempt + 1, MAX_RETRIES, query, per_page)
            resp = requests.get(
                UNSPLASH_URL, headers=headers, params=params, timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])

            if resp.status_code == 401:
                raise PermissionError(
                    "❌ API Key không hợp lệ hoặc chưa được cấp quyền. "
                    "Kiểm tra lại UNSPLASH_ACCESS_KEY."
                )

            if resp.status_code == 403:
                raise PermissionError(
                    "❌ Truy cập bị từ chối. API Key có thể đã bị vô hiệu hóa."
                )

            if resp.status_code == 429:
                raise ConnectionError(
                    "⏳ Rate Limit đã bị vượt quá (HTTP 429). "
                    "Unsplash cho phép 50 req/giờ (demo key). Vui lòng thử lại sau."
                )

            resp.raise_for_status()   # bắt các lỗi HTTP khác

        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                log.warning("Lỗi mạng lần %d, thử lại sau %ds: %s",
                            attempt + 1, delay, exc)
                time.sleep(delay)
            else:
                raise ConnectionError(
                    f"❌ Không thể kết nối đến Unsplash API sau {MAX_RETRIES} lần thử. "
                    "Kiểm tra kết nối Internet."
                ) from exc

    return []   # fallback (không bao giờ đến đây trong thực tế)


def parse_json(raw_results: list) -> list:
    """
    Bước 3 — Chắt lọc các trường cần thiết từ raw API response.
    Chỉ giữ lại: id, description, user.name, user.links.html,
                 urls.small, urls.full
    """
    parsed = []
    for item in raw_results:
        try:
            parsed.append({
                "id":          item["id"],
                "description": item.get("description") or item.get("alt_description") or "",
                "user": {
                    "name": item["user"]["name"],
                    "html": item["user"]["links"]["html"],
                },
                "urls": {
                    "small": item["urls"]["small"],
                    "full":  item["urls"]["full"],
                },
            })
        except KeyError as exc:
            log.warning("Bỏ qua ảnh thiếu field: %s", exc)
    return parsed


# ─────────────────────────────────────────────────────────────────
# PHẦN 3 — DỊCH THUẬT
# ─────────────────────────────────────────────────────────────────

def translate_to_english(text: str) -> str:
    """
    Dịch văn bản sang Tiếng Anh bằng deep-translator (Google Translate).
    Trả về bản gốc nếu thất bại.
    """
    text = text.strip()
    if not text:
        return text
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(text)
        if translated and translated.lower() != text.lower():
            log.info("Dịch: '%s' → '%s'", text, translated)
        return translated or text
    except Exception as exc:
        log.warning("Không thể dịch '%s': %s", text, exc)
        return text


# ─────────────────────────────────────────────────────────────────
# PHẦN 4 — LOAD API KEY
# ─────────────────────────────────────────────────────────────────

def load_api_key() -> str | None:
    """
    Đọc API key theo thứ tự ưu tiên:
    1. st.secrets (Streamlit Cloud)
    2. os.environ / .env file (local)
    """
    # Streamlit Cloud
    try:
        key = st.secrets.get("UNSPLASH_ACCESS_KEY", "")
        if key:
            return key
    except Exception:
        pass

    # .env / biến môi trường
    key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    return key if key else None


# ─────────────────────────────────────────────────────────────────
# PHẦN 5 — ORCHESTRATE (tìm kiếm chính)
# ─────────────────────────────────────────────────────────────────

def search_images(
    conn: sqlite3.Connection,
    access_key: str,
    keyword: str,
    per_page: int,
) -> tuple[list, float, str, str]:
    """
    Điều phối toàn bộ quy trình:
      1. Dịch keyword → Tiếng Anh
      2. Kiểm tra SQLite Cache
      3. Nếu Cache Miss → Gọi API → Parse → Lưu Cache
    Trả về: (images, response_ms, source, translated_keyword)
    """
    en_keyword = translate_to_english(keyword)
    query_key  = f"{en_keyword.lower().strip()}::{per_page}"

    t_start = time.perf_counter()

    # Bước 1 — Kiểm tra cache
    cached = get_cache(conn, query_key)
    if cached is not None:
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        return cached, elapsed_ms, "🟢 SQLite Cache", en_keyword

    # Bước 2 — Gọi API
    raw_results = fetch_api(access_key, en_keyword, per_page)

    # Bước 3 — Parse JSON
    images = parse_json(raw_results)

    # Bước 4 — Lưu vào Cache
    if images:
        save_cache(conn, query_key, images)

    elapsed_ms = (time.perf_counter() - t_start) * 1000
    return images, elapsed_ms, "🔵 Unsplash API", en_keyword


def get_suggested_images(conn: sqlite3.Connection, access_key: str, per_page: int) -> tuple[list, str]:
    """
    Lấy hình ảnh gợi ý dựa trên lịch sử tìm kiếm trong SQLite.
    Nếu chưa có lịch sử -> dùng các chủ đề mặc định.
    Mỗi lần reload sẽ random/shuffle lại để giao diện luôn mới.
    """
    history = get_search_history(conn)
    if history:
        sample_size = min(len(history), 3)
        chosen_keywords = random.sample(history, k=sample_size)
        all_images = []
        for kw in chosen_keywords:
            imgs, _, _, _ = search_images(conn, access_key, kw, per_page)
            all_images.extend(imgs)
        
        # Loại bỏ ảnh trùng lặp theo ID
        unique_images = list({img["id"]: img for img in all_images}.values())
        random.shuffle(unique_images)
        suggested = unique_images[:per_page]
        tagline = f"Chủ đề từ lịch sử: {', '.join(chosen_keywords)}"
    else:
        default_topics = ["aesthetic wallpapers", "nature landscape", "city architecture", "minimalist art", "cozy coffee"]
        chosen_topic = random.choice(default_topics)
        suggested, _, _, _ = search_images(conn, access_key, chosen_topic, per_page)
        random.shuffle(suggested)
        tagline = f"Chủ đề ngẫu nhiên: {chosen_topic}"
        
    return suggested, tagline


def render_benchmark(elapsed_ms: float, source: str, count: int, translated: str, original: str) -> None:
    """Hiển thị thẻ benchmark / thống kê dạng nhỏ gọn."""
    cols = st.columns([1, 1, 1, 2])
    cols[0].caption(f"⏱️ **{elapsed_ms:.1f} ms**")
    cols[1].caption(f"📦 **{source}**")
    cols[2].caption(f"🖼️ **{count} ảnh**")
    if translated.lower() != original.lower():
         cols[3].caption(f"🌐 Dịch: **{original}** → **{translated}**")
    st.write("") # Spacer


def render_image_grid(images: list) -> None:
    """Hiển thị ảnh dạng Grid 4 cột."""
    COLS = 4
    for row_start in range(0, len(images), COLS):
        row_images = images[row_start: row_start + COLS]
        cols = st.columns(COLS)
        for col, img in zip(cols, row_images):
            with col:
                st.image(img["urls"]["small"], use_container_width=True)
                author_html = (
                    f'<a href="{img["user"]["html"]}?utm_source=unsplash_search_app'
                    f'&utm_medium=referral" target="_blank" '
                    f'style="font-size:0.8rem;color:#888;text-decoration:none;">'
                    f'📷 {img["user"]["name"]}</a>'
                )
                st.markdown(author_html, unsafe_allow_html=True)
                if img["description"]:
                    st.caption(img["description"][:60] +
                               ("…" if len(img["description"]) > 60 else ""))
                st.markdown(
                    f'<a href="{img["urls"]["full"]}" target="_blank" '
                    f'style="display:inline-block;margin-top:4px;padding:4px 10px;'
                    f'background:#1a73e8;color:white;border-radius:6px;'
                    f'font-size:0.75rem;text-decoration:none;">⬇️ Tải ảnh gốc</a>',
                    unsafe_allow_html=True,
                )


def main() -> None:
    # ── Page config ──────────────────────────────────────────────
    st.set_page_config(
        page_title="🔍 Unsplash Image Search",
        page_icon="🖼️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Custom CSS ────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    /* Ẩn header mặc định của Streamlit để giao diện tràn viền hơn */
    header {visibility: hidden;}
    
    /* Thanh tìm kiếm dán lên trên cùng */
    .stTextInput > div > div > input {
        border-radius: 30px;
        background-color: #2c2c2c;
        border: none;
        padding: 15px 25px;
        font-size: 1.1rem;
        color: white;
    }
    
    /* Grid ảnh */
    .stImage img { 
        border-radius: 16px; 
        transition: transform 0.2s, filter 0.2s;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3); 
        margin-bottom: 10px;
    }
    .stImage img:hover { 
        transform: scale(1.02);
        filter: brightness(1.1);
    }
    
    /* Loại bỏ khoảng trống thừa */
    .block-container {
        padding-top: 2rem;
        max-width: 95%;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        per_page = st.slider(
            "Số lượng hình ảnh",
            min_value=4, max_value=30, value=12, step=4,
            help="Số ảnh tối đa trả về mỗi lần tìm kiếm"
        )

        st.divider()
        st.caption(
            "Made with ❤️ · [Unsplash API](https://unsplash.com/developers)"
        )

    # ── Khởi tạo DB (chỉ một lần nhờ session_state) ──────────────
    if "db_conn" not in st.session_state:
        st.session_state.db_conn = init_db()
    conn = st.session_state.db_conn

    # ── Kiểm tra API Key ──────────────────────────────────────────
    access_key = load_api_key()
    if not access_key:
        st.error(
            "⚠️ **Chưa cấu hình Unsplash API Key!**\n\n"
            "**Local:** Tạo file `.env` với nội dung:\n"
            "```\nUNSPLASH_ACCESS_KEY=your_key_here\n```\n\n"
            "**Streamlit Cloud:** Vào *Settings → Secrets* và thêm:\n"
            "```toml\nUNSPLASH_ACCESS_KEY = \"your_key_here\"\n```\n\n"
            "👉 [Đăng ký API Key tại đây](https://unsplash.com/developers)"
        )
        st.stop()

    # ── Thanh tìm kiếm (không cần form, Enter là submit) ──────────
    keyword_input = st.text_input(
        "Tìm kiếm",
        placeholder="🔍 Nhập từ khóa (vd: phong cảnh, cats, aesthetic...) và nhấn Enter",
        label_visibility="collapsed",
    )
    
    # ── Xác định keyword để tìm (mặc định nếu trống) ──────────────
    keyword = keyword_input.strip()
    is_default = False
    tagline = ""

    if not keyword:
        is_default = True
        with st.spinner("⏳ Đang tổng hợp gợi ý từ lịch sử…"):
            images, tagline = get_suggested_images(conn, access_key, per_page)
    else:
        with st.spinner("⏳ Đang tìm kiếm hình ảnh…"):
            try:
                images, elapsed_ms, source, translated = search_images(
                    conn, access_key, keyword, per_page
                )
            except PermissionError as exc:
                st.error(str(exc))
                st.stop()
            except ConnectionError as exc:
                st.error(str(exc))
                st.stop()
            except Exception as exc:
                st.error(f"❌ Lỗi không xác định: {exc}")
                log.exception("Lỗi không xác định khi tìm kiếm '%s'", keyword)
                st.stop()

        # Chỉ hiển thị benchmark khi người dùng chủ động tìm kiếm
        render_benchmark(elapsed_ms, source, len(images), translated, keyword)

    if not images:
        st.info(
            f"🔎 Không tìm thấy hình ảnh nào. Hãy thử từ khóa khác."
        )
    else:
        if not is_default:
            st.markdown(
                f"### Kết quả cho: **\"{translated}\"**  "
                f"<span style='font-size:0.85rem;color:#888;font-weight:400;'>"
                f"({len(images)} ảnh)</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"### ✨ Gợi ý cho bạn  "
                f"<span style='font-size:0.85rem;color:#888;font-weight:400;'>"
                f"({tagline})</span>",
                unsafe_allow_html=True,
            )
            
        render_image_grid(images)

        # Attribution (Unsplash API Guidelines)
        st.markdown(
            "<br><div style='text-align:center;color:#aaa;font-size:0.8rem;'>"
            "Hình ảnh được cung cấp bởi "
            "<a href='https://unsplash.com/?utm_source=unsplash_search_app"
            "&utm_medium=referral' target='_blank' style='color:#888;'>Unsplash</a>"
            "</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
