"""In-memory high-throughput TTL cache for serverless & production deployments.

Ensures hot endpoints (editions, categories, public events, admin rollups)
respond in <1ms without hitting Supabase PostgreSQL repeatedly.
"""

from __future__ import annotations

import asyncio
import fnmatch
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_LOCK = asyncio.Lock()


def cache_get(key: str) -> Any | None:
    """Get value from memory cache if not expired."""
    item = _CACHE.get(key)
    if not item:
        return None
    expires_at, value = item
    if time.monotonic() > expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl_seconds: float = 60.0) -> None:
    """Store value in memory cache with TTL."""
    # Prevent memory bloat by evicting expired items if cache grows large
    if len(_CACHE) > 500:
        now = time.monotonic()
        expired = [k for k, (exp, _) in _CACHE.items() if now > exp]
        for k in expired:
            _CACHE.pop(k, None)

    _CACHE[key] = (time.monotonic() + ttl_seconds, value)


def cache_delete(key: str) -> None:
    """Explicitly delete a cached key."""
    _CACHE.pop(key, None)


def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a wildcard pattern (e.g. 'events:*')."""
    matching = [k for k in _CACHE if fnmatch.fnmatch(k, pattern)]
    for k in matching:
        _CACHE.pop(k, None)


def cache_clear() -> None:
    """Clear entire cache."""
    _CACHE.clear()


def cached(ttl_seconds: float = 60.0, key_prefix: str = ""):
    """Decorator for caching async function results by arguments."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name + stringified args (ignoring db sessions)
            arg_parts = [
                str(arg)
                for arg in args
                if not hasattr(arg, "execute") and not hasattr(arg, "connection")
            ]
            kwarg_parts = [
                f"{k}={v}"
                for k, v in sorted(kwargs.items())
                if not hasattr(v, "execute") and not hasattr(v, "connection")
            ]
            cache_key = f"{key_prefix or func.__name__}:{':'.join(arg_parts)}:{':'.join(kwarg_parts)}"

            val = cache_get(cache_key)
            if val is not None:
                return val

            result = await func(*args, **kwargs)
            if result is not None:
                cache_set(cache_key, result, ttl_seconds)
            return result

        return wrapper

    return decorator

