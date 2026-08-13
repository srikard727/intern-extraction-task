from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_rfq_extractor.models import EmailRecord  # noqa: E402
from agent_rfq_extractor.quality import build_review, normalize_items  # noqa: E402
from database.storage import ExtractionStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay stored LLM output through the current deterministic quality rules."
    )
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    source = Path(args.source_db).resolve()
    target = Path(args.db).resolve()
    json_output = Path(args.json).resolve()
    if source == target:
        parser.error("--source-db and --db must be different files")
    if not source.exists():
        parser.error(f"source database does not exist: {source}")
    if target.exists() and not args.replace:
        parser.error(f"target database already exists: {target}; pass --replace to overwrite it")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    _copy_database(source, target)

    store = ExtractionStore(target)
    try:
        records = _renormalize_records(store)
        store.export_json(json_output)
        counts = store.counts()
    finally:
        store.close()

    statuses = Counter(record.status for record in records)
    print(f"Renormalized {len(records)} stored email record(s).")
    print(
        "Rows: "
        f"emails={counts['emails']}, items={counts['items']}, agent_runs={counts['agent_runs']}"
    )
    print(
        "Statuses: "
        + ", ".join(f"{status}={count}" for status, count in sorted(statuses.items()))
    )
    print(f"Database: {target}")
    print(f"JSON: {json_output}")
    return 0


def _copy_database(source: Path, target: Path) -> None:
    source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()


def _renormalize_records(store: ExtractionStore) -> list[EmailRecord]:
    email_rows = store.conn.execute(
        "SELECT email_id, raw_json FROM emails ORDER BY received_at DESC, email_id"
    ).fetchall()
    item_rows = store.conn.execute(
        "SELECT * FROM items ORDER BY email_id, id"
    ).fetchall()
    items_by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in item_rows:
        items_by_email[row["email_id"]].append(dict(row))

    records: list[EmailRecord] = []
    for email_row in email_rows:
        email_id = email_row["email_id"]
        stored_record = json.loads(email_row["raw_json"])
        raw_items = [_raw_item(row) for row in items_by_email.get(email_id, [])]
        items = normalize_items(raw_items)
        raw_review = stored_record.get("review")
        review = build_review(items, raw_review if isinstance(raw_review, dict) else None)
        old_status = stored_record.get("status")
        status = (
            "extraction_failed"
            if old_status == "extraction_failed"
            else "human_review_required"
            if review
            else "completed"
        )
        record = EmailRecord(
            email_id=email_id,
            conv_id=stored_record.get("conv_id"),
            from_email=stored_record.get("from_email"),
            to_email=stored_record.get("to_email"),
            subject=stored_record.get("subject"),
            body_text=str(stored_record.get("body_text") or ""),
            emailbody_variant=str(stored_record.get("emailbody_variant") or "plain"),
            received_at=stored_record.get("received_at"),
            has_attachments=bool(stored_record.get("has_attachments")),
            extracted_at=str(stored_record.get("extracted_at") or ""),
            status=status,
            items=items,
            review=review,
            attachments=stored_record.get("attachments") or [],
            llm_model=stored_record.get("llm_model"),
        )
        store.upsert_record(record)
        records.append(record)
    return records


def _raw_item(row: dict[str, Any]) -> dict[str, Any]:
    raw = _unit_from_payload(_load_json(row.get("spec_json"), {}))
    raw["glass_type"] = row.get("glass_type") or raw.get("glass_type") or "unknown"
    raw["source"] = row.get("source") or "body"
    raw["field_sources"] = _load_json(row.get("field_sources_json"), {})
    raw["notes"] = row.get("notes") or raw.get("notes")

    direct_fields = (
        "mark",
        "quantity",
        "shape",
        "TK",
        "HT",
        "TT",
        "color",
        "overall_thickness",
        "gas_fill",
        "coating",
        "edge_work",
        "interlayer",
    )
    for field in direct_fields:
        if row.get(field) not in (None, ""):
            raw[field] = row[field]
    if row.get("width") is not None and row.get("height") is not None:
        raw["dimensions"] = {
            "width": row["width"],
            "height": row["height"],
            "shape": row.get("shape"),
        }
    if row.get("airspace") not in (None, ""):
        raw["spacer_thickness"] = row["airspace"]
    lite_details = _load_json(row.get("lite_details_json"), [])
    if lite_details:
        raw["lite_details"] = lite_details
    return raw


def _unit_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    extraction = payload.get("extraction") if isinstance(payload.get("extraction"), dict) else payload
    groups = extraction.get("glass_type_groups") if isinstance(extraction, dict) else None
    if not isinstance(groups, list):
        return {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        units = group.get("glass_units")
        if isinstance(units, list) and units and isinstance(units[0], dict):
            return {**units[0], "glass_type": group.get("glass_type")}
    return {}


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


if __name__ == "__main__":
    raise SystemExit(main())
