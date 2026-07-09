from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from .storage import ExtractionStore


class Store(Protocol):
    def close(self) -> None: ...


def create_store(
    db_path: str | Path | None = None,
    *,
    database_url: str | None = None,
):
    url = database_url if database_url is not None else os.getenv("DATABASE_URL")
    if url:
        if _is_postgres_url(url):
            from .postgres import PostgresExtractionStore

            return PostgresExtractionStore(url)
        if _is_sqlite_url(url):
            return ExtractionStore(_sqlite_path_from_url(url))
        raise ValueError(f"unsupported DATABASE_URL scheme: {urlparse(url).scheme or '(none)'}")

    return ExtractionStore(db_path or os.getenv("RFQ_DB_PATH", "outputs/rfq_extractions.db"))


def storage_label(db_path: str | Path | None = None, database_url: str | None = None) -> str:
    url = database_url if database_url is not None else os.getenv("DATABASE_URL")
    if url:
        if _is_postgres_url(url):
            parsed = urlparse(url)
            return f"postgresql://{parsed.hostname or 'localhost'}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"
        if _is_sqlite_url(url):
            return str(_sqlite_path_from_url(url))
        return url
    return str(db_path or os.getenv("RFQ_DB_PATH", "outputs/rfq_extractions.db"))


def _is_postgres_url(value: str) -> bool:
    return value.startswith(("postgresql://", "postgres://"))


def _is_sqlite_url(value: str) -> bool:
    return value.startswith("sqlite:///")


def _sqlite_path_from_url(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.netloc:
        return Path(f"/{parsed.netloc}{parsed.path}")
    return Path(parsed.path)
