from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .models import Conflict, Dimensions, RFQItem, ReviewInfo, Shape
from .units import (
    normalize_measurement,
    normalize_quantity,
    parse_measurements_in_text,
    split_dimension_pair,
)


FIELD_ALIASES = {
    "TK": ("TK", "tk", "thickness", "glass_thickness"),
    "HT": ("HT", "ht", "heat_treatment", "heat_type", "treatment"),
    "TT": ("TT", "tt", "tint", "glass_tint"),
    "color": ("color", "glass_color", "tint_color"),
    "TK1": ("TK1", "tk1", "thickness1", "lite1_thickness", "outboard_thickness"),
    "HT1": ("HT1", "ht1", "heat_treatment1", "heat_type1", "lite1_HT", "outboard_HT"),
    "TT1": ("TT1", "tt1", "tint1", "color1", "lite1_TT", "outboard_TT"),
    "TK2": ("TK2", "tk2", "thickness2", "lite2_thickness", "inboard_thickness"),
    "HT2": ("HT2", "ht2", "heat_treatment2", "heat_type2", "lite2_HT", "inboard_HT"),
    "TT2": ("TT2", "tt2", "tint2", "color2", "lite2_TT", "inboard_TT"),
    "TK3": ("TK3", "tk3", "thickness3", "lite3_thickness"),
    "HT3": ("HT3", "ht3", "heat_treatment3", "heat_type3", "lite3_HT"),
    "TT3": ("TT3", "tt3", "tint3", "color3", "lite3_TT"),
    "spacer_material": ("spacer_material", "spacer_type", "bar_material"),
    "spacer_thickness": (
        "spacer_thickness",
        "spacer_width",
        "airspace",
        "air_space",
        "air_space_thickness",
        "gap",
        "cavity",
    ),
    "gas_fill": ("gas_fill", "gas", "fill", "gas_type"),
    "interlayer_material": ("interlayer_material", "interlayer_type"),
    "interlayer_thickness": ("interlayer_thickness", "interlayer_width"),
    "laminate_lite": (
        "laminate_lite",
        "laminated_lite",
        "laminate_position",
        "laminated_position",
    ),
}

GLASS_TYPE_ALIASES = {
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
    "laminated_insulated": "laminated-insulated",
}

CONSTRUCTION_TT_VALUES = {
    "glass",
    "glass type",
    "igu",
    "insulated",
    "insulated glass",
    "insulated unit",
    "inu",
    "lam",
    "laminated",
    "laminated glass",
    "laminated insulated",
    "laminated insulated glass",
    "laminated insulated unit",
    "laminated-insulated",
    "liu",
    "mono",
    "monolithic",
    "monolithic glass",
    "single",
    "single glass",
    "single lite",
    "unit",
}

SOURCE_TT_VALUES = {"attachment", "attachments", "body", "source"}

MONOLITHIC_COLOR_ONLY_TT_VALUES = {
    "black",
    "blue",
    "bronze",
    "gray",
    "green",
    "grey",
    "warm gray",
    "warm grey",
    "white",
}


def normalize_items(raw_items: list[dict[str, Any]]) -> list[RFQItem]:
    items: list[RFQItem] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        raw = _flatten_formatted_item(raw)

        quantity, quantity_note = _normalize_quantity_with_default(raw.get("quantity"))
        item = RFQItem(
            mark=_clean(raw.get("mark")),
            dimensions=_normalize_dimensions(raw.get("dimensions")),
            quantity=quantity,
            shape=_normalize_shape(raw.get("shape"), raw.get("dimensions"), raw),
            TK=_clean(_first(raw, FIELD_ALIASES["TK"])),
            HT=_normalize_ht(_clean(_first(raw, FIELD_ALIASES["HT"]))),
            TT=_clean(_first(raw, FIELD_ALIASES["TT"])),
            color=_clean(_first(raw, FIELD_ALIASES["color"])),
            glass_type=_normalize_glass_type(raw.get("glass_type")),
            TK1=_clean(_first(raw, FIELD_ALIASES["TK1"])),
            HT1=_normalize_ht(_clean(_first(raw, FIELD_ALIASES["HT1"]))),
            TT1=_clean(_first(raw, FIELD_ALIASES["TT1"])),
            TK2=_clean(_first(raw, FIELD_ALIASES["TK2"])),
            HT2=_normalize_ht(_clean(_first(raw, FIELD_ALIASES["HT2"]))),
            TT2=_clean(_first(raw, FIELD_ALIASES["TT2"])),
            TK3=_clean(_first(raw, FIELD_ALIASES["TK3"])),
            HT3=_normalize_ht(_clean(_first(raw, FIELD_ALIASES["HT3"]))),
            TT3=_clean(_first(raw, FIELD_ALIASES["TT3"])),
            spacer_material=_normalize_spacer_material(
                _first(raw, FIELD_ALIASES["spacer_material"])
            ),
            spacer_thickness=_normalize_spacer_thickness(
                _first(raw, FIELD_ALIASES["spacer_thickness"])
            ),
            gas_fill=_normalize_gas_fill(_first(raw, FIELD_ALIASES["gas_fill"])),
            interlayer_material=_clean(_first(raw, FIELD_ALIASES["interlayer_material"])),
            interlayer_thickness=_normalize_interlayer_thickness(
                _first(raw, FIELD_ALIASES["interlayer_thickness"])
            ),
            laminate_lite=_normalize_laminate_lite(
                _clean(_first(raw, FIELD_ALIASES["laminate_lite"]))
            ),
            airspace=_normalize_spacer_thickness(raw.get("airspace")),
            overall_thickness=_clean(raw.get("overall_thickness")),
            coating=_clean(raw.get("coating")),
            edge_work=_clean(raw.get("edge_work")),
            interlayer=_clean(raw.get("interlayer")),
            lite_details=_normalize_lite_details(raw.get("lite_details")),
            source=_clean(raw.get("source")) or "body",
            field_sources=_normalize_field_sources(raw.get("field_sources"), raw.get("source")),
            notes=_clean(raw.get("notes")),
        )

        if quantity_note:
            item.field_sources.setdefault("quantity", "default")
            item.notes = _append_note(item.notes, quantity_note)

        _apply_lite_details(item)
        _apply_construction_text(item, raw)
        _apply_legacy_parts(item)
        _derive_missing_spacer_thickness(item)
        _apply_no_guess_guards(item, raw)
        _cleanup_tt_values(item)
        _apply_glass_type_scope(item)
        _cleanup_field_sources(item)
        item.missing_fields = missing_fields_for_item(item)
        items.append(item)
    return items


def _flatten_formatted_item(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Accept either Claude's flat item schema or the final formatted unit shape."""
    item = dict(raw)
    specs = raw.get("glass_specs")
    if isinstance(specs, Mapping):
        for field, value in specs.items():
            item.setdefault(str(field), value)

    fabrication = raw.get("fabrication")
    if isinstance(fabrication, Mapping):
        if "coatings" in fabrication:
            item.setdefault("coating", fabrication.get("coatings"))
        if "edge_work" in fabrication:
            item.setdefault("edge_work", fabrication.get("edge_work"))

    if "dimensions" not in item and ("width" in raw or "height" in raw):
        item["dimensions"] = {
            "width": raw.get("width"),
            "height": raw.get("height"),
            "shape": raw.get("shape"),
        }

    return item


def missing_fields_for_item(item: RFQItem) -> list[str]:
    missing: list[str] = []
    if item.dimensions is None:
        missing.append("dimensions")
    if item.glass_type == "unknown":
        missing.append("glass_type")

    if item.glass_type == "monolithic":
        if not item.TK:
            missing.append("TK")
        if not item.HT and not _is_mirror(item):
            missing.append("HT")
    elif item.glass_type == "laminated":
        missing.extend(
            field
            for field in (
                "TK1",
                "TK2",
                "interlayer_thickness",
                "interlayer_material",
                "HT1",
                "HT2",
            )
            if not getattr(item, field)
        )
    elif item.glass_type == "insulated":
        missing.extend(
            field
            for field in (
                "TK1",
                "TK2",
                "spacer_material",
                "spacer_thickness",
                "HT1",
                "HT2",
            )
            if not getattr(item, field)
        )
    elif item.glass_type == "laminated-insulated":
        missing.extend(
            field
            for field in (
                "TK1",
                "TK2",
                "TK3",
                "HT1",
                "HT2",
                "HT3",
                "interlayer_material",
                "interlayer_thickness",
                "spacer_material",
                "spacer_thickness",
                "laminate_lite",
            )
            if not getattr(item, field)
        )

    return _dedupe(missing)


def build_review(items: list[RFQItem], raw_review: dict[str, Any] | None = None) -> ReviewInfo | None:
    missing = _dedupe(field for item in items for field in item.missing_fields)
    conflicts = _normalize_conflicts((raw_review or {}).get("conflicts"))
    reasons: list[str] = []

    raw_reason = _strip_generated_missing_fields_sentence(_clean((raw_review or {}).get("reason")))
    if (
        raw_reason
        and not _is_ignorable_review_reason(raw_reason, items, conflicts)
        and _raw_reason_requires_review(raw_reason, items, missing, conflicts)
    ):
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


def _normalize_quantity_with_default(raw: object) -> tuple[int, str | None]:
    quantity = normalize_quantity(raw)
    if quantity is not None:
        return quantity, None
    if raw in (None, ""):
        return 1, "Quantity was not specified; defaulted to 1 piece."
    return 1, f"Quantity was ambiguous ({raw}); defaulted to minimum 1 piece."


def _normalize_dimensions(raw: object) -> Dimensions | None:
    if raw is None:
        return None

    width_raw: object | None = None
    height_raw: object | None = None

    if isinstance(raw, Mapping):
        width_raw = raw.get("width")
        height_raw = raw.get("height")
        diameter = raw.get("diameter") or raw.get("radius")
        shape = str(raw.get("shape") or "").lower()
        if raw.get("radius") and not raw.get("diameter"):
            radius = normalize_measurement(raw.get("radius"))
            if radius is not None:
                diameter = radius * 2
        if (width_raw is None or height_raw is None) and diameter is not None:
            width_raw = height_raw = diameter
        if (width_raw is None or height_raw is None) and raw.get("raw"):
            raw_text = str(raw["raw"])
            pair = split_dimension_pair(raw_text)
            if pair:
                width_raw, height_raw = pair
            elif "round" in shape or _mentions_circle(raw_text) or _mentions_square(raw_text):
                measures = parse_measurements_in_text(raw_text)
                if measures:
                    width_raw = height_raw = measures[0]
    elif isinstance(raw, str):
        pair = split_dimension_pair(raw)
        if pair:
            width_raw, height_raw = pair
        elif _mentions_circle(raw) or _mentions_square(raw):
            measures = parse_measurements_in_text(raw)
            if measures:
                width_raw = height_raw = measures[0]

    width = normalize_measurement(width_raw)
    height = normalize_measurement(height_raw)
    if width is None or height is None:
        return None
    return Dimensions(width=width, height=height)


def _normalize_shape(raw_shape: object, raw_dimensions: object, raw_item: Mapping[str, Any]) -> Shape:
    if isinstance(raw_dimensions, Mapping):
        width = normalize_measurement(raw_dimensions.get("width"))
        height = normalize_measurement(raw_dimensions.get("height"))
        if raw_dimensions.get("diameter") or raw_dimensions.get("radius"):
            return "circle"
        raw_text = _clean(raw_dimensions.get("raw"))
        dimension_text = " ".join(
            part
            for part in (
                _clean(raw_dimensions.get("shape")),
                raw_text,
            )
            if part
        )
        if _mentions_circle(dimension_text) and not split_dimension_pair(dimension_text):
            return "circle"
        if _mentions_square(dimension_text) and not split_dimension_pair(dimension_text):
            return "square"
        if width is not None and height is not None:
            if width == height and _mentions_circle(raw_shape):
                return "circle"
            return "rectangle"
        if raw_text and split_dimension_pair(raw_text):
            return "rectangle"
        if raw_text and not split_dimension_pair(raw_text):
            return "square"
    elif isinstance(raw_dimensions, str) and raw_dimensions and not split_dimension_pair(raw_dimensions):
        if _mentions_circle(raw_dimensions):
            return "circle"
        if parse_measurements_in_text(raw_dimensions):
            return "square"

    shape_text = _clean(raw_shape)
    if shape_text:
        if _mentions_circle(shape_text):
            return "circle"
        if _mentions_square(shape_text):
            return "square"
        if any(word in shape_text.lower() for word in ("rectangle", "rectangular")):
            return "rectangle"

    return "rectangle"


def _apply_lite_details(item: RFQItem) -> None:
    if not item.lite_details:
        return

    for index, lite in enumerate(item.lite_details[:3], start=1):
        tk_key = f"TK{index}"
        ht_key = f"HT{index}"
        tt_key = f"TT{index}"
        if not getattr(item, tk_key):
            setattr(item, tk_key, _clean(lite.get("thickness") or lite.get("TK") or lite.get("tk")))
        if not getattr(item, ht_key):
            setattr(item, ht_key, _normalize_ht(_clean(lite.get("HT") or lite.get("ht"))))
        if not getattr(item, tt_key):
            setattr(
                item,
                tt_key,
                _clean(lite.get("TT") or lite.get("tt") or lite.get("color"))
                or _infer_tt_from_text(lite.get("notes")),
            )

    if item.glass_type == "monolithic":
        if not item.TK:
            item.TK = item.TK1
        if not item.HT:
            item.HT = item.HT1
        if not item.TT:
            item.TT = item.TT1


def _apply_construction_text(item: RFQItem, raw: Mapping[str, Any]) -> None:
    text = _raw_text(raw)
    if not text:
        return

    if item.glass_type in {"laminated", "laminated-insulated"}:
        _apply_laminated_sequence(item, text)
        if not item.laminate_lite:
            item.laminate_lite = _infer_laminate_lite(text)

    if item.glass_type in {"insulated", "laminated-insulated"}:
        _apply_insulated_sequence(item, text)
        if not item.spacer_material:
            item.spacer_material = _extract_spacer_material(text)
        if not item.gas_fill:
            item.gas_fill = _extract_gas_fill(text)


def _apply_laminated_sequence(item: RFQItem, text: str) -> None:
    parts = [part.strip(" -,") for part in re.split(r"\s*\+\s*", text) if part.strip()]
    if len(parts) < 3:
        return
    for index in range(len(parts) - 2):
        first, middle, second = parts[index], parts[index + 1], parts[index + 2]
        if not _looks_like_interlayer(middle):
            continue
        tk1 = _extract_thickness(first)
        tk2 = _extract_thickness(second)
        if tk1 and not item.TK1:
            item.TK1 = tk1
        if tk2 and not item.TK2:
            item.TK2 = tk2
        ht1 = _extract_ht(first)
        ht2 = _extract_ht(second)
        if ht1 and not item.HT1:
            item.HT1 = ht1
        if ht2 and not item.HT2:
            item.HT2 = ht2
        tt1 = _extract_tt(first)
        tt2 = _extract_tt(second)
        if tt1 and not item.TT1:
            item.TT1 = tt1
        if tt2 and not item.TT2:
            item.TT2 = tt2
        material, thickness = _split_interlayer(middle)
        if material and not item.interlayer_material:
            item.interlayer_material = material
        if thickness and not item.interlayer_thickness:
            item.interlayer_thickness = thickness
        return


def _apply_insulated_sequence(item: RFQItem, text: str) -> None:
    if "/" not in text:
        _apply_inline_spacer_sequence(item, text)
        return
    parts = [part.strip(" -,") for part in re.split(r"\s+/\s+", text) if part.strip()]
    if len(parts) < 3:
        _apply_inline_spacer_sequence(item, text)
        return

    for index in range(len(parts) - 2):
        first, middle, second = parts[index], parts[index + 1], parts[index + 2]
        spacer = _normalize_spacer_thickness(middle)
        if not spacer and not any(word in middle.lower() for word in ("air", "spacer", "bar")):
            continue

        if item.glass_type == "insulated":
            if not item.TK1:
                item.TK1 = _extract_thickness(first)
            if not item.TK2:
                item.TK2 = _extract_thickness(second)
            if not item.HT1:
                item.HT1 = _extract_ht(first)
            if not item.HT2:
                item.HT2 = _extract_ht(second)
            if not item.TT1:
                item.TT1 = _extract_tt(first)
            if not item.TT2:
                item.TT2 = _extract_tt(second)
        else:
            if not item.spacer_thickness and spacer:
                item.spacer_thickness = spacer
            if not item.TK3:
                item.TK3 = _extract_thickness(second)
            if not item.HT3:
                item.HT3 = _extract_ht(second)
            if not item.TT3:
                item.TT3 = _extract_tt(second)

        if not item.spacer_thickness and spacer:
            item.spacer_thickness = spacer
        material = _extract_spacer_material(middle)
        if material and not item.spacer_material:
            item.spacer_material = material
        return


def _apply_inline_spacer_sequence(item: RFQItem, text: str) -> None:
    match = re.search(
        r"(?P<spacer>\d+\s*-\s*\d+/\d+|\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+(?:\.\d+)?\s*mm|\d+(?:\.\d+)?)\s*\"?\s*(?:(?:black|silver|gray|grey|bronze|white|warm edge|stainless|aluminum|aluminium)\s+)?(?:airspace|spacer|bar)",
        text,
        re.I,
    )
    if not match:
        return
    if not item.spacer_thickness:
        item.spacer_thickness = _format_measurement(match.group("spacer"))
    if not item.spacer_material:
        item.spacer_material = _extract_spacer_material(text)

    after_spacer = text[match.end() :]
    if item.glass_type == "laminated-insulated":
        if not item.TK3:
            item.TK3 = _extract_thickness(after_spacer)
        if not item.HT3:
            item.HT3 = _extract_ht(after_spacer)
        if not item.TT3:
            item.TT3 = _extract_tt(after_spacer)


def _apply_legacy_parts(item: RFQItem) -> None:
    if item.airspace and not item.spacer_thickness:
        item.spacer_thickness = item.airspace
    if item.interlayer:
        material, thickness = _split_interlayer(item.interlayer)
        if material and not item.interlayer_material:
            item.interlayer_material = material
        if thickness and not item.interlayer_thickness:
            item.interlayer_thickness = thickness

    if item.glass_type == "monolithic":
        return

    if item.TK and any(separator in item.TK for separator in ("+", "/")):
        _apply_laminated_sequence(item, item.TK)
        _apply_insulated_sequence(item, item.TK)


def _derive_missing_spacer_thickness(item: RFQItem) -> None:
    if item.spacer_thickness or not item.overall_thickness:
        return

    overall = normalize_measurement(item.overall_thickness)
    if overall is None:
        return

    if item.glass_type == "insulated":
        thicknesses = [normalize_measurement(item.TK1), normalize_measurement(item.TK2)]
    elif item.glass_type == "laminated-insulated":
        thicknesses = [
            normalize_measurement(item.TK1),
            normalize_measurement(item.TK2),
            normalize_measurement(item.TK3),
            normalize_measurement(item.interlayer_thickness),
        ]
    else:
        return

    if any(value is None for value in thicknesses):
        return
    spacer = overall - sum(value for value in thicknesses if value is not None)
    if spacer <= 0:
        return
    item.spacer_thickness = f"{round(spacer, 4)} inch"


def _apply_glass_type_scope(item: RFQItem) -> None:
    if item.glass_type == "monolithic":
        item.TK1 = item.HT1 = item.TT1 = None
        item.TK2 = item.HT2 = item.TT2 = None
        item.TK3 = item.HT3 = item.TT3 = None
        item.spacer_material = item.spacer_thickness = None
        item.gas_fill = None
        item.interlayer_material = item.interlayer_thickness = None
        item.laminate_lite = None
        item.airspace = None
        item.overall_thickness = None
        item.interlayer = None
        item.lite_details = []
    elif item.glass_type == "laminated":
        item.TK3 = item.HT3 = item.TT3 = None
        item.spacer_material = item.spacer_thickness = None
        item.gas_fill = None
        item.laminate_lite = None
        item.airspace = None
        item.overall_thickness = None
        item.lite_details = []
    elif item.glass_type == "insulated":
        item.TK3 = item.HT3 = item.TT3 = None
        item.interlayer_material = item.interlayer_thickness = None
        item.laminate_lite = None
    elif item.glass_type == "laminated-insulated":
        item.lite_details = []


def _apply_no_guess_guards(item: RFQItem, raw: Mapping[str, Any]) -> None:
    text = _raw_text(raw).lower()
    notes = (item.notes or "").lower()
    _clear_defaulted_spec_fields(item)

    if item.glass_type == "monolithic":
        if any(
            phrase in notes
            for phrase in (
                "tk should be confirmed",
                "thickness should be confirmed",
                "thickness is assumed",
                "standard door lite thickness is assumed",
            )
        ):
            item.TK = None
        if any(
            phrase in notes
            for phrase in (
                "ht defaulted",
                "heat treatment defaulted",
                "defaulted to annealed",
                "no heat treatment specified",
                "no heat treatment stated",
                "heat treatment not explicitly stated",
                "ht not explicitly stated",
                "heat treatment not stated",
                "heat treatment not specified",
                "tempered assumed",
            )
        ):
            item.HT = None
        if any(
            phrase in notes
            for phrase in (
                "tt assumed",
                "glass type not explicitly stated",
                "assumed clear",
                "color not explicitly stated",
            )
        ):
            item.TT = None
            item.color = None

    if item.glass_type in {"laminated", "insulated", "laminated-insulated"}:
        _clear_unspecified_multi_lite_heat_treatments(item, notes)

    if item.glass_type == "laminated-insulated" and item.laminate_lite == "outboard":
        outboard_segment = _outboard_laminate_segment(text)
        if outboard_segment and _extract_ht(outboard_segment) is None:
            item.HT1 = None
            item.HT2 = None

    if _dimensions_are_area_context(raw.get("dimensions")):
        item.dimensions = None
        item.shape = "rectangle"


def _clear_unspecified_multi_lite_heat_treatments(item: RFQItem, notes: str) -> None:
    if any(
        phrase in notes
        for phrase in (
            "heat treatment not specified for either lite",
            "heat treatment not specified for both lites",
            "heat treatment not specified for all lites",
            "heat treatment not specified for any lite",
            "heat treatment not specified",
            "heat treatment not explicitly stated",
            "ht not explicitly stated",
        )
    ):
        item.HT1 = None
        item.HT2 = None
        if item.glass_type == "laminated-insulated":
            item.HT3 = None


def _clear_defaulted_spec_fields(item: RFQItem) -> None:
    allowed_default_fields = {"quantity", "shape"}
    spec_fields = (
        "TK",
        "HT",
        "TT",
        "color",
        "TK1",
        "HT1",
        "TT1",
        "TK2",
        "HT2",
        "TT2",
        "TK3",
        "HT3",
        "TT3",
        "spacer_material",
        "spacer_thickness",
        "gas_fill",
        "interlayer_material",
        "interlayer_thickness",
        "laminate_lite",
        "overall_thickness",
    )
    for field in spec_fields:
        if field in allowed_default_fields:
            continue
        if item.field_sources.get(field) == "default":
            setattr(item, field, None)


def _cleanup_tt_values(item: RFQItem) -> None:
    for field in ("TT", "TT1", "TT2", "TT3"):
        value = getattr(item, field)
        if _is_invalid_tt_value(value):
            setattr(item, field, None)

    if item.glass_type != "monolithic" or not item.TT:
        return

    if _is_monolithic_color_only_tt(item.TT) or _same_clean_value(item.TT, item.color):
        if not item.color:
            item.color = _canonical_color_value(item.TT)
            if item.field_sources.get("TT"):
                item.field_sources.setdefault("color", item.field_sources["TT"])
        item.TT = None


def _is_invalid_tt_value(value: object) -> bool:
    text = _normalized_label(value)
    if not text:
        return False
    return (
        text in CONSTRUCTION_TT_VALUES
        or text in SOURCE_TT_VALUES
        or text.startswith("attachment:")
    )


def _is_monolithic_color_only_tt(value: object) -> bool:
    return _normalized_label(value) in MONOLITHIC_COLOR_ONLY_TT_VALUES


def _same_clean_value(left: object, right: object) -> bool:
    left_text = _normalized_label(left)
    right_text = _normalized_label(right)
    return bool(left_text and right_text and left_text == right_text)


def _canonical_color_value(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    normalized = _normalized_label(text)
    if normalized == "gray":
        return "gray"
    if normalized == "grey":
        return "grey"
    return normalized or text


def _normalized_label(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    text = text.lower().replace("_", " ")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _outboard_laminate_segment(text: str) -> str | None:
    if "outboard" not in text:
        return None
    start = text.find("outboard")
    end_candidates = [
        idx
        for idx in (
            text.find("airspace", start),
            text.find("spacer", start),
            text.find("inboard", start),
        )
        if idx != -1
    ]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


def _dimensions_are_area_context(raw_dimensions: object) -> bool:
    if isinstance(raw_dimensions, Mapping):
        values = [
            raw_dimensions.get("raw"),
            raw_dimensions.get("width"),
            raw_dimensions.get("height"),
            raw_dimensions.get("diameter"),
        ]
    else:
        values = [raw_dimensions]
    return any(_is_area_text(value) for value in values)


def _is_area_text(value: object) -> bool:
    return bool(
        value is not None
        and re.search(
            r"\b(?:sq\.?\s*ft|sqft|square\s+feet|square\s+foot|square\s+ft|sf)\b",
            str(value).lower(),
        )
    )


def _cleanup_field_sources(item: RFQItem) -> None:
    if not item.field_sources:
        return
    cleaned: dict[str, str] = {}
    for field, source in item.field_sources.items():
        if field == "item":
            cleaned[field] = source
            continue
        if field == "dimensions":
            if item.dimensions is not None:
                cleaned[field] = source
            continue
        if field == "quantity":
            if item.quantity is not None:
                if source == "default" and not _quantity_was_defaulted(item):
                    cleaned[field] = item.source or "body"
                elif _quantity_was_defaulted(item):
                    cleaned[field] = "default"
                else:
                    cleaned[field] = source
            continue
        if not hasattr(item, field):
            continue
        value = getattr(item, field)
        if value not in (None, "", []):
            cleaned[field] = source
    item.field_sources = cleaned


def _normalize_spacer_thickness(raw: object) -> str | None:
    value = _clean(raw)
    if not value:
        return None
    measurement = normalize_measurement(value)
    if measurement is None:
        return None
    return _extract_thickness(value) or _format_measurement(value)


def _normalize_spacer_material(raw: object) -> str | None:
    value = _clean(raw)
    if not value:
        return None
    lower = value.lower()
    if "argon" in lower or "krypton" in lower:
        return None
    if lower in {"air", "airspace", "standard", "standard airspace"}:
        return None
    if not any(
        word in lower
        for word in (
            "spacer",
            "bar",
            "superspacer",
            "swisspacer",
            "aluminum",
            "aluminium",
            "stainless",
            "warm edge",
        )
    ):
        return None
    return value


def _normalize_gas_fill(raw: object) -> str | None:
    value = _clean(raw)
    if not value:
        return None
    lower = value.lower()
    if any(phrase in lower for phrase in ("no gas", "not stated", "not specified", "unspecified")):
        return None
    if "argon" in lower:
        return "argon"
    if "krypton" in lower:
        return "krypton"
    if re.search(r"\bair(?:\s+fill(?:ed)?)?\b", lower):
        return "air"
    return None


def _quantity_was_defaulted(item: RFQItem) -> bool:
    note = (item.notes or "").lower()
    return "quantity" in note and "default" in note


def _normalize_interlayer_thickness(raw: object) -> str | None:
    value = _clean(raw)
    if not value:
        return None
    _, thickness = _split_interlayer(value)
    if thickness:
        return thickness
    measurement = normalize_measurement(value)
    if measurement is None:
        return None
    return _format_measurement(value)


def _split_interlayer(raw: object) -> tuple[str | None, str | None]:
    text = _clean(raw)
    if not text:
        return None, None
    lower = text.lower()
    material = None
    for candidate in ("PVB", "SGP", "EVA"):
        if candidate.lower() in lower:
            material = candidate
            break
    if not material and "interlayer" in lower:
        material = "specified"

    thickness = None
    match = re.search(r"\d+\s*-\s*\d+/\d+|\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+(?:\.\d+)?\s*mm", lower)
    if match:
        thickness = _format_measurement(match.group(0))
    return material, thickness


def _normalize_laminate_lite(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.lower().replace("_", "-")
    if "out" in text or text in {"exterior", "outer", "outside"}:
        return "outboard"
    if "in" in text or text in {"interior", "inner", "inside"}:
        return "inboard"
    if text in {"lite 1", "first", "first lite"}:
        return "lite 1"
    if text in {"lite 2", "second", "second lite"}:
        return "lite 2"
    return raw


def _normalize_glass_type(raw: object) -> str:
    value = _clean(raw)
    if not value:
        return "unknown"
    key = value.lower().replace("_", "-")
    return GLASS_TYPE_ALIASES.get(key, "unknown")


def _normalize_ht(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.lower()
    if value in {"ft", "fully tempered", "temp", "tempered"}:
        return "tempered"
    if value in {"hs", "heat strengthened", "heat-strengthened"}:
        return "heat strengthened"
    if value in {"ann", "annealed"}:
        return "annealed"
    return raw


def _normalize_lite_details(raw: object) -> list[dict[str, Any]]:
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
            body = _clean(entry.get("body"))
            attachment = _clean(entry.get("attachment"))
            source = _clean(entry.get("source"))
            if _is_same_body_correction(body=body, attachment=attachment, source=source):
                continue
            conflicts.append(
                Conflict(
                    field=field,
                    body=body,
                    attachment=attachment,
                    source=source,
                )
            )
    return conflicts


def _is_same_body_correction(
    body: str | None,
    attachment: str | None,
    source: str | None,
) -> bool:
    if attachment:
        return False
    text = " ".join(part for part in (body, source) if part).lower()
    if "attachment" in text:
        return False
    return bool(source == "body" and any(word in text for word in ("correct", "superseded", "changed")))


def _raw_reason_requires_review(
    reason: str,
    items: list[RFQItem],
    missing: list[str],
    conflicts: list[Conflict],
) -> bool:
    if missing or conflicts or not items:
        return True
    text = reason.lower()
    return any(
        phrase in text
        for phrase in (
            "ambiguous",
            "unresolved",
            "tbd",
            "unconfirmed",
            "confirm",
            "clarification",
            "not specified",
            "not provided",
            "missing",
            "incomplete",
            "cannot",
            "can't",
            "unclear",
            "conflict",
            "not final",
            "not attached",
            "approximate",
            "roughly",
            "give or take",
            "prior job",
            "historical job",
        )
    )


def _strip_generated_missing_fields_sentence(reason: str | None) -> str | None:
    if not reason:
        return None
    cleaned = re.sub(
        r"\s*One or more items are missing required fields:[^.]*\.",
        "",
        reason,
    ).strip()
    return cleaned or None


def _is_ignorable_review_reason(
    reason: str,
    items: list[RFQItem],
    conflicts: list[Conflict],
) -> bool:
    if conflicts or any(item.missing_fields for item in items):
        return False
    text = reason.lower()
    if "mirror" in text and "heat treatment" in text:
        return True
    if "quantity" in text and "default" in text and all(item.quantity == 1 for item in items):
        return True
    if "tt" in text and "bronze" in text and "color" in text:
        return True
    if "rush order" in text and "missing" not in text and "ambiguous" not in text:
        return True
    if "mixed unit" in text and "missing" not in text and "ambiguous" not in text:
        return True
    if "no conflicts" in text and "missing" not in text and "ambiguous" not in text:
        return True
    if "no modifications" in text and "missing" not in text and "ambiguous" not in text:
        return True
    if "all specs are clear" in text:
        return True
    if (
        "follow-up" in text
        and "no new item details" in text
        and "missing" not in text
        and "ambiguous" not in text
        and "not specified" not in text
    ):
        return True
    if (
        "rfq extracted from message 1" in text
        and "missing" not in text
        and "ambiguous" not in text
        and "not specified" not in text
    ):
        return True
    return False


def _is_mirror(item: RFQItem) -> bool:
    text = " ".join(part for part in (item.TT, item.mark, item.edge_work) if part).lower()
    return "mirror" in text


def _mentions_circle(text: object) -> bool:
    lower = str(text or "").lower()
    return any(word in lower for word in ("circle", "circular", "round", "diameter", "radius"))


def _mentions_square(text: object) -> bool:
    lower = str(text or "").lower()
    return "square" in lower or re.search(r"\bsq\.?\b", lower) is not None


def _dimension_text(raw_dimensions: object) -> str | None:
    if isinstance(raw_dimensions, Mapping):
        parts = [
            _clean(raw_dimensions.get("shape")),
            _clean(raw_dimensions.get("raw")),
            _clean(raw_dimensions.get("diameter")),
            _clean(raw_dimensions.get("radius")),
        ]
        return " ".join(part for part in parts if part) or None
    return _clean(raw_dimensions)


def _raw_text(raw: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "construction",
        "glass_construction",
        "description",
        "notes",
        "TK",
        "thickness",
        "interlayer",
        "spacer",
        "airspace",
        "overall_thickness",
        "gas",
        "gas_fill",
    ):
        value = raw.get(key)
        if value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _looks_like_interlayer(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in ("pvb", "sgp", "eva", "interlayer")) or bool(
        re.search(r"\.\d{2,3}", lower)
    )


def _extract_thickness(text: str) -> str | None:
    matches = list(
        re.finditer(
        r"\d+\s*-\s*\d+/\d+\s*\"?|\d+\s+\d+/\d+\s*\"?|\d+/\d+\s*\"?|\d+(?:\.\d+)?\s*mm|\d*\.\d+\s*\"?|\d+(?:\.\d+)?\s*\"",
        text.lower(),
        )
    )
    if not matches:
        return None
    return _format_measurement(matches[-1].group(0))


def _extract_ht(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\b(temp|tempered|fully tempered|ft)\b", lower):
        return "tempered"
    if re.search(r"\b(hs|heat[- ]strengthened)\b", lower):
        return "heat strengthened"
    if re.search(r"\b(ann|annealed)\b", lower):
        return "annealed"
    return None


def _extract_tt(text: str) -> str | None:
    return _infer_tt_from_text(text)


def _extract_spacer_material(text: str) -> str | None:
    lower = text.lower()
    for pattern in (
        r"\b(black|silver|gray|grey|bronze|white|warm edge|stainless|aluminum|aluminium)\s+(?:spacer|bar)\b",
        r"\b(superspacer|swisspacer)\b",
    ):
        match = re.search(pattern, lower)
        if match:
            return match.group(0)
    return None


def _extract_gas_fill(text: str) -> str | None:
    return _normalize_gas_fill(text)


def _infer_laminate_lite(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\boutboard\b[^.]{0,80}\blaminat", lower) or re.search(
        r"\blaminat[^.]{0,80}\boutboard\b", lower
    ):
        return "outboard"
    if re.search(r"\binboard\b[^.]{0,80}\blaminat", lower) or re.search(
        r"\blaminat[^.]{0,80}\binboard\b", lower
    ):
        return "inboard"
    return None


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


def _format_measurement(value: object) -> str:
    text = str(value).strip()
    if not text:
        return text
    if re.search(r"mm\b|cm\b|inch|in\b|ft\b|feet|foot|\"|'", text, re.I):
        return text
    if re.fullmatch(r"\d*\.\d+|\d+/\d+|\d+\s*-\s*\d+/\d+|\d+\s+\d+/\d+", text):
        return f'{text}"'
    return text


def _append_note(existing: str | None, note: str) -> str:
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing} {note}"


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
