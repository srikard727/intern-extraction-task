from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_rfq_extractor.agents.base import AgentContext, AgentResult  # noqa: E402
from agent_rfq_extractor.models import EmailRecord, RFQItem  # noqa: E402
from database.factory import create_store, storage_label  # noqa: E402
from database.storage import ExtractionStore  # noqa: E402


def copy_results(
    source: ExtractionStore,
    target: Any,
    json_output: str | Path,
    *,
    replace: bool = False,
) -> dict[str, int]:
    records = _load_records(source)
    runs = source.list_agent_runs(limit=500, offset=0)
    records_by_email = {record.email_id: record for record in records}

    if replace:
        target.clear()
    for record in records:
        target.upsert_record(record)
    for run in runs:
        target.record_agent_run(_agent_result(run, records_by_email))
    target.export_json(json_output)
    return target.counts()


def _load_records(source: ExtractionStore) -> list[EmailRecord]:
    items_by_email: dict[str, list[RFQItem]] = {}
    item_rows = source.conn.execute(
        "SELECT email_id, raw_json FROM items ORDER BY email_id, id"
    ).fetchall()
    for row in item_rows:
        raw_item = _load_json(row["raw_json"], {})
        items_by_email.setdefault(row["email_id"], []).append(
            RFQItem.model_validate(raw_item)
        )

    records: list[EmailRecord] = []
    email_rows = source.conn.execute(
        "SELECT raw_json FROM emails ORDER BY received_at DESC, email_id"
    ).fetchall()
    for row in email_rows:
        payload = _load_json(row["raw_json"], {})
        email_id = str(payload.get("email_id") or "")
        if not email_id:
            raise ValueError("source database contains an email without email_id")
        records.append(
            EmailRecord(
                email_id=email_id,
                conv_id=payload.get("conv_id"),
                from_email=payload.get("from_email"),
                to_email=payload.get("to_email"),
                subject=payload.get("subject"),
                body_text=str(payload.get("body_text") or ""),
                emailbody_variant=str(payload.get("emailbody_variant") or "plain"),
                received_at=payload.get("received_at"),
                has_attachments=bool(payload.get("has_attachments")),
                extracted_at=str(payload.get("extracted_at") or ""),
                status=payload.get("status") or "human_review_required",
                items=items_by_email.get(email_id, []),
                review=payload.get("review"),
                attachments=payload.get("attachments") or [],
                llm_model=payload.get("llm_model"),
            )
        )
    return records


def _agent_result(
    run: dict[str, Any],
    records_by_email: dict[str, EmailRecord],
) -> AgentResult[Any]:
    context_data = dict(run.get("context") or {})
    context_data.setdefault("run_id", run["run_id"])
    context_data.setdefault("parent_run_id", run.get("parent_run_id"))
    metadata = dict(run.get("metadata") or {})
    if run.get("model"):
        metadata.setdefault("model", run["model"])
    email_id = run.get("email_id")
    output = records_by_email.get(str(email_id)) if email_id else None
    return AgentResult[Any](
        agent_name=run["agent_name"],
        status=run["status"],
        output=output,
        error=run.get("error"),
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        duration_ms=run["duration_ms"],
        context=AgentContext.model_validate(context_data),
        metadata=metadata,
    )


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def main() -> int:
    load_dotenv(override=False)
    parser = argparse.ArgumentParser(
        description="Copy accepted SQLite records and agent logs into a platform database."
    )
    parser.add_argument("--source-db", default="outputs/rfq_extractions.db")
    parser.add_argument("--target-db")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--json", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.source_db).resolve()
    if not source_path.exists():
        parser.error(f"source database does not exist: {source_path}")
    if not args.database_url and not args.target_db:
        parser.error("provide --database-url or --target-db")
    if args.database_url and args.target_db:
        parser.error("provide only one of --database-url or --target-db")
    if args.target_db and Path(args.target_db).resolve() == source_path:
        parser.error("source and target SQLite databases must be different")

    source = ExtractionStore(source_path)
    target = create_store(args.target_db, database_url=args.database_url)
    try:
        counts = copy_results(source, target, args.json, replace=args.replace)
    finally:
        target.close()
        source.close()

    target_label = storage_label(args.target_db, args.database_url)
    print(f"Imported records into {target_label}")
    print(
        f"Rows: emails={counts['emails']}, items={counts['items']}, "
        f"agent_runs={counts['agent_runs']}"
    )
    print(f"JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
