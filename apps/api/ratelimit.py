"""Rate limiting for authentication, uploads, and semantic search."""

import os

import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from limits.errors import StorageError
from redis.exceptions import RedisError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from apps.api.auth import JWT_ALGORITHM, get_signing_secret


def _env_limit(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def limit_login() -> str:
    return _env_limit("RATE_LIMIT_LOGIN", "10/minute")


def limit_register() -> str:
    return _env_limit("RATE_LIMIT_REGISTER", "5/hour")


def limit_upload() -> str:
    return _env_limit("RATE_LIMIT_UPLOAD", "10/minute")


def limit_search() -> str:
    return _env_limit("RATE_LIMIT_SEARCH", "30/minute")


def limit_ask() -> str:
    return _env_limit("RATE_LIMIT_ASK", "20/minute")


def rate_limit_key(request: Request) -> str:
    """Use the authenticated user ID when possible, otherwise the client IP."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = jwt.decode(token, get_signing_secret(), algorithms=[JWT_ALGORITHM])
            subject = payload.get("sub")
            if isinstance(subject, str) and subject:
                return f"user:{subject}"
        except (jwt.InvalidTokenError, HTTPException):
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_limit_key,
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "").strip() or "memory://",
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() != "false",
    swallow_errors=False,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = 60
    try:
        retry_after = int(exc.limit.limit.get_expiry())
    except (AttributeError, TypeError, ValueError):
        pass
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again shortly."},
        headers={"Retry-After": str(retry_after)},
    )


def rate_limit_storage_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Rate-limit storage is unavailable."},
    )
