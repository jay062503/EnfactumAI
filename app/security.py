import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            raise HTTPException(429, "Too many requests. Please wait a moment.")
        q.append(now)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    CSP = ("default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; "
           "script-src 'self'; connect-src 'self'; frame-src 'self' blob:; media-src 'self' blob:; "
           "object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
    # Served user files (uploads / generated) can never run script in the app's origin.
    FILE_CSP = "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"

    def __init__(self, app, frame_ancestors: str = ""):
        super().__init__(app)
        self.csp = self.CSP.replace("frame-ancestors 'self'", f"frame-ancestors 'self' {frame_ancestors}".strip())

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        path = request.url.path
        if not path.startswith("/api/"):
            response.headers.setdefault("Content-Security-Policy", self.csp)
        elif path.endswith("/file") or path.startswith("/api/files/"):
            response.headers.setdefault("Content-Security-Policy", self.FILE_CSP)
        return response
