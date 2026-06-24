"""Server-side client for Moose metadata endpoints."""

from __future__ import annotations

import copy
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _CacheEntry:
    value: Any
    expires_at: float


class MooseClientError(RuntimeError):
    """Raised when Moose metadata cannot be fetched."""

    def __init__(self, message: str, *, stale_value: Any = None):
        super().__init__(message)
        self.stale_value = stale_value


class MooseMetadataClient:
    """Fetch non-secret Moose catalog metadata with a short-lived cache."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
    ):
        self.base_url = (
            base_url if base_url is not None else os.getenv("MOOSE_API_BASE_URL", "")
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("MOOSE_API_KEY", "")
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("MOOSE_API_TIMEOUT_SECONDS", "5")
        )
        self.cache_ttl_seconds = cache_ttl_seconds or float(
            os.getenv("MOOSE_CATALOG_CACHE_TTL_SECONDS", "300")
        )
        self._cache: dict[str, _CacheEntry] = {}

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def get_json(self, path: str, *, force: bool = False) -> Any:
        if not self.configured:
            raise MooseClientError("Moose metadata service is not configured")

        now = time.monotonic()
        cached = self._cache.get(path)
        if cached and cached.expires_at > now and not force:
            return copy.deepcopy(cached.value)

        metadata_request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Accept": "application/json", "X-API-Key": self.api_key},
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                metadata_request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            stale_value = copy.deepcopy(cached.value) if cached else None
            raise MooseClientError(
                f"Moose metadata request failed for {path}: {exc}",
                stale_value=stale_value,
            ) from exc

        self._cache[path] = _CacheEntry(
            value=copy.deepcopy(payload),
            expires_at=now + self.cache_ttl_seconds,
        )
        return payload
