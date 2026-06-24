from __future__ import annotations


def faceit_http_message(status_code: int | None, *, context: str = "") -> str:
    """HTTP durum koduna göre kullanıcı dostu Türkçe mesaj döndürür."""
    prefix = f"{context}: " if context else ""

    if status_code == 401:
        return f"{prefix}API key hatalı veya .env okunmuyor."
    if status_code == 403:
        return f"{prefix}Yetki/key tipi sorunu — Server-side API key kullandığınızdan emin olun."
    if status_code == 404:
        return f"{prefix}Oyuncu bulunamadı veya oyun verisi yok."
    if status_code == 429:
        return f"{prefix}Rate limit aşıldı — kısa süre sonra tekrar deneyin."

    if status_code is not None:
        return f"{prefix}API hatası (HTTP {status_code})."
    return f"{prefix}Bilinmeyen API hatası."
