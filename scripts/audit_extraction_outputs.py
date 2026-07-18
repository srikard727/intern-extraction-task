from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


EXPECTED_FIXTURE_ITEM_COUNTS = {
    "fixture-001": 1,
    "fixture-002": 1,
    "fixture-003": 1,
    "fixture-004": 1,
    "fixture-005": 1,
    "fixture-006": 1,
    "fixture-007": 1,
    "fixture-008": 1,
    "fixture-009": 1,
    "fixture-010": 1,
    "fixture-011": 1,
    "fixture-012": 1,
    "fixture-013": 1,
    "fixture-014": 1,
    "fixture-015": 1,
    "fixture-016": 1,
    "fixture-017": 1,
    "fixture-018": 4,
    "fixture-019": 4,
    "fixture-020": 4,
    "fixture-021": 3,
    "fixture-022": 1,
    "fixture-023": 0,
    "fixture-024": 2,
    "fixture-025": 1,
    "fixture-026": 2,
    "fixture-027": 1,
    "fixture-028": 1,
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


def _invalid_tt(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower().replace("_", " ")
    return text in INVALID_TT_VALUES or text.startswith("attachment:")


def _check_fixture_expectations(records: list[dict[str, Any]], errors: list[str]) -> None:
    by_id = {record.get("email_id"): record for record in records}
    missing_records = sorted(set(EXPECTED_FIXTURE_ITEM_COUNTS) - set(by_id))
    if missing_records:
        errors.append(f"missing fixture records: {', '.join(missing_records)}")

    for email_id, expected_count in EXPECTED_FIXTURE_ITEM_COUNTS.items():
        record = by_id.get(email_id)
        if not record:
            continue
        actual_count = _item_count(record)
        if actual_count != expected_count:
            errors.append(f"{email_id}: expected {expected_count} item(s), found {actual_count}")

    _expect_spec(by_id, "fixture-009", "insulated", 0, "TT1", "bronze", errors)
    _expect_spec(by_id, "fixture-009", "insulated", 0, "TT2", "clear", errors)
    _expect_spec(by_id, "fixture-019", "laminated-insulated", 0, "HT3", "heat strengthened", errors)
    _expect_spec(by_id, "fixture-022", "monolithic", 0, "TK", '3/8"', errors)
    _expect_status(by_id, "fixture-023", "human_review_required", errors)

    record_018 = by_id.get("fixture-018")
    if record_018:
        expected_types = ["monolithic", "laminated", "insulated", "laminated-insulated"]
        actual_types = [
            group.get("glass_type")
            for group in record_018.get("extraction", {}).get("glass_type_groups", [])
        ]
        if actual_types != expected_types:
            errors.append(f"fixture-018: expected groups {expected_types}, found {actual_types}")

    record_024 = by_id.get("fixture-024")
    units_024 = _units_for(record_024, "monolithic") if record_024 else []
    if units_024:
        width = units_024[0].get("width")
        height = units_024[0].get("height")
        if round(float(width or 0), 3) != 23.622 or round(float(height or 0), 3) != 59.055:
            errors.append(f"fixture-024: expected 600mm x 1500mm to normalize to 23.622 x 59.055, found {width} x {height}")


def _expect_status(
    by_id: dict[str, dict[str, Any]],
    email_id: str,
    expected: str,
    errors: list[str],
) -> None:
    actual = by_id.get(email_id, {}).get("status")
    if actual != expected:
        errors.append(f"{email_id}: expected status {expected}, found {actual}")


def _expect_spec(
    by_id: dict[str, dict[str, Any]],
    email_id: str,
    glass_type: str,
    unit_index: int,
    key: str,
    expected: Any,
    errors: list[str],
) -> None:
    units = _units_for(by_id.get(email_id), glass_type)
    if len(units) <= unit_index:
        errors.append(f"{email_id}: missing {glass_type} unit {unit_index + 1}")
        return
    specs = units[unit_index].get("glass_specs", {})
    actual = specs.get(key) if isinstance(specs, dict) else None
    if actual != expected:
        errors.append(f"{email_id}: expected {glass_type} {key}={expected!r}, found {actual!r}")


def _units_for(record: dict[str, Any] | None, glass_type: str) -> list[dict[str, Any]]:
    if not record:
        return []
    groups = record.get("extraction", {}).get("glass_type_groups", [])
    for group in groups:
        if isinstance(group, dict) and group.get("glass_type") == glass_type:
            units = group.get("glass_units", [])
            return [unit for unit in units if isinstance(unit, dict)]
    return []


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
