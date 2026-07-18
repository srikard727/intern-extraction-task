from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from html import escape
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
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

    @app.get("/view", response_class=HTMLResponse)
    def view_emails(store=Depends(_store)) -> HTMLResponse:
        emails = store.list_emails(limit=500, offset=0)
        return HTMLResponse(_render_email_index(emails))

    @app.get("/view/emails/{email_id}", response_class=HTMLResponse)
    def view_email(email_id: str, store=Depends(_store)) -> HTMLResponse:
        record = store.get_email(email_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"email not found: {email_id}")
        return HTMLResponse(_render_email_detail(record))

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


def _render_email_index(emails: list[dict[str, Any]]) -> str:
    rows = "\n".join(_email_row(email) for email in emails)
    if not rows:
        rows = '<tr><td colspan="6" class="empty">No extracted emails found.</td></tr>'
    return _html_page(
        "RFQ Extraction Results",
        f"""
        <header>
          <h1>RFQ Extraction Results</h1>
          <p>{len(emails)} stored email records</p>
        </header>
        <main>
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Status</th>
                <th>Items</th>
                <th>Subject</th>
                <th>Received</th>
                <th>Model</th>
              </tr>
            </thead>
            <tbody>
              {rows}
            </tbody>
          </table>
        </main>
        """,
    )


def _email_row(email: dict[str, Any]) -> str:
    email_id = str(email.get("email_id") or "")
    status = str(email.get("status") or "unknown")
    return f"""
    <tr>
      <td><a href="/view/emails/{escape(email_id)}">{escape(email_id)}</a></td>
      <td>{_status_badge(status)}</td>
      <td>{escape(str(email.get("item_count") or 0))}</td>
      <td>{escape(str(email.get("subject") or ""))}</td>
      <td>{escape(str(email.get("received_at") or ""))}</td>
      <td>{escape(str(email.get("llm_model") or ""))}</td>
    </tr>
    """


def _render_email_detail(record: dict[str, Any]) -> str:
    email_id = str(record.get("email_id") or "")
    status = str(record.get("status") or "unknown")
    extraction = record.get("extraction") if isinstance(record.get("extraction"), dict) else {}
    review = record.get("review") if isinstance(record.get("review"), dict) else None
    groups = extraction.get("glass_type_groups") if isinstance(extraction.get("glass_type_groups"), list) else []
    group_sections = "\n".join(_group_section(group) for group in groups if isinstance(group, dict))
    review_panel = _review_panel(review)
    return _html_page(
        f"RFQ {email_id}",
        f"""
        <header>
          <a class="back" href="/view">Back to results</a>
          <h1>{escape(email_id)}</h1>
          <p>{_status_badge(status)} <span>{escape(str(record.get("subject") or ""))}</span></p>
        </header>
        <main class="detail">
          <section>
            <h2>Summary</h2>
            <dl class="summary">
              <div><dt>Glass Type</dt><dd>{escape(str(extraction.get("glass_type") or "unknown"))}</dd></div>
              <div><dt>Types</dt><dd>{escape(", ".join(extraction.get("glass_types") or []))}</dd></div>
              <div><dt>Missing</dt><dd>{escape(", ".join(extraction.get("missing_fields") or []) or "None")}</dd></div>
              <div><dt>Model</dt><dd>{escape(str(record.get("llm_model") or ""))}</dd></div>
            </dl>
          </section>
          {review_panel}
          {group_sections or '<section><h2>Glass Units</h2><p class="empty">No glass units extracted.</p></section>'}
        </main>
        """,
    )


def _review_panel(review: dict[str, Any] | None) -> str:
    if not review:
        return '<section><h2>Human Review</h2><p class="ok">Not required.</p></section>'
    conflicts = review.get("conflicts") if isinstance(review.get("conflicts"), list) else []
    conflict_rows = "\n".join(
        f"""
        <tr>
          <td>{escape(str(conflict.get("field") or ""))}</td>
          <td>{escape(str(conflict.get("body") or ""))}</td>
          <td>{escape(str(conflict.get("attachment") or ""))}</td>
        </tr>
        """
        for conflict in conflicts
        if isinstance(conflict, dict)
    )
    conflict_table = ""
    if conflict_rows:
        conflict_table = f"""
        <table>
          <thead><tr><th>Field</th><th>Body</th><th>Attachment</th></tr></thead>
          <tbody>{conflict_rows}</tbody>
        </table>
        """
    return f"""
    <section>
      <h2>Human Review</h2>
      <p>{escape(str(review.get("reason") or "Review required."))}</p>
      {conflict_table}
    </section>
    """


def _group_section(group: dict[str, Any]) -> str:
    glass_type = str(group.get("glass_type") or "unknown")
    units = group.get("glass_units") if isinstance(group.get("glass_units"), list) else []
    unit_rows = "\n".join(_unit_row(unit) for unit in units if isinstance(unit, dict))
    if not unit_rows:
        unit_rows = '<tr><td colspan="8" class="empty">No units in this group.</td></tr>'
    return f"""
    <section>
      <h2>{escape(glass_type.title())}</h2>
      <table>
        <thead>
          <tr>
            <th>Qty</th>
            <th>Size</th>
            <th>Shape</th>
            <th>Mark</th>
            <th>Specs</th>
            <th>Fabrication</th>
            <th>Missing</th>
            <th>Complete</th>
          </tr>
        </thead>
        <tbody>
          {unit_rows}
        </tbody>
      </table>
    </section>
    """


def _unit_row(unit: dict[str, Any]) -> str:
    size = _size_label(unit)
    return f"""
    <tr>
      <td>{escape(str(unit.get("quantity") or ""))}</td>
      <td>{escape(size)}</td>
      <td>{escape(str(unit.get("shape") or ""))}</td>
      <td>{escape(str(unit.get("mark") or ""))}</td>
      <td>{_dict_list(unit.get("glass_specs"))}</td>
      <td>{_dict_list(unit.get("fabrication"))}</td>
      <td>{escape(", ".join(unit.get("missing_fields") or []) or "None")}</td>
      <td>{escape("yes" if unit.get("is_complete") else "no")}</td>
    </tr>
    """


def _size_label(unit: dict[str, Any]) -> str:
    width = unit.get("width")
    height = unit.get("height")
    uom = unit.get("unit_of_measurement") or "inch"
    if width is None or height is None:
        return "missing"
    return f"{width} x {height} {uom}"


def _dict_list(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return '<span class="muted">None</span>'
    items = "".join(
        f"<li><strong>{escape(str(key))}</strong>: {escape(str(item))}</li>"
        for key, item in value.items()
        if item not in (None, "", [])
    )
    return f"<ul>{items}</ul>" if items else '<span class="muted">None</span>'


def _status_badge(status: str) -> str:
    class_name = "review" if status == "human_review_required" else status.replace("_", "-")
    return f'<span class="status {escape(class_name)}">{escape(status)}</span>'


def _html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #65717f;
      --line: #d8dee6;
      --ok: #146c43;
      --warn: #9a5b00;
      --fail: #b42318;
      --link: #1458a8;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header, main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }}
    header {{
      padding-bottom: 8px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      line-height: 1.2;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 18px;
    }}
    p {{
      margin: 0;
      color: var(--muted);
    }}
    a {{
      color: var(--link);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .back {{
      display: inline-block;
      margin-bottom: 12px;
    }}
    section, table {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    section {{
      margin-bottom: 18px;
      padding: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      overflow: hidden;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .status {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 12px;
      white-space: nowrap;
    }}
    .status.completed {{
      color: var(--ok);
      border-color: #a9d6bc;
      background: #edf8f1;
    }}
    .status.review {{
      color: var(--warn);
      border-color: #f0d39a;
      background: #fff8e8;
    }}
    .status.extraction-failed {{
      color: var(--fail);
      border-color: #f1b8b3;
      background: #fff0ee;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin: 0;
    }}
    .summary div {{
      border-left: 3px solid var(--line);
      padding-left: 10px;
    }}
    dt {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    dd {{
      margin: 2px 0 0;
    }}
    .empty, .muted {{
      color: var(--muted);
    }}
    .ok {{
      color: var(--ok);
    }}
    @media (max-width: 780px) {{
      header, main {{
        padding: 16px;
      }}
      table {{
        display: block;
        overflow-x: auto;
      }}
      th, td {{
        white-space: nowrap;
      }}
    }}
  </style>
</head>
<body>
  {body}
</body>
</html>
"""


app = create_app()
