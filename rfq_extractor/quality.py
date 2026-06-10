from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import Conflict, Dimensions, RFQItem, ReviewInfo
from .units import (
    normalize_measurement,
    normalize_quantity,
    parse_measurements_in_text,
    split_dimension_pair,
)


FIELD_ALIASES = {
    "TK": ("TK", "tk", "thickness", "glass_thickness"),
    "HT": ("HT", "ht", "heat_treatment", "treatment"),
    "TT": ("TT", "tt", "tint", "color", "glass_type"),
}

MAKEUP_ALIASES = {
    "mono": "monolithic",
    "monolithic": "monolithic",
    "single": "monolithic",
    "single lite": "monolithic",
    "lam": "laminated",
    "laminated": "laminated",
    "igu": "insulated",
    "inu": "insulated",
    "insulated": "insulated",
    "insulated unit": "insulated",
    "l-inu": "laminated-insulated",
    "liu": "laminated-insulated",
    "laminated insulated": "laminated-insulated",
    "laminated-insulated": "laminated-insulated",
}


def normalize_items(raw_items: list[dict[str, Any]]) -> list[RFQItem]:
    items: list[RFQItem] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        item = RFQItem(
            mark=_clean(raw.get("mark")),
            dimensions=_normalize_dimensions(raw.get("dimensions")),
            quantity=normalize_quantity(raw.get("quantity")),
            TK=_clean(_first(raw, FIELD_ALIASES["TK"])),
            HT=_normalize_ht(_clean(_first(raw, FIELD_ALIASES["HT"]))),
            TT=_clean(_first(raw, FIELD_ALIASES["TT"])),
            makeup=_normalize_makeup(raw.get("makeup")),
            airspace=_clean(raw.get("airspace")),
            overall_thickness=_clean(raw.get("overall_thickness")),
            coating=_clean(raw.get("coating")),
            edge_work=_clean(raw.get("edge_work")),
            interlayer=_clean(raw.get("interlayer")),
            lite_makeup=_normalize_lite_makeup(raw.get("lite_makeup")),
            source=_clean(raw.get("source")) or "body",
            field_sources=_normalize_field_sources(raw.get("field_sources"), raw.get("source")),
            notes=_clean(raw.get("notes")),
        )
        _lift_single_lite_fields(item)
        if not item.airspace:
            item.airspace = _derive_airspace(item)
        item.missing_fields = missing_fields_for_item(item)
        items.append(item)
    return items


def missing_fields_for_item(item: RFQItem) -> list[str]:
    missing: list[str] = []
    if item.dimensions is None:
        missing.append("dimensions")
    if item.quantity is None:
        missing.append("quantity")
    if not item.TK:
        missing.append("TK")
    if not item.HT:
        missing.append("HT")
    if item.makeup == "unknown":
        missing.append("makeup")

    if item.makeup == "monolithic" and not item.TT:
        missing.append("TT")

    if item.makeup == "laminated":
        if not (item.interlayer or _lite_makeup_mentions_interlayer(item)):
            missing.append("interlayer")

    if item.makeup == "insulated":
        if not (item.airspace or item.overall_thickness):
            missing.append("airspace")
        if len(item.lite_makeup) < 2:
            missing.append("lite_makeup")

    if item.makeup == "laminated-insulated":
        if not (item.airspace or item.overall_thickness):
            missing.append("airspace")
        if len(item.lite_makeup) < 2:
            missing.append("lite_makeup")
        if not (item.interlayer or _lite_makeup_mentions_interlayer(item)):
            missing.append("interlayer")

    return _dedupe(missing)


def build_review(items: list[RFQItem], raw_review: dict[str, Any] | None = None) -> ReviewInfo | None:
    missing = _dedupe(field for item in items for field in item.missing_fields)
    conflicts = _normalize_conflicts((raw_review or {}).get("conflicts"))
    reasons: list[str] = []

    raw_reason = _clean((raw_review or {}).get("reason"))
    if raw_reason:
        reasons.append(raw_reason)

    if missing:
        reasons.append(
            "One or more items are missing required fields: " + ", ".join(missing) + "."
        )
    if not items:
        reasons.append("No glass items were extracted from the message.")
    if conflicts:
        reasons.append("One or more body/attachment conflicts require review.")

    if not reasons and not missing and not conflicts:
        return None
    return ReviewInfo(reason=" ".join(reasons), missing_fields=missing, conflicts=conflicts)


def _normalize_dimensions(raw: object) -> Dimensions | None:
    if raw is None:
        return None

    width_raw: object | None = None
    height_raw: object | None = None

    if isinstance(raw, Mapping):
        width_raw = raw.get("width")
        height_raw = raw.get("height")
        diameter = raw.get("diameter")
        shape = str(raw.get("shape") or "").lower()
        if (width_raw is None or height_raw is None) and diameter is not None:
            width_raw = height_raw = diameter
        if (width_raw is None or height_raw is None) and "round" in shape and raw.get("raw"):
            measures = parse_measurements_in_text(raw.get("raw"))
            if measures:
                width_raw = height_raw = measures[0]
        if (width_raw is None or height_raw is None) and raw.get("raw"):
            pair = split_dimension_pair(str(raw["raw"]))
            if pair:
                width_raw, height_raw = pair
    elif isinstance(raw, str):
        pair = split_dimension_pair(raw)
        if pair:
            width_raw, height_raw = pair

    width = normalize_measurement(width_raw)
    height = normalize_measurement(height_raw)
    if width is None or height is None:
        return None
    return Dimensions(width=width, height=height)


def _derive_airspace(item: RFQItem) -> str | None:
    if not item.overall_thickness or not item.lite_makeup:
        return None
    overall = normalize_measurement(item.overall_thickness)
    if overall is None:
        return None

    lite_thicknesses: list[float] = []
    for lite in item.lite_makeup:
        thickness = lite.get("thickness") or lite.get("TK") or lite.get("tk")
        measurements = parse_measurements_in_text(thickness)
        if len(measurements) == 1:
            lite_thicknesses.append(measurements[0])

    if len(lite_thicknesses) < 2:
        return None
    airspace = overall - sum(lite_thicknesses)
    if airspace <= 0:
        return None
    return f"{round(airspace, 4)} inch"


def _lift_single_lite_fields(item: RFQItem) -> None:
    if not item.lite_makeup:
        return
    if len(item.lite_makeup) != 1 and item.makeup == "monolithic":
        return
    lite = item.lite_makeup[0]
    if not item.TK:
        item.TK = _clean(lite.get("thickness") or lite.get("TK") or lite.get("tk"))
    if not item.HT:
        item.HT = _normalize_ht(_clean(lite.get("HT") or lite.get("ht")))
    if not item.TT:
        item.TT = _clean(lite.get("TT") or lite.get("tt") or lite.get("color"))
    if not item.TT:
        item.TT = _infer_tt_from_text(lite.get("notes"))
    if item.TT and "TT" not in item.field_sources:
        item.field_sources["TT"] = item.source


def _infer_tt_from_text(raw: object) -> str | None:
    text = _clean(raw)
    if not text:
        return None
    lower = text.lower()
    for color in (
        "low-iron",
        "low iron",
        "clear",
        "bronze",
        "grey",
        "gray",
        "green",
        "mirror",
        "ceramic",
    ):
        if color in lower:
            return "low-iron" if color == "low iron" else color
    return None


def _normalize_makeup(raw: object) -> str:
    value = _clean(raw)
    if not value:
        return "unknown"
    key = value.lower().replace("_", "-")
    return MAKEUP_ALIASES.get(key, "unknown")


def _normalize_ht(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.lower()
    if value in {"ft", "fully tempered", "temp", "tempered"}:
        return "tempered"
    if value in {"hs", "heat strengthened", "heat-strengthened"}:
        return "heat-strengthened"
    if value in {"ann", "annealed"}:
        return "annealed"
    return raw


def _normalize_lite_makeup(raw: object) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [dict(entry) for entry in raw if isinstance(entry, Mapping)]
    if isinstance(raw, Mapping):
        return [dict(raw)]
    return [{"description": str(raw)}]


def _normalize_field_sources(raw: object, item_source: object) -> dict[str, str]:
    if isinstance(raw, Mapping):
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    source = _clean(item_source) or "body"
    return {"item": source}


def _normalize_conflicts(raw: object) -> list[Conflict]:
    if not isinstance(raw, list):
        return []
    conflicts: list[Conflict] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        field = _clean(entry.get("field"))
        if field:
            conflicts.append(
                Conflict(
                    field=field,
                    body=_clean(entry.get("body")),
                    attachment=_clean(entry.get("attachment")),
                    source=_clean(entry.get("source")),
                )
            )
    return conflicts


def _lite_makeup_mentions_interlayer(item: RFQItem) -> bool:
    haystack = " ".join(str(entry) for entry in item.lite_makeup).lower()
    return any(term in haystack for term in ("pvb", "sgp", "interlayer", ".030", ".060", ".090"))


def _first(raw: Mapping[str, Any], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
