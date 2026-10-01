from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class FetchResult:
    ok: bool
    status_code: int
    body: str = ""
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    not_modified: bool = False
    error: Optional[str] = None


class Fetcher:
    def __init__(self, user_agent: str, timeout: float) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )

    def fetch(
        self,
        url: str,
        *,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> FetchResult:
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        try:
            resp = self.client.get(url, headers=headers)
        except httpx.HTTPError as e:
            return FetchResult(ok=False, status_code=0, error=str(e))

        if resp.status_code == 304:
            return FetchResult(
                ok=True,
                status_code=304,
                not_modified=True,
                etag=etag,
                last_modified=last_modified,
            )

        if resp.status_code >= 400:
            return FetchResult(
                ok=False,
                status_code=resp.status_code,
                error=f"HTTP {resp.status_code}",
            )

        # кодировка
        try:
            body = resp.text
        except Exception:
            body = resp.content.decode("utf-8", errors="replace")

        return FetchResult(
            ok=True,
            status_code=resp.status_code,
            body=body,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
        )

    def close(self) -> None:
        self.client.close()
