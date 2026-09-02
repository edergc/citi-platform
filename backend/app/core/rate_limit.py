"""In-memory rate limiter for auth endpoints (brute-force protection).

Single-process, in-memory by design: CITI's backend runs as a single uvicorn
worker (see NSSM CitiBackend), so a dict guarded by a lock is sufficient and
avoids adding a Redis dependency just for this. If the backend is ever scaled
to multiple worker processes, this needs to move to a shared store (Redis).
"""

import ipaddress
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _prune(self, key: str, window_seconds: int, now: float) -> list[float]:
        cutoff = now - window_seconds
        fresh = [t for t in self._attempts.get(key, []) if t > cutoff]
        self._attempts[key] = fresh
        return fresh

    def retry_after_if_blocked(self, key: str, max_attempts: int, window_seconds: int) -> int | None:
        """Returns seconds to wait if `key` is currently blocked, else None. Does not record anything."""
        now = time.monotonic()
        with self._lock:
            fresh = self._prune(key, window_seconds, now)
            if len(fresh) >= max_attempts:
                return max(int(window_seconds - (now - fresh[0])) + 1, 1)
            return None

    def record_attempt(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


rate_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """Real client IP, not Caddy's (CitiProxy sits in front of every request in
    production — see Caddyfile — and its reverse_proxy directive adds X-Forwarded-For by
    default, so request.client.host alone would just be 127.0.0.1 for every técnico).
    Falls back to request.client.host (direct connections, e.g. local dev on :5190) when
    there's no forwarded header. Always returns something INET-safe to store/rate-limit
    on — "unknown" for anything that doesn't parse as an IP, never a raw unvalidated
    string (see resolve_ip_for_storage for why that matters)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if _is_valid_ip(candidate):
            return candidate
    if request.client and _is_valid_ip(request.client.host):
        return request.client.host
    return "unknown"


def _is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def resolve_ip_for_storage(request: Request) -> str | None:
    """Like client_ip, but returns None instead of "unknown" — for columns typed INET
    (AuditLog.ip_address), which reject non-IP strings outright rather than just losing
    rate-limiting precision."""
    ip = client_ip(request)
    return ip if ip != "unknown" else None


def enforce_not_blocked(key: str, max_attempts: int, window_seconds: int, detail: str) -> None:
    retry_after = rate_limiter.retry_after_if_blocked(key, max_attempts, window_seconds)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )
