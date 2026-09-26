import os
import re
import asyncio
from typing import Optional
from fastapi import HTTPException, status
import ctranslate2
import transformers

from app.core.config import (
    TRANSLATION_MODEL_DIR,
    TRANSLATION_DEVICE,
    TRANSLATION_COMPUTE_TYPE
)

_generator: Optional[ctranslate2.Generator] = None
_tokenizer: Optional[transformers.AutoTokenizer] = None
_active_device: str = "cpu"


def init_translation_model():
    """Khởi tạo và nạp model Qwen2.5-1.5B-Instruct (CTranslate2) lên GPU/CPU + Warmup."""
    global _generator, _tokenizer, _active_device

    if not os.path.exists(TRANSLATION_MODEL_DIR):
        print(f"[NMT Error] Không tìm thấy thư mục model: {TRANSLATION_MODEL_DIR}")
        return

    print(f"=== Nạp Qwen2.5-1.5B Local NMT Engine ({TRANSLATION_DEVICE.upper()} - {TRANSLATION_COMPUTE_TYPE})... ===")
    
    try:
        _tokenizer = transformers.AutoTokenizer.from_pretrained(
            TRANSLATION_MODEL_DIR,
            fix_markdown=False
        )
    except Exception as e:
        print(f"[NMT Error] Lỗi nạp tokenizer: {e}")
        return

    # Thử nạp trên CUDA trước, nếu lỗi tự động fallback sang CPU
    device = TRANSLATION_DEVICE
    compute_type = TRANSLATION_COMPUTE_TYPE
    try:
        _generator = ctranslate2.Generator(
            TRANSLATION_MODEL_DIR,
            device=device,
            compute_type=compute_type,
            intra_threads=4 if device == "cpu" else 1
        )
        _active_device = device
    except Exception as e:
        print(f"[NMT Warning] Không thể nạp trên {device} ({e}). Đang fallback sang CPU...")
        try:
            _generator = ctranslate2.Generator(
                TRANSLATION_MODEL_DIR,
                device="cpu",
                compute_type="int8",
                intra_threads=4
            )
            _active_device = "cpu"
        except Exception as err:
            print(f"[NMT Error] Lỗi nạp model trên CPU: {err}")
            return

    # Warmup GPU
    try:
        _warmup_prompt = (
            "<|im_start|>system\n"
            "You are a professional translator. Translate Vietnamese to natural English. Return only the translated sentence.<|im_end|>\n"
            "<|im_start|>user\n"
            "Xin chào<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        tokens = _tokenizer.convert_ids_to_tokens(_tokenizer.encode(_warmup_prompt))
        _ = _generator.generate_batch(
            [tokens],
            max_length=16,
            sampling_topp=0.8,
            sampling_temperature=0.1,
            include_prompt_in_result=False,
            end_token=["<|im_end|>", "<|endoftext|>"]
        )
        print(f"[NMT] Qwen2.5-1.5B Local Model đã được Warmup thành công ({_active_device.upper()} Ready)!")
    except Exception as e:
        print(f"[NMT Warning] Warmup translation model thất bại: {e}")


def get_translation_info() -> dict:
    return {
        "model": "Qwen2.5-1.5B-Instruct (CTranslate2 Local)",
        "device": _active_device,
        "compute_type": TRANSLATION_COMPUTE_TYPE,
        "status": "ready" if _generator is not None else "not_loaded"
    }


def _clean_output_text(text: str) -> str:
    """Loại bỏ các thẻ ChatML, markdown hoặc khoảng trắng thừa."""
    text = re.sub(r"<\|im_start\|>.*", "", text, flags=re.DOTALL)
    text = re.sub(r"<\|im_end\|>.*", "", text, flags=re.DOTALL)
    text = text.strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    return text


def _run_local_translation(text: str, source_lang: str, target_lang: str) -> str:
    global _generator, _tokenizer

    if _generator is None or _tokenizer is None:
        init_translation_model()

    if _generator is None or _tokenizer is None:
        raise RuntimeError("Model dịch thuật Qwen2.5-1.5B chưa được nạp.")

    if source_lang == "vi" and target_lang == "en":
        system_msg = (
            "You are a professional translator. "
            "Translate the Vietnamese text to fluent, natural English. "
            "Return ONLY the translated text without explanations or quotation marks."
        )
    elif source_lang == "en" and target_lang == "vi":
        system_msg = (
            "You are a professional translator. "
            "Translate the English text to fluent, natural Vietnamese. "
            "Return ONLY the translated text without explanations or quotation marks."
        )
    else:
        system_msg = (
            f"You are a professional translator. "
            f"Translate from {source_lang} to {target_lang}. "
            f"Return ONLY the translated text without explanations or quotation marks."
        )

    prompt = (
        f"<|im_start|>system\n{system_msg}<|im_end|>\n"
        f"<|im_start|>user\n{text}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    tokens = _tokenizer.convert_ids_to_tokens(_tokenizer.encode(prompt))
    
    # Tối ưu hóa: Greedy Decoding (sampling_topk=1) cho tốc độ cực đại và độ chính xác cao nhất
    results = _generator.generate_batch(
        [tokens],
        max_length=120,
        sampling_topk=1,
        include_prompt_in_result=False,
        end_token=["<|im_end|>", "<|endoftext|>"]
    )

    output_tokens = results[0].sequences[0]
    raw_output = _tokenizer.decode(_tokenizer.convert_tokens_to_ids(output_tokens))
    return _clean_output_text(raw_output)


async def translate_text(
    text: str,
    source_lang: str = "vi",
    target_lang: str = "en"
) -> str:
    """
    Dịch văn bản 100% Local bằng model Qwen2.5-1.5B-Instruct (CTranslate2).
    Hoàn toàn Offline, không phụ thuộc API Key hay kết nối Internet.
    """
    cleaned_input = text.strip()
    if not cleaned_input:
        return ""

    try:
        translated = await asyncio.to_thread(
            _run_local_translation,
            cleaned_input,
            source_lang,
            target_lang
        )
        return translated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi dịch thuật Local Qwen: {str(e)}"
        )
