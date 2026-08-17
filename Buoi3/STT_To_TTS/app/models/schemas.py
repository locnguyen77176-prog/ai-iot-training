from typing import Optional
from pydantic import BaseModel

class TextTranslateRequest(BaseModel):
    text: str
    api_key: Optional[str] = None
    source_lang: str = "vi"
    target_lang: str = "en"
