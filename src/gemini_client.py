from __future__ import annotations

import logging
from typing import Any

from src.ai_prompt import build_coaching_prompt
from src.config import GEMINI_DEFAULT_MODEL, get_gemini_api_key

logger = logging.getLogger(__name__)

GEMINI_UNAVAILABLE = "Gemini AI yorumu alınamadı"


def generate_coaching_comment(processed_payload: dict[str, Any]) -> str:
    """
    İşlenmiş özetten Gemini AI koçluk yorumu üretir.
    Hata durumunda uygulama çökmez; hata mesajı döner.
    """
    try:
        api_key = get_gemini_api_key()
    except ValueError:
        return f"{GEMINI_UNAVAILABLE}: API anahtarı yapılandırılmamış."

    prompt = build_coaching_prompt(processed_payload)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=2048,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            return GEMINI_UNAVAILABLE
        return text

    except ImportError:
        logger.exception("google-genai paketi yüklü değil")
        return f"{GEMINI_UNAVAILABLE}: google-genai paketi yüklü değil."
    except Exception as exc:
        logger.exception("Gemini API hatası")
        return f"{GEMINI_UNAVAILABLE}: {type(exc).__name__}"
