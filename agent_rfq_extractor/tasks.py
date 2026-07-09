from __future__ import annotations

import os
from collections import Counter
from typing import Any

from dotenv import load_dotenv

from .celery_app import celery_app
from .models import EmailRecord
from .pipeline import RFQPipeline


@celery_app.task(name="rfq.extract_fixture")
def extract_fixture_task(
    fixture_path: str = "Emails.txt",
    limit: int | None = None,
    replace_existing: bool = False,
    model: str | None = None,
) -> dict[str, Any]:
    def run(pipeline: RFQPipeline) -> list[EmailRecord]:
        return pipeline.run_fixture(fixture_path, limit=limit)

    return _run_pipeline(run, model=model, replace_existing=replace_existing)


@celery_app.task(name="rfq.extract_gmail")
def extract_gmail_task(
    query: str,
    limit: int = 30,
    email_ids: list[str] | None = None,
    replace_existing: bool = False,
    credentials_path: str | None = None,
    token_path: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    def run(pipeline: RFQPipeline) -> list[EmailRecord]:
        if email_ids:
            return pipeline.run_gmail_ids(
                message_ids=email_ids,
                credentials_path=credentials_path,
                token_path=token_path,
            )
        return pipeline.run_gmail(
            query=query,
            limit=limit,
            credentials_path=credentials_path,
            token_path=token_path,
        )

    return _run_pipeline(run, model=model, replace_existing=replace_existing)


def _run_pipeline(runner, *, model: str | None, replace_existing: bool) -> dict[str, Any]:
    load_dotenv(override=True)
    pipeline = RFQPipeline(
        db_path=os.getenv("RFQ_DB_PATH", "outputs/rfq_extractions.db"),
        json_path=os.getenv("RFQ_JSON_PATH", "outputs/rfq_extractions.json"),
        model=model,
        replace_existing=replace_existing,
        database_url=os.getenv("DATABASE_URL"),
    )
    try:
        pipeline.validate_llm()
        records = runner(pipeline)
    finally:
        pipeline.close()
    return extraction_summary(records, pipeline.database_label, str(pipeline.json_path))


def extraction_summary(records: list[EmailRecord], database: str, json_output: str) -> dict[str, Any]:
    counts = Counter(record.status for record in records)
    return {
        "records": len(records),
        "statuses": dict(sorted(counts.items())),
        "emails": [record.email_id for record in records],
        "database": database,
        "json_output": json_output,
    }
