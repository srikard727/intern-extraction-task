from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from database.factory import create_store, storage_label
from database.storage import StorageError

from .celery_app import celery_app
from .claude_client import DEFAULT_MODEL, LLMConfigurationError
from .models import EmailRecord
from .pipeline import RFQPipeline
from .tasks import extract_fixture_task, extract_gmail_task


class FixtureExtractionRequest(BaseModel):
    fixture_path: str = "Emails.txt"
    limit: int | None = Field(default=None, ge=1, le=500)
    replace_existing: bool = False
    model: str | None = None


class GmailExtractionRequest(BaseModel):
    query: str = 'in:inbox newer_than:30d {subject:RFQ subject:"Request for Quote"}'
    limit: int = Field(default=30, ge=1, le=500)
    email_ids: list[str] = Field(default_factory=list)
    replace_existing: bool = False
    credentials_path: str | None = None
    token_path: str | None = None
    model: str | None = None


def create_app(
    *,
    db_path: str | Path | None = None,
    database_url: str | None = None,
    json_path: str | Path | None = None,
    project_root: str | Path | None = None,
) -> FastAPI:
    load_dotenv(override=True)
    app = FastAPI(
        title="Glass RFQ Extraction API",
        version="0.1.0",
        description="API wrapper around the RFQ extraction agent workflow.",
    )
    app.state.db_path = Path(db_path or os.getenv("RFQ_DB_PATH", "outputs/rfq_extractions.db"))
    app.state.database_url = database_url if database_url is not None else os.getenv("DATABASE_URL")
    app.state.database_label = storage_label(app.state.db_path, app.state.database_url)
    app.state.json_path = Path(json_path or os.getenv("RFQ_JSON_PATH", "outputs/rfq_extractions.json"))
    app.state.project_root = Path(project_root or Path.cwd())

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "glass-rfq-extraction-api",
            "status": "ok",
            "docs": "/docs",
        }

    @app.get("/health")
    def health(store=Depends(_store)) -> dict[str, Any]:
        return {
            "status": "ok",
            "database": app.state.database_label,
            "json_output": str(app.state.json_path),
            "model": os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
            "redis": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            "celery_broker": str(celery_app.conf.broker_url),
            "counts": store.counts(),
        }

    @app.get("/emails")
    def list_emails(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        store=Depends(_store),
    ) -> dict[str, Any]:
        return {"emails": store.list_emails(limit=limit, offset=offset)}

    @app.get("/emails/{email_id}")
    def get_email(email_id: str, store=Depends(_store)) -> dict[str, Any]:
        record = store.get_email(email_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"email not found: {email_id}")
        return record

    @app.get("/agent-runs")
    def list_agent_runs(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        email_id: str | None = None,
        store=Depends(_store),
    ) -> dict[str, Any]:
        return {
            "agent_runs": store.list_agent_runs(
                limit=limit,
                offset=offset,
                email_id=email_id,
            )
        }

    @app.get("/agent-runs/{run_id}")
    def get_agent_run(run_id: str, store=Depends(_store)) -> dict[str, Any]:
        run = store.get_agent_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"agent run not found: {run_id}")
        return run

    @app.post("/extract/fixture")
    def extract_fixture(payload: FixtureExtractionRequest) -> dict[str, Any]:
        fixture_path = _resolve_path(payload.fixture_path, app.state.project_root)
        if not fixture_path.exists():
            raise HTTPException(status_code=404, detail=f"fixture not found: {payload.fixture_path}")

        def run(pipeline: RFQPipeline) -> list[EmailRecord]:
            return pipeline.run_fixture(fixture_path, limit=payload.limit)

        records = _run_pipeline(
            app,
            run,
            model=payload.model,
            replace_existing=payload.replace_existing,
        )
        return _extraction_response(records, app)

    @app.post("/extract/gmail")
    def extract_gmail(payload: GmailExtractionRequest) -> dict[str, Any]:
        def run(pipeline: RFQPipeline) -> list[EmailRecord]:
            if payload.email_ids:
                return pipeline.run_gmail_ids(
                    message_ids=payload.email_ids,
                    credentials_path=payload.credentials_path,
                    token_path=payload.token_path,
                )
            return pipeline.run_gmail(
                query=payload.query,
                limit=payload.limit,
                credentials_path=payload.credentials_path,
                token_path=payload.token_path,
            )

        records = _run_pipeline(
            app,
            run,
            model=payload.model,
            replace_existing=payload.replace_existing,
        )
        return _extraction_response(records, app)

    @app.post("/tasks/extract/fixture")
    def queue_fixture_extraction(payload: FixtureExtractionRequest) -> dict[str, Any]:
        fixture_path = _resolve_path(payload.fixture_path, app.state.project_root)
        if not fixture_path.exists():
            raise HTTPException(status_code=404, detail=f"fixture not found: {payload.fixture_path}")
        task = extract_fixture_task.delay(**payload.model_dump())
        return {"task_id": task.id, "status": "queued", "task": "rfq.extract_fixture"}

    @app.post("/tasks/extract/gmail")
    def queue_gmail_extraction(payload: GmailExtractionRequest) -> dict[str, Any]:
        task = extract_gmail_task.delay(**payload.model_dump())
        return {"task_id": task.id, "status": "queued", "task": "rfq.extract_gmail"}

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        result = celery_app.AsyncResult(task_id)
        response: dict[str, Any] = {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
        }
        if result.successful():
            response["result"] = result.result
        elif result.failed():
            response["error"] = str(result.result)
        return response

    return app


def _store(request: Request) -> Iterator[Any]:
    store = create_store(request.app.state.db_path, database_url=request.app.state.database_url)
    try:
        yield store
    finally:
        store.close()


def _run_pipeline(
    app: FastAPI,
    runner,
    *,
    model: str | None,
    replace_existing: bool,
) -> list[EmailRecord]:
    try:
        pipeline = RFQPipeline(
            db_path=app.state.db_path,
            json_path=app.state.json_path,
            model=model,
            replace_existing=replace_existing,
            database_url=app.state.database_url,
        )
    except (KeyError, StorageError) as exc:
        raise HTTPException(status_code=500, detail=f"pipeline startup failed: {exc}") from exc

    try:
        pipeline.validate_llm()
        return runner(pipeline)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        pipeline.close()


def _extraction_response(records: list[EmailRecord], app: FastAPI) -> dict[str, Any]:
    counts = Counter(record.status for record in records)
    return {
        "records": len(records),
        "statuses": dict(sorted(counts.items())),
        "emails": [record.email_id for record in records],
        "database": app.state.database_label,
        "json_output": str(app.state.json_path),
    }


def _resolve_path(path: str, project_root: Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return project_root / resolved


app = create_app()
