from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class SemTClientError(RuntimeError):
    """Raised when the configured SemT backend cannot provide a catalog."""


@dataclass
class _CacheEntry:
    expires_at: float
    value: list[dict[str, Any]]


class SemTClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
    ):
        self.base_url = (
            base_url if base_url is not None else os.getenv("SEMT_API_BASE_URL", "")
        ).strip()
        self.token = (
            token if token is not None else os.getenv("SEMT_API_TOKEN", "")
        ).strip()
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("SEMT_CATALOG_TIMEOUT_SECONDS", "5")
        )
        self.cache_ttl_seconds = cache_ttl_seconds or float(
            os.getenv("SEMT_CATALOG_CACHE_TTL_SECONDS", "300")
        )
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = Lock()

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def list_services(
        self,
        family: str,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        if family not in {"reconciliators", "extenders"}:
            raise ValueError(f"Unsupported SemT service family: {family}")
        if not self.configured:
            raise SemTClientError("SEMT_API_BASE_URL is not configured")

        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(family)
            if cached and cached.expires_at > now and not force_refresh:
                return [dict(item) for item in cached.value]

        endpoint = urljoin(self.base_url.rstrip("/") + "/", f"api/{family}/list")
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(endpoint, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SemTClientError(f"Failed to load SemT {family}: {exc}") from exc

        if not isinstance(payload, list):
            raise SemTClientError(
                f"SemT {family} response must be a list, got {type(payload).__name__}"
            )

        services = [
            dict(item)
            for item in payload
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        with self._cache_lock:
            self._cache[family] = _CacheEntry(
                expires_at=now + max(self.cache_ttl_seconds, 0),
                value=services,
            )
        return [dict(item) for item in services]
