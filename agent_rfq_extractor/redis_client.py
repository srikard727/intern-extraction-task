from __future__ import annotations

import os

from redis import Redis


def redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


def redis_client(url: str | None = None) -> Redis:
    return Redis.from_url(url or redis_url(), decode_responses=True)
