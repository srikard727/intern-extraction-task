from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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
    load_dotenv(override=False)
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
            "view": "/view",
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
    def view_emails(
        status: str = "",
        glass_type: str = "",
        q: str = "",
        store=Depends(_store),
    ) -> HTMLResponse:
        summaries = store.list_emails(limit=500, offset=0)
        records = [_view_record(summary, store.get_email(summary["email_id"])) for summary in summaries]
        filters = {"status": status.strip(), "glass_type": glass_type.strip(), "q": q.strip()}
        visible_records = _filter_view_records(records, filters)
        return HTMLResponse(_render_email_index(records, visible_records, filters))

    @app.get("/view/emails/{email_id}", response_class=HTMLResponse)
    def view_email(email_id: str, request: Request, store=Depends(_store)) -> HTMLResponse:
        record = store.get_email(email_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"email not found: {email_id}")
        runs = store.list_agent_runs(limit=20, offset=0, email_id=email_id)
        return HTMLResponse(_render_email_detail(record, runs, str(request.url.query)))

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


def _render_email_index(
    records: list[dict[str, Any]],
    visible_records: list[dict[str, Any]],
    filters: dict[str, str],
) -> str:
    rows = "\n".join(_email_row(record, filters) for record in visible_records)
    if not rows:
        rows = '<tr><td colspan="8" class="empty">No extracted emails match the current filters.</td></tr>'
    metrics = _index_metrics(records)
    filter_bar = _filter_bar(records, filters)
    return _html_page(
        "RFQ Review Dashboard",
        f"""
        <header class="app-header">
          <div>
            <p class="eyebrow">Glass RFQ Extraction</p>
            <h1>Review Dashboard</h1>
            <p>{len(visible_records)} of {len(records)} stored email records shown</p>
          </div>
          <nav aria-label="Primary">
            <a href="/health">Health</a>
            <a href="/docs">API Docs</a>
          </nav>
        </header>
        <main>
          {metrics}
          {filter_bar}
          <section class="surface">
            <div class="section-title">
              <div>
                <h2>Email Queue</h2>
                <p>Sorted by extraction time and email id</p>
              </div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Glass</th>
                  <th>Items</th>
                  <th>Missing</th>
                  <th>Attach</th>
                  <th>Subject</th>
                  <th>Extracted</th>
                </tr>
              </thead>
              <tbody>
                {rows}
              </tbody>
            </table>
          </section>
        </main>
        """,
    )


def _view_record(summary: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    extraction = record.get("extraction") if isinstance(record, dict) else {}
    if not isinstance(extraction, dict):
        extraction = {}
    review = record.get("review") if isinstance(record, dict) else None
    if not isinstance(review, dict):
        review = {}
    attachments = record.get("attachments") if isinstance(record, dict) else []
    if not isinstance(attachments, list):
        attachments = []
    glass_types = extraction.get("glass_types") if isinstance(extraction.get("glass_types"), list) else []
    missing = extraction.get("missing_fields") if isinstance(extraction.get("missing_fields"), list) else []
    return {
        **summary,
        "glass_type": extraction.get("glass_type") or "unknown",
        "glass_types": [str(item) for item in glass_types],
        "missing_fields": [str(item) for item in missing],
        "review_reason": str(review.get("reason") or ""),
        "attachment_count": len(attachments),
        "body_text": str(record.get("body_text") or "") if isinstance(record, dict) else "",
    }


def _filter_view_records(records: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    status_filter = filters.get("status", "")
    type_filter = filters.get("glass_type", "")
    query = filters.get("q", "").lower()
    visible = []
    for record in records:
        if status_filter and record.get("status") != status_filter:
            continue
        if type_filter and type_filter not in record.get("glass_types", []):
            continue
        if query and query not in _search_blob(record):
            continue
        visible.append(record)
    return visible


def _search_blob(record: dict[str, Any]) -> str:
    parts = [
        record.get("email_id"),
        record.get("conv_id"),
        record.get("from_email"),
        record.get("to_email"),
        record.get("subject"),
        record.get("status"),
        record.get("glass_type"),
        record.get("review_reason"),
        record.get("body_text"),
        " ".join(record.get("glass_types") or []),
        " ".join(record.get("missing_fields") or []),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _index_metrics(records: list[dict[str, Any]]) -> str:
    statuses = Counter(str(record.get("status") or "unknown") for record in records)
    item_count = sum(int(record.get("item_count") or 0) for record in records)
    attachment_count = sum(int(record.get("attachment_count") or 0) for record in records)
    missing_count = sum(1 for record in records if record.get("missing_fields"))
    return f"""
    <section class="metrics" aria-label="Extraction summary">
      {_metric("Emails", len(records))}
      {_metric("Items", item_count)}
      {_metric("Completed", statuses.get("completed", 0), "ok")}
      {_metric("Human Review", statuses.get("human_review_required", 0), "warn")}
      {_metric("Failed", statuses.get("extraction_failed", 0), "fail")}
      {_metric("With Missing Fields", missing_count)}
      {_metric("Attachments", attachment_count)}
    </section>
    """


def _metric(label: str, value: int, tone: str = "") -> str:
    tone_class = f" {tone}" if tone else ""
    return f"""
    <div class="metric{tone_class}">
      <dt>{escape(label)}</dt>
      <dd>{escape(str(value))}</dd>
    </div>
    """


def _filter_bar(records: list[dict[str, Any]], filters: dict[str, str]) -> str:
    statuses = sorted({str(record.get("status") or "unknown") for record in records})
    glass_types = sorted({glass_type for record in records for glass_type in record.get("glass_types", [])})
    return f"""
    <section class="surface filters">
      <form method="get" action="/view">
        <label>
          <span>Search</span>
          <input name="q" value="{escape(filters.get("q", ""))}" placeholder="email, subject, sender, missing field">
        </label>
        <label>
          <span>Status</span>
          <select name="status">
            <option value="">All statuses</option>
            {_options(statuses, filters.get("status", ""))}
          </select>
        </label>
        <label>
          <span>Glass Type</span>
          <select name="glass_type">
            <option value="">All glass types</option>
            {_options(glass_types, filters.get("glass_type", ""))}
          </select>
        </label>
        <div class="filter-actions">
          <button type="submit">Apply</button>
          <a href="/view">Reset</a>
        </div>
      </form>
    </section>
    """


def _options(values: list[str], selected: str) -> str:
    return "\n".join(
        f'<option value="{escape(value)}"{" selected" if value == selected else ""}>{escape(value)}</option>'
        for value in values
    )


def _email_row(record: dict[str, Any], filters: dict[str, str]) -> str:
    email_id = str(record.get("email_id") or "")
    status = str(record.get("status") or "unknown")
    detail_href = f"/view/emails/{escape(email_id)}"
    back_query = urlencode({key: value for key, value in filters.items() if value})
    if back_query:
        detail_href += f"?{escape(back_query)}"
    missing = record.get("missing_fields") or []
    return f"""
    <tr>
      <td><a href="{detail_href}">{escape(email_id)}</a></td>
      <td>{_status_badge(status)}</td>
      <td>{escape(", ".join(record.get("glass_types") or []) or "unknown")}</td>
      <td>{escape(str(record.get("item_count") or 0))}</td>
      <td>{_missing_label(missing)}</td>
      <td>{escape(str(record.get("attachment_count") or 0))}</td>
      <td>{escape(str(record.get("subject") or ""))}</td>
      <td>{escape(str(record.get("extracted_at") or record.get("received_at") or ""))}</td>
    </tr>
    """


def _missing_label(missing: list[str]) -> str:
    if not missing:
        return '<span class="ok">None</span>'
    return escape(", ".join(missing))


def _render_email_detail(record: dict[str, Any], runs: list[dict[str, Any]], back_query: str = "") -> str:
    email_id = str(record.get("email_id") or "")
    status = str(record.get("status") or "unknown")
    extraction = record.get("extraction") if isinstance(record.get("extraction"), dict) else {}
    review = record.get("review") if isinstance(record.get("review"), dict) else None
    groups = extraction.get("glass_type_groups") if isinstance(extraction.get("glass_type_groups"), list) else []
    group_sections = "\n".join(_group_section(group) for group in groups if isinstance(group, dict))
    review_panel = _review_panel(review)
    back_href = "/view" + (f"?{escape(back_query)}" if back_query else "")
    attachments = record.get("attachments") if isinstance(record.get("attachments"), list) else []
    item_count = _record_item_count(record)
    return _html_page(
        f"RFQ {email_id}",
        f"""
        <header class="app-header">
          <div>
            <a class="back" href="{back_href}">Back to queue</a>
            <p class="eyebrow">Email Detail</p>
            <h1>{escape(email_id)}</h1>
            <p>{_status_badge(status)} <span>{escape(str(record.get("subject") or ""))}</span></p>
          </div>
          <nav aria-label="Primary">
            <a href="/view">Dashboard</a>
            <a href="/emails/{escape(email_id)}">JSON</a>
          </nav>
        </header>
        <main class="detail">
          <section class="metrics" aria-label="Email summary">
            {_metric("Items", item_count)}
            {_metric("Attachments", len(attachments))}
            {_metric("Groups", len(groups))}
            {_metric("Missing Fields", len(extraction.get("missing_fields") or []), "warn" if extraction.get("missing_fields") else "")}
            {_metric("Agent Runs", len(runs))}
          </section>
          <section class="surface">
            <h2>Summary</h2>
            <dl class="summary">
              <div><dt>Glass Type</dt><dd>{escape(str(extraction.get("glass_type") or "unknown"))}</dd></div>
              <div><dt>Types</dt><dd>{escape(", ".join(extraction.get("glass_types") or []))}</dd></div>
              <div><dt>Missing</dt><dd>{escape(", ".join(extraction.get("missing_fields") or []) or "None")}</dd></div>
              <div><dt>Model</dt><dd>{escape(str(record.get("llm_model") or ""))}</dd></div>
              <div><dt>Conversation</dt><dd>{escape(str(record.get("conv_id") or ""))}</dd></div>
              <div><dt>Extracted</dt><dd>{escape(str(record.get("extracted_at") or ""))}</dd></div>
            </dl>
          </section>
          {_email_panel(record)}
          {_attachments_panel(attachments)}
          {review_panel}
          {group_sections or '<section class="surface"><h2>Glass Units</h2><p class="empty">No glass units extracted.</p></section>'}
          {_agent_runs_panel(runs)}
        </main>
        """,
    )


def _record_item_count(record: dict[str, Any]) -> int:
    groups = record.get("extraction", {}).get("glass_type_groups", [])
    if not isinstance(groups, list):
        return 0
    count = 0
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("glass_units"), list):
            count += len(group["glass_units"])
    return count


def _email_panel(record: dict[str, Any]) -> str:
    body_text = str(record.get("body_text") or "")
    return f"""
    <section class="surface">
      <div class="section-title">
        <div>
          <h2>Email</h2>
          <p>{escape(str(record.get("emailbody_variant") or "plain"))} body</p>
        </div>
      </div>
      <dl class="summary">
        <div><dt>From</dt><dd>{escape(str(record.get("from_email") or ""))}</dd></div>
        <div><dt>To</dt><dd>{escape(str(record.get("to_email") or ""))}</dd></div>
        <div><dt>Received</dt><dd>{escape(str(record.get("received_at") or ""))}</dd></div>
        <div><dt>Subject</dt><dd>{escape(str(record.get("subject") or ""))}</dd></div>
      </dl>
      <pre class="email-body">{escape(body_text)}</pre>
    </section>
    """


def _attachments_panel(attachments: list[Any]) -> str:
    rows = "\n".join(_attachment_row(item) for item in attachments if isinstance(item, dict))
    if not rows:
        rows = '<tr><td colspan="5" class="empty">No attachments stored for this email.</td></tr>'
    return f"""
    <section class="surface">
      <div class="section-title">
        <div>
          <h2>Attachments</h2>
          <p>{len(attachments)} stored attachment record(s)</p>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>File</th>
            <th>Type</th>
            <th>Source</th>
            <th>Text</th>
            <th>Preview / Error</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _attachment_row(attachment: dict[str, Any]) -> str:
    preview = attachment.get("text_preview") or attachment.get("error") or ""
    text_state = "yes" if attachment.get("text_extracted") else "no"
    return f"""
    <tr>
      <td>{escape(str(attachment.get("filename") or ""))}</td>
      <td>{escape(str(attachment.get("mime_type") or ""))}</td>
      <td>{escape(str(attachment.get("source") or ""))}</td>
      <td>{escape(text_state)}</td>
      <td>{escape(str(preview))}</td>
    </tr>
    """


def _review_panel(review: dict[str, Any] | None) -> str:
    if not review:
        return '<section class="surface"><h2>Human Review</h2><p class="ok">Not required.</p></section>'
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
    <section class="surface review-panel">
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
        unit_rows = '<tr><td colspan="9" class="empty">No units in this group.</td></tr>'
    return f"""
    <section class="surface">
      <div class="section-title">
        <div>
          <h2>{escape(glass_type.title())}</h2>
          <p>{len(units)} extracted unit(s)</p>
        </div>
      </div>
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
            <th>Notes</th>
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
      <td>{escape(str(unit.get("notes") or ""))}</td>
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


def _agent_runs_panel(runs: list[dict[str, Any]]) -> str:
    rows = "\n".join(_agent_run_row(run) for run in runs)
    if not rows:
        rows = '<tr><td colspan="8" class="empty">No agent runs found for this email.</td></tr>'
    return f"""
    <section class="surface">
      <div class="section-title">
        <div>
          <h2>Agent Runs</h2>
          <p>{len(runs)} execution log record(s)</p>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Started</th>
            <th>Agent</th>
            <th>Status</th>
            <th>Review</th>
            <th>Items</th>
            <th>Duration</th>
            <th>Model</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _agent_run_row(run_data: dict[str, Any]) -> str:
    return f"""
    <tr>
      <td>{escape(str(run_data.get("started_at") or ""))}</td>
      <td>{escape(str(run_data.get("agent_name") or ""))}</td>
      <td>{_status_badge(str(run_data.get("status") or "unknown"))}</td>
      <td>{escape(str(run_data.get("review_status") or ""))}</td>
      <td>{escape(str(run_data.get("item_count") or 0))}</td>
      <td>{escape(str(run_data.get("duration_ms") or 0))} ms</td>
      <td>{escape(str(run_data.get("model") or ""))}</td>
      <td>{escape(str(run_data.get("error") or ""))}</td>
    </tr>
    """


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
      --bg: #f5f7fa;
      --panel: #ffffff;
      --panel-soft: #f9fafb;
      --text: #17202a;
      --muted: #65717f;
      --line: #d8dee6;
      --line-strong: #b9c3d0;
      --ok: #146c43;
      --warn: #9a5b00;
      --fail: #b42318;
      --link: #1458a8;
      --focus: #2f6fed;
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
    .app-header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 24px;
      padding-bottom: 8px;
    }}
    .app-header nav {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .app-header nav a {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--text);
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
    .eyebrow {{
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
      text-transform: uppercase;
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
    table {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .surface {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 18px;
      padding: 18px;
    }}
    .section-title {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 14px;
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
    tbody tr:hover {{
      background: #fbfcfe;
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
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric {{
      min-height: 72px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .metric dt {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .metric dd {{
      margin: 4px 0 0;
      font-size: 24px;
      font-weight: 700;
    }}
    .metric.ok {{
      border-color: #a9d6bc;
    }}
    .metric.warn {{
      border-color: #f0d39a;
    }}
    .metric.fail {{
      border-color: #f1b8b3;
    }}
    .filters form {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(160px, 220px) minmax(160px, 220px) auto;
      gap: 14px;
      align-items: end;
    }}
    label span {{
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    input, select, button {{
      width: 100%;
      min-height: 38px;
      box-sizing: border-box;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
    }}
    input, select {{
      padding: 0 10px;
    }}
    input:focus, select:focus, button:focus {{
      outline: 2px solid var(--focus);
      outline-offset: 1px;
    }}
    button {{
      padding: 0 14px;
      border-color: #1458a8;
      background: #1458a8;
      color: #ffffff;
      cursor: pointer;
    }}
    .filter-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
    }}
    .filter-actions a {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 10px;
      color: var(--muted);
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
    .review-panel {{
      border-color: #f0d39a;
      background: #fffdf7;
    }}
    .email-body {{
      max-height: 420px;
      overflow: auto;
      margin: 16px 0 0;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-soft);
      color: var(--text);
      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
    }}
    @media (max-width: 780px) {{
      header, main {{
        padding: 16px;
      }}
      .app-header {{
        display: block;
      }}
      .app-header nav {{
        justify-content: flex-start;
        margin-top: 14px;
      }}
      .filters form {{
        grid-template-columns: 1fr;
      }}
      .filter-actions {{
        justify-content: flex-start;
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
