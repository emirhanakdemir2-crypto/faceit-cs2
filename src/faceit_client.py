from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from src.config import FACEIT_BASE_URL, MATCHES_RAW_DIR, RAW_DIR
from src.errors import faceit_http_message


class FaceitAPIError(Exception):
    """FACEIT API isteği başarısız olduğunda fırlatılır."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.user_message = user_message or message


class FaceitClient:
    def __init__(
        self,
        api_key: str,
        *,
        request_delay: float = 0.25,
        max_retries: int = 2,
    ) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            }
        )
        self._request_delay = request_delay
        self._max_retries = max_retries

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{FACEIT_BASE_URL}{path}"

        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                raise FaceitAPIError(
                    f"Bağlantı hatası: {exc}",
                    user_message=f"Ağ hatası: {exc}",
                ) from exc

            if response.status_code == 429 and attempt < self._max_retries:
                wait = self._request_delay * (2 ** (attempt + 2))
                time.sleep(wait)
                continue

            if not response.ok:
                user_msg = faceit_http_message(response.status_code)
                raise FaceitAPIError(
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                    user_message=user_msg,
                )

            time.sleep(self._request_delay)

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise FaceitAPIError(
                    "Geçersiz JSON yanıtı",
                    user_message="API geçersiz yanıt döndürdü.",
                ) from exc

            if not isinstance(payload, dict):
                return {"data": payload}
            return payload

        raise FaceitAPIError("İstek tamamlanamadı.")

    @staticmethod
    def _write_cache(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_player_by_nickname(self, nickname: str) -> dict[str, Any]:
        cache_path = RAW_DIR / f"{nickname.lower()}_player.json"
        data = self._get("/players", params={"nickname": nickname})
        self._write_cache(cache_path, data)
        return data

    def get_player_history(
        self,
        player_id: str,
        nickname: str,
        *,
        game: str = "cs2",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        cache_path = RAW_DIR / f"{nickname.lower()}_history.json"
        data = self._get(
            f"/players/{player_id}/history",
            params={"game": game, "limit": limit, "offset": offset},
        )
        self._write_cache(cache_path, data)
        return data

    def get_match_stats(self, match_id: str) -> dict[str, Any]:
        cache_path = MATCHES_RAW_DIR / f"{match_id}_stats.json"
        data = self._get(f"/matches/{match_id}/stats")
        self._write_cache(cache_path, data)
        return data
