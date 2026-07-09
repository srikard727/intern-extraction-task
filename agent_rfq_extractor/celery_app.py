from __future__ import annotations

import os

from celery import Celery
from dotenv import load_dotenv


load_dotenv(override=True)


def redis_url(default_db: int) -> str:
    base = os.getenv("REDIS_URL")
    if base:
        return base
    return f"redis://localhost:6379/{default_db}"


celery_app = Celery(
    "rfq_extractor",
    broker=os.getenv("CELERY_BROKER_URL", redis_url(0)),
    backend=os.getenv("CELERY_RESULT_BACKEND", redis_url(1)),
    include=["agent_rfq_extractor.tasks"],
)

celery_app.conf.update(
    accept_content=["json"],
    result_serializer="json",
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
)
