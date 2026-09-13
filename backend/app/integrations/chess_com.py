from __future__ import annotations

import random
import time
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..errors import AppError
from ..protocols import ArchiveFetchResult, ArchiveRef


class ChessComClient:
    base_url = "https://api.chess.com/pub"

    def __init__(self, client: httpx.Client | None = None):
        settings = get_settings()
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(20.0, connect=8.0),
            headers={"User-Agent": settings.chess_com_user_agent, "Accept-Encoding": "gzip"},
        )

    def _request(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        for attempt in range(4):
            try:
                response = self.client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                if attempt == 3:
                    raise AppError("chess_com_network", "无法连接 Chess.com，已有数据不受影响", status_code=503) from exc
                time.sleep(0.3 * (2**attempt) + random.random() * 0.2)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 3:
                    raise AppError("chess_com_rate_limited", "Chess.com 暂时限制访问，稍后会自动重试", status_code=503)
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.5 * (2**attempt)
                time.sleep(delay + random.random() * 0.2)
                continue
            if response.status_code == 404:
                raise AppError("chess_com_user_not_found", "未找到该公开账号，请检查用户名", status_code=404)
            if response.status_code in {410}:
                raise AppError("chess_com_archive_unavailable", "该归档已不可用", status_code=410)
            # A conditional archive request uses 304 as its successful cache-hit
            # signal. httpx.raise_for_status() treats all 3xx responses as
            # redirects, so let the caller translate this response first.
            if response.status_code == 304:
                return response
            response.raise_for_status()
            return response
        raise AssertionError("unreachable")

    def list_archives(self, username: str) -> list[ArchiveRef]:
        response = self._request(f"{self.base_url}/player/{username.lower()}/games/archives")
        archives: list[ArchiveRef] = []
        for url in response.json().get("archives", []):
            parsed = urlparse(url)
            parts = parsed.path.rstrip("/").split("/")
            month = f"{parts[-2]}-{parts[-1]}" if len(parts) >= 2 else "unknown"
            archives.append(ArchiveRef(url=url, month=month))
        return archives

    def fetch_archive(self, archive: ArchiveRef, *, etag: str | None, last_modified: str | None) -> ArchiveFetchResult:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = self._request(archive.url, headers=headers)
        if response.status_code == 304:
            return ArchiveFetchResult("not_modified", [], etag, last_modified)
        return ArchiveFetchResult(
            "ok",
            response.json().get("games", []),
            response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
        )
