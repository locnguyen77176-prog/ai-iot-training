from pydantic import BaseModel


class TextTranslateRequest(BaseModel):
    text: str
    source_lang: str = "vi"
    target_lang: str = "en"
