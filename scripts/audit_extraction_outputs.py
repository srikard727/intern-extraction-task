from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_EXPECTATIONS_PATH = PROJECT_ROOT / "tests/fixtures/expected_fixture_extractions.json"
EXPECTED_FIXTURE_MODEL = "claude-opus-4-8"
REQUIRED_EMAIL_FIELDS = {
    "email_id",
    "conv_id",
    "from_email",
    "to_email",
    "subject",
    "body_text",
    "emailbody_variant",
    "received_at",
    "has_attachments",
    "extracted_at",
    "status",
}

INVALID_TT_VALUES = {
    "attachment",
    "attachments",
    "body",
    "glass type",
    "igu",
    "insulated",
    "laminated",
    "laminated-insulated",
    "liu",
    "monolithic",
    "source",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit RFQ extraction JSON and SQLite outputs.")
    parser.add_argument("--json", default="outputs/rfq_extractions.json")
    parser.add_argument("--db", default="outputs/rfq_extractions.db")
    parser.add_argument("--fixture-expectations", action="store_true")
    args = parser.parse_args()

    records = _load_json(Path(args.json))
    db_counts = _db_counts(Path(args.db))
    errors: list[str] = []

    _check_counts(records, db_counts, errors)
    _check_json_shape(records, errors)
    _check_sqlite_integrity(Path(args.db), errors)
    if args.fixture_expectations:
        _check_fixture_expectations(records, errors)

    print(f"JSON records: {len(records)}")
    print(
        "SQLite rows: "
        f"emails={db_counts['emails']}, items={db_counts['items']}, agent_runs={db_counts['agent_runs']}"
    )
    status_counts: dict[str, int] = {}
    for record in records:
        status_counts[record.get("status", "unknown")] = status_counts.get(record.get("status", "unknown"), 0) + 1
    print("Statuses: " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())))

    if errors:
        print("\nAudit failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nAudit passed.")
    return 0


def _load_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return [record for record in data if isinstance(record, dict)]


def _db_counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(path)
    try:
        return {
            "emails": _count(conn, "emails"),
            "items": _count(conn, "items"),
            "agent_runs": _count(conn, "agent_runs"),
        }
    finally:
        conn.close()


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _check_counts(records: list[dict[str, Any]], db_counts: dict[str, int], errors: list[str]) -> None:
    json_items = sum(_item_count(record) for record in records)
    if len(records) != db_counts["emails"]:
        errors.append(f"JSON record count {len(records)} does not match SQLite emails {db_counts['emails']}")
    if json_items != db_counts["items"]:
        errors.append(f"JSON item count {json_items} does not match SQLite items {db_counts['items']}")
    if db_counts["agent_runs"] < db_counts["emails"]:
        errors.append("SQLite agent_runs should have at least one row per email")


def _check_json_shape(records: list[dict[str, Any]], errors: list[str]) -> None:
    for record in records:
        email_id = record.get("email_id", "(missing email_id)")
        missing_email_fields = sorted(REQUIRED_EMAIL_FIELDS - set(record))
        if missing_email_fields:
            errors.append(
                f"{email_id}: missing required email field(s): {', '.join(missing_email_fields)}"
            )
        _check_record_status(record, errors)
        extraction = record.get("extraction")
        if not isinstance(extraction, dict):
            errors.append(f"{email_id}: missing extraction object")
            continue
        groups = extraction.get("glass_type_groups")
        if not isinstance(groups, list):
            errors.append(f"{email_id}: extraction.glass_type_groups must be a list")
            continue
        for group in groups:
            group_type = group.get("glass_type") if isinstance(group, dict) else None
            units = group.get("glass_units") if isinstance(group, dict) else None
            if not isinstance(units, list):
                errors.append(f"{email_id}: {group_type} group glass_units must be a list")
                continue
            for unit_index, unit in enumerate(units, start=1):
                if not isinstance(unit, dict):
                    errors.append(f"{email_id}: {group_type} unit {unit_index} is not an object")
                    continue
                _check_unit(email_id, group_type, unit_index, unit, errors)
            if isinstance(group, dict) and isinstance(units, list):
                expected_complete = all(
                    isinstance(unit, dict) and not unit.get("missing_fields")
                    for unit in units
                )
                if group.get("is_complete") != expected_complete:
                    errors.append(
                        f"{email_id}: {group_type} group is_complete does not match its units"
                    )


def _check_record_status(record: dict[str, Any], errors: list[str]) -> None:
    email_id = record.get("email_id", "(missing email_id)")
    status = record.get("status")
    review = record.get("review")
    extraction = record.get("extraction")
    if status not in {"completed", "human_review_required", "extraction_failed"}:
        errors.append(f"{email_id}: invalid status {status!r}")
    if status == "completed" and review is not None:
        errors.append(f"{email_id}: completed record must not contain a review object")
    if status == "human_review_required":
        reason = review.get("reason") if isinstance(review, dict) else None
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{email_id}: human review record needs a non-empty reason")
    if (
        status == "completed"
        and isinstance(extraction, dict)
        and extraction.get("is_complete") is not True
    ):
        errors.append(f"{email_id}: completed record has an incomplete extraction")


def _check_unit(
    email_id: str,
    group_type: str | None,
    unit_index: int,
    unit: dict[str, Any],
    errors: list[str],
) -> None:
    label = f"{email_id}: {group_type} unit {unit_index}"
    for forbidden in ("field_sources", "source"):
        if forbidden in unit:
            errors.append(f"{label}: exported unit contains forbidden key {forbidden}")
    if unit.get("shape") not in {"rectangle", "square", "circle"}:
        errors.append(f"{label}: invalid or missing shape {unit.get('shape')!r}")
    quantity = unit.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        errors.append(f"{label}: quantity must be a positive integer")
    width = unit.get("width")
    height = unit.get("height")
    if (width is None) != (height is None):
        errors.append(f"{label}: width and height must both be present or both be null")
    if width is not None and (not isinstance(width, int | float) or width <= 0):
        errors.append(f"{label}: width must be positive")
    if height is not None and (not isinstance(height, int | float) or height <= 0):
        errors.append(f"{label}: height must be positive")
    if unit.get("unit_of_measurement") != "inch":
        errors.append(f"{label}: unit_of_measurement must be inch")
    missing_fields = unit.get("missing_fields", [])
    if not isinstance(missing_fields, list):
        errors.append(f"{label}: missing_fields must be a list")
    if unit.get("is_complete") != (not missing_fields):
        errors.append(f"{label}: is_complete does not match missing_fields")

    specs = unit.get("glass_specs", {})
    if not isinstance(specs, dict):
        errors.append(f"{label}: glass_specs must be an object")
        return
    for key, value in specs.items():
        if key.startswith("TT") and _invalid_tt(value):
            errors.append(f"{label}: {key} has invalid TT value {value!r}")
    confidence = unit.get("field_confidence")
    if not isinstance(confidence, dict):
        errors.append(f"{label}: field_confidence must be an object")
    else:
        for field, score in confidence.items():
            if (
                isinstance(score, bool)
                or not isinstance(score, int | float)
                or not 0 <= score <= 1
            ):
                errors.append(f"{label}: invalid confidence for {field}: {score!r}")


def _invalid_tt(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower().replace("_", " ")
    return text in INVALID_TT_VALUES or text.startswith("attachment:")


def _check_sqlite_integrity(path: Path, errors: list[str]) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            errors.append(f"SQLite foreign_key_check found {len(foreign_key_errors)} error(s)")

        orphan_items = conn.execute(
            """
            SELECT COUNT(*)
            FROM items i
            LEFT JOIN emails e ON e.email_id = i.email_id
            WHERE e.email_id IS NULL
            """
        ).fetchone()[0]
        if orphan_items:
            errors.append(f"SQLite contains {orphan_items} orphan item row(s)")

        emails_without_runs = conn.execute(
            """
            SELECT COUNT(*)
            FROM emails e
            LEFT JOIN agent_runs a ON a.email_id = e.email_id
            WHERE a.email_id IS NULL
            """
        ).fetchone()[0]
        if emails_without_runs:
            errors.append(f"SQLite contains {emails_without_runs} email(s) without an agent run")

        rows = conn.execute(
            """
            SELECT
                id, email_id, mark, width, height, quantity, shape,
                TK, HT, TT, color, glass_type, airspace, gas_fill,
                coating, edge_work, source, field_sources_json, spec_json
            FROM items
            ORDER BY email_id, id
            """
        ).fetchall()
        for row in rows:
            _check_item_sources(dict(row), errors)
    finally:
        conn.close()


def _check_item_sources(row: dict[str, Any], errors: list[str]) -> None:
    label = f"{row.get('email_id')}: SQLite item {row.get('id')}"
    item_source = row.get("source")
    if not _valid_source(item_source):
        errors.append(f"{label}: invalid item source {item_source!r}")

    try:
        field_sources = json.loads(row.get("field_sources_json") or "{}")
    except json.JSONDecodeError:
        errors.append(f"{label}: field_sources_json is invalid JSON")
        return
    if not isinstance(field_sources, dict):
        errors.append(f"{label}: field_sources_json must be an object")
        return
    for field, source in field_sources.items():
        if source == "default" and field not in {"quantity", "shape"}:
            errors.append(f"{label}: default source is not allowed for {field}")
        elif source != "default" and not _valid_source(source):
            errors.append(f"{label}: invalid source for {field}: {source!r}")

    expected_fields: set[str] = {"quantity", "shape", "glass_type"}
    if row.get("width") is not None and row.get("height") is not None:
        expected_fields.add("dimensions")
    for field in ("mark", "TK", "HT", "TT", "color", "gas_fill", "coating", "edge_work"):
        if row.get(field) not in (None, ""):
            expected_fields.add(field)
    if row.get("airspace") not in (None, ""):
        expected_fields.add("spacer_thickness")

    try:
        spec_payload = json.loads(row.get("spec_json") or "{}")
    except json.JSONDecodeError:
        errors.append(f"{label}: spec_json is invalid JSON")
        spec_payload = {}
    units = _flat_items({"extraction": spec_payload})
    if units:
        for field, value in (units[0].get("glass_specs") or {}).items():
            if value not in (None, ""):
                expected_fields.add("laminate_lite" if field == "laminated_lite" else field)
        fabrication = units[0].get("fabrication") or {}
        fabrication_source_fields = {
            "coatings": "coating",
            "edge_work": "edge_work",
            "details": "fabrication_details",
        }
        for field, source_field in fabrication_source_fields.items():
            if fabrication.get(field) not in (None, ""):
                expected_fields.add(source_field)

    missing_sources = sorted(field for field in expected_fields if field not in field_sources)
    if missing_sources:
        errors.append(
            f"{label}: missing source attribution for {', '.join(missing_sources)}"
        )


def _valid_source(value: Any) -> bool:
    return isinstance(value, str) and (
        value == "body" or (value.startswith("attachment:") and len(value) > len("attachment:"))
    )


def _check_fixture_expectations(records: list[dict[str, Any]], errors: list[str]) -> None:
    expectations = json.loads(FIXTURE_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    by_id = {record.get("email_id"): record for record in records}
    missing_records = sorted(set(expectations) - set(by_id))
    if missing_records:
        errors.append(f"missing fixture records: {', '.join(missing_records)}")

    unexpected_records = sorted(set(by_id) - set(expectations))
    if unexpected_records:
        errors.append(f"unexpected fixture records: {', '.join(unexpected_records)}")

    for email_id, expected_record in expectations.items():
        record = by_id.get(email_id)
        if not record:
            continue
        expected_status = expected_record.get("status")
        if record.get("status") != expected_status:
            errors.append(
                f"{email_id}: expected status {expected_status}, found {record.get('status')}"
            )
        if record.get("llm_model") != EXPECTED_FIXTURE_MODEL:
            errors.append(
                f"{email_id}: expected model {EXPECTED_FIXTURE_MODEL}, "
                f"found {record.get('llm_model')}"
            )

        actual_items = _flat_items(record)
        expected_items = expected_record.get("items", [])
        if len(actual_items) != len(expected_items):
            errors.append(
                f"{email_id}: expected {len(expected_items)} item(s), "
                f"found {len(actual_items)}"
            )
            continue
        for index, (actual, expected) in enumerate(
            zip(actual_items, expected_items, strict=True),
            start=1,
        ):
            _check_expected_item(email_id, index, actual, expected, errors)


def _flat_items(record: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    groups = record.get("extraction", {}).get("glass_type_groups", [])
    if not isinstance(groups, list):
        return items
    for group in groups:
        if not isinstance(group, dict):
            continue
        glass_type = group.get("glass_type")
        units = group.get("glass_units", [])
        if not isinstance(units, list):
            continue
        for unit in units:
            if isinstance(unit, dict):
                items.append({**unit, "_glass_type": glass_type})
    return items


def _check_expected_item(
    email_id: str,
    index: int,
    actual: dict[str, Any],
    expected: dict[str, Any],
    errors: list[str],
) -> None:
    label = f"{email_id}: item {index}"
    field_map = {
        "glass_type": "_glass_type",
        "mark": "mark",
        "width": "width",
        "height": "height",
        "quantity": "quantity",
        "shape": "shape",
        "missing_fields": "missing_fields",
    }
    for expected_field, actual_field in field_map.items():
        if expected_field not in expected:
            continue
        expected_value = expected[expected_field]
        actual_value = actual.get(actual_field)
        if not _same_expected_value(actual_value, expected_value):
            errors.append(
                f"{label}: expected {expected_field}={expected_value!r}, "
                f"found {actual_value!r}"
            )

    specs = actual.get("glass_specs") if isinstance(actual.get("glass_specs"), dict) else {}
    for field, expected_value in expected.get("specs", {}).items():
        actual_value = specs.get(field)
        if not _same_expected_value(actual_value, expected_value):
            errors.append(
                f"{label}: expected {field}={expected_value!r}, found {actual_value!r}"
            )

    fabrication = (
        actual.get("fabrication") if isinstance(actual.get("fabrication"), dict) else {}
    )
    for field, expected_value in expected.get("fabrication", {}).items():
        actual_value = fabrication.get(field)
        if not _same_expected_value(actual_value, expected_value):
            errors.append(
                f"{label}: expected fabrication.{field}={expected_value!r}, "
                f"found {actual_value!r}"
            )
    for field, expected_fragments in expected.get("fabrication_contains", {}).items():
        actual_text = str(fabrication.get(field) or "").lower()
        for fragment in expected_fragments:
            if str(fragment).lower() not in actual_text:
                errors.append(
                    f"{label}: fabrication.{field} does not contain {fragment!r}"
                )


def _same_expected_value(actual: Any, expected: Any) -> bool:
    if (
        not isinstance(actual, bool)
        and not isinstance(expected, bool)
        and isinstance(actual, int | float)
        and isinstance(expected, int | float)
    ):
        return abs(float(actual) - float(expected)) <= 0.0001
    return actual == expected


def _item_count(record: dict[str, Any]) -> int:
    groups = record.get("extraction", {}).get("glass_type_groups", [])
    if not isinstance(groups, list):
        return 0
    return sum(
        len(group.get("glass_units", []))
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("glass_units"), list)
    )


if __name__ == "__main__":
    raise SystemExit(main())
