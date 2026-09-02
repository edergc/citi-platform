"""In-memory rate limiter for auth endpoints (brute-force protection).

Single-process, in-memory by design: CITI's backend runs as a single uvicorn
worker (see NSSM CitiBackend), so a dict guarded by a lock is sufficient and
avoids adding a Redis dependency just for this. If the backend is ever scaled
to multiple worker processes, this needs to move to a shared store (Redis).
"""

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
    return request.client.host if request.client else "unknown"


def enforce_not_blocked(key: str, max_attempts: int, window_seconds: int, detail: str) -> None:
    retry_after = rate_limiter.retry_after_if_blocked(key, max_attempts, window_seconds)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )
