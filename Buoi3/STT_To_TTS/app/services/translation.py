import os
import asyncio
from typing import Optional
from fastapi import HTTPException, status
from google import genai
from google.genai import types
from app.core.config import GEMINI_MODEL

# [OPT-3a] Cache Gemini client theo API key, tránh tạo mới mỗi request
gemini_client_cache: dict[str, genai.Client] = {}

# [OPT-3b] Pre-build config objects cho 2 chiều dịch → không allocate mỗi request
_CONFIG_VI_TO_EN = types.GenerateContentConfig(
    system_instruction=(
        "You are a professional translator. "
        "Translate Vietnamese to natural English. "
        "Return only the translated sentence. "
        "Do not add any extra text or explanations."
    ),
    temperature=0.1,
    max_output_tokens=256,
)

_CONFIG_EN_TO_VI = types.GenerateContentConfig(
    system_instruction=(
        "You are a professional translator. "
        "Translate English to natural Vietnamese. "
        "Return only the translated sentence. "
        "Do not add any extra text or explanations."
    ),
    temperature=0.1,
    max_output_tokens=256,
)

# [OPT-3d] Pre-build prompt template, chỉ format text lúc runtime
_PROMPT_VI_TO_EN = "Translate the following Vietnamese text to natural English. Return only the translation, no explanations:\n{text}"
_PROMPT_EN_TO_VI = "Translate the following English text to natural Vietnamese. Return only the translation, no explanations:\n{text}"

def get_gemini_client(api_key: str) -> genai.Client:
    global gemini_client_cache
    if api_key not in gemini_client_cache:
        gemini_client_cache[api_key] = genai.Client(api_key=api_key)
    return gemini_client_cache[api_key]

async def translate_text(
    text: str,
    source_lang: str = "vi",
    target_lang: str = "en",
    api_key: Optional[str] = None
) -> str:
    """
    Dịch giữa Tiếng Việt và Tiếng Anh bằng Gemini API.

    Optimizations:
    - [OPT-3b] Dùng pre-built GenerateContentConfig thay vì tạo mới mỗi call
    - [OPT-3d] Prompt template gọn hơn, giảm input token cho Gemini
    - [OPT-4]  asyncio.wait_for timeout 15s tránh request treo vô hạn
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gemini API Key chưa được cung cấp. Vui lòng nhập API Key trên giao diện web hoặc cấu hình GEMINI_API_KEY."
        )

    try:
        client = get_gemini_client(key)

        # Determine translation direction: en->vi or vi->en
        if source_lang == "en" and target_lang == "vi":
            prompt = _PROMPT_EN_TO_VI.format(text=text)
            config = _CONFIG_EN_TO_VI
        elif source_lang == "vi" and target_lang == "en":
            prompt = _PROMPT_VI_TO_EN.format(text=text)
            config = _CONFIG_VI_TO_EN
        else:
            # Default: assume vi->en for unsupported language pairs
            prompt = _PROMPT_VI_TO_EN.format(text=text)
            config = _CONFIG_VI_TO_EN

        # [OPT-4] Timeout 15s: nếu Gemini không phản hồi, trả lỗi ngay thay vì treo
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=prompt,
                config=config,
            ),
            timeout=15.0
        )
        translated = response.text.strip() if getattr(response, "text", None) else ""
        return translated

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Gemini API timeout sau 15 giây. Vui lòng thử lại."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi Gemini Translation API: {str(e)}"
        )

