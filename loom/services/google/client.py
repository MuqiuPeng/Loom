"""Shared base client for Google API services.

Everything a Google API call needs that is not specific to one API lives here:

  * API key resolution (GOOGLE_MAPS_API_KEY, falling back to GOOGLE_API_KEY)
  * a single pooled httpx.AsyncClient shared by every Google service
  * retry with backoff on transient HTTP failures and Google's soft errors
    (UNKNOWN_ERROR / OVER_QUERY_LIMIT)
  * a TTL cache, because most Google lookups are stable and every uncached
    call is a billable request
  * one Loom log entry per network call under service="google_maps", so
    volume, latency and failures show up in the dashboard's log stream

A concrete service subclasses GoogleService, sets `name` / `base_url`, and
calls `self.request(...)`. See geocoding.py.
"""

import asyncio
import json
import os
import time
from typing import Any

import httpx

# Log service tag — the dashboard filters log entries on this.
LOG_SERVICE = "google_maps"

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 2
RETRY_BACKOFF = 0.5  # seconds; doubled per attempt

# HTTP codes worth retrying — throttling and transient upstream failures.
RETRY_HTTP_STATUS = {429, 500, 502, 503, 504}

# Google's legacy web-service APIs answer 200 OK with a `status` string.
# ZERO_RESULTS is a valid answer ("nothing matched"), not a failure.
OK_STATUSES = {"OK", "ZERO_RESULTS"}
RETRY_STATUSES = {"UNKNOWN_ERROR", "OVER_QUERY_LIMIT"}


class GoogleAPIError(RuntimeError):
    """A Google API call failed.

    `status` carries Google's own status string (REQUEST_DENIED, ...) when the
    API returned one; `http_status` carries the HTTP code when the failure was
    at the transport level.
    """

    def __init__(
        self,
        message: str,
        *,
        status: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.http_status = http_status


class GoogleNotConfiguredError(GoogleAPIError):
    """No API key is configured — the component is effectively disabled."""


# ── Shared HTTP client ───────────────────────────────────────────────

_http_client: httpx.AsyncClient | None = None
_http_lock = asyncio.Lock()


async def _http() -> httpx.AsyncClient:
    """One pooled client for every Google service in the process."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        async with _http_lock:
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                    headers={"User-Agent": "loom/0.1 (+https://github.com/loom)"},
                )
    return _http_client


async def close_http_client() -> None:
    """Close the shared client. Call on app shutdown; safe to call twice."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


# ── TTL cache ────────────────────────────────────────────────────────


class _TTLCache:
    """Small FIFO+TTL cache. Bounded so a long-running process can't grow it."""

    def __init__(self, maxsize: int = 512, ttl: float = 86400.0) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        hit = self._data.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if time.monotonic() > expires_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        if len(self._data) >= self.maxsize:
            # Drop the oldest insertion — dicts preserve insertion order.
            self._data.pop(next(iter(self._data)), None)
        self._data[key] = (time.monotonic() + self.ttl, value)

    def clear(self) -> None:
        self._data.clear()


# ── Base service ─────────────────────────────────────────────────────


class GoogleService:
    """Base class for one Google API.

    Subclasses set `name` (used as the log action prefix) and `base_url`, then
    call `self.request(path, params=...)`.
    """

    name: str = "google"
    base_url: str = ""
    # v1 APIs (Places, Routes) authenticate with an X-Goog-Api-Key header
    # instead of a `key` query parameter.
    key_in_header: bool = False
    # 24h default. Maps Platform ToS caps caching of most Content at 30 days,
    # so never raise this past that — see the note in geocoding.py / places.py.
    cache_ttl: float = 86400.0
    cache_size: int = 512

    def __init__(self, api_key: str | None = None, cache_ttl: float | None = None) -> None:
        self._api_key = api_key
        self._cache = _TTLCache(
            maxsize=self.cache_size,
            ttl=self.cache_ttl if cache_ttl is None else cache_ttl,
        )
        self.calls = 0  # network calls (billable)
        self.cache_hits = 0
        self.errors = 0

    # ── configuration ────────────────────────────────────────────────

    @property
    def api_key(self) -> str:
        key = self._api_key or os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get(
            "GOOGLE_API_KEY"
        )
        if not key:
            raise GoogleNotConfiguredError(
                f"{self.name}: GOOGLE_MAPS_API_KEY is not set"
            )
        return key

    def enabled(self) -> bool:
        """True when a key is configured — callers can degrade gracefully."""
        try:
            return bool(self.api_key)
        except GoogleNotConfiguredError:
            return False

    def stats(self) -> dict[str, int]:
        """Per-process counters — handy for a health endpoint or a smoke test."""
        return {"calls": self.calls, "cache_hits": self.cache_hits, "errors": self.errors}

    def clear_cache(self) -> None:
        self._cache.clear()

    # ── request ──────────────────────────────────────────────────────

    async def request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        action: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Call `base_url + path` with the API key attached.

        The key rides in the query string by default; services that want it in
        a header (Places and the other v1 APIs) set `key_in_header = True`.

        Returns the decoded payload. Raises GoogleAPIError on a hard failure;
        a soft "nothing matched" answer (ZERO_RESULTS) comes back normally so
        the caller can decide what it means.
        """
        action = action or path.strip("/").split("/")[0] or self.name
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        # The field mask changes the response, so it belongs in the cache key —
        # but the key header never does.
        mask = (headers or {}).get("X-Goog-FieldMask", "")
        cache_key = (
            method,
            self.base_url,
            path,
            tuple(sorted(clean.items())),
            json.dumps(body, sort_keys=True) if body else "",
            mask,
        )

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self.cache_hits += 1
                return cached

        key = self.api_key  # raises when unconfigured, before any network work
        url = f"{self.base_url}{path}"
        sent_headers = dict(headers or {})
        if self.key_in_header:
            sent_headers["X-Goog-Api-Key"] = key
        else:
            clean = {**clean, "key": key}
        started = time.perf_counter()
        last_error: GoogleAPIError | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                payload = await self._send(
                    method, url, params=clean, body=body, headers=sent_headers, action=action
                )
            except GoogleAPIError as e:
                last_error = e
                retryable = e.http_status in RETRY_HTTP_STATUS or e.status in RETRY_STATUSES
                if not retryable or attempt == MAX_RETRIES:
                    break
                await asyncio.sleep(RETRY_BACKOFF * (2**attempt))
                continue

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.calls += 1
            if use_cache:
                self._cache.set(cache_key, payload)
            await self._log(
                "info",
                action,
                f"{self.name}.{action} ok",
                status=payload.get("status", "OK"),
                latency_ms=elapsed_ms,
                attempts=attempt + 1,
                params=self._loggable(clean),
                body=body,
            )
            return payload

        # Every attempt failed.
        self.errors += 1
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        assert last_error is not None
        await self._log(
            "error",
            action,
            f"{self.name}.{action} failed: {last_error}",
            error=last_error,
            status=last_error.status,
            http_status=last_error.http_status,
            latency_ms=elapsed_ms,
            attempts=MAX_RETRIES + 1,
            params=self._loggable(clean),
        )
        raise last_error

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any],
        body: dict[str, Any] | None,
        headers: dict[str, str],
        action: str,
    ) -> dict[str, Any]:
        """One attempt: transport, HTTP status, JSON decode, Google status."""
        client = await _http()
        try:
            response = await client.request(
                method, url, params=params or None, json=body, headers=headers or None
            )
        except httpx.HTTPError as e:
            raise GoogleAPIError(f"request failed: {e}", http_status=503) from e

        if response.status_code >= 400:
            raise GoogleAPIError(
                f"HTTP {response.status_code}: {response.text[:200]}",
                http_status=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise GoogleAPIError(f"malformed JSON response: {response.text[:200]}") from e

        self._check_status(payload)
        return payload

    def _check_status(self, payload: dict[str, Any]) -> None:
        """Raise on Google's in-body error reporting.

        Legacy web services (Geocoding, Distance Matrix) return a `status`
        string; the newer APIs (Routes, Places v1) return an `error` object.
        Both are handled so subclasses rarely need to override this.
        """
        status = payload.get("status")
        if status is not None and status not in OK_STATUSES:
            message = payload.get("error_message") or status
            raise GoogleAPIError(f"{status}: {message}", status=status)

        error = payload.get("error")
        if isinstance(error, dict):
            raise GoogleAPIError(
                f"{error.get('status', 'ERROR')}: {error.get('message', '')}",
                status=error.get("status"),
                http_status=error.get("code"),
            )

    # ── logging ──────────────────────────────────────────────────────

    @staticmethod
    def _loggable(params: dict[str, Any]) -> dict[str, Any]:
        """Never let the API key reach the log stream."""
        return {k: v for k, v in params.items() if k != "key"}

    async def _log(self, level: str, action: str, message: str, **data: Any) -> None:
        """Write to Loom's log stream under service="google_maps".

        Logging must never break an API call, so failures here are swallowed.
        Cache hits are deliberately not logged — only billable network calls.
        """
        try:
            from loom.services.logger import logger as loom_logger

            await getattr(loom_logger, level)(
                "api_call", f"{self.name}.{action}", message, service=LOG_SERVICE, **data
            )
        except Exception as e:  # pragma: no cover - defensive
            print(f"[LOG_ERROR] google.{self.name}: {e}")
