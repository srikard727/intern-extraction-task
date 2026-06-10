from __future__ import annotations

import re
from fractions import Fraction


UNICODE_FRACTIONS = {
    "¼": " 1/4",
    "½": " 1/2",
    "¾": " 3/4",
    "⅛": " 1/8",
    "⅜": " 3/8",
    "⅝": " 5/8",
    "⅞": " 7/8",
}

WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
}

WORD_FRACTIONS = {
    "quarter": 0.25,
    "one quarter": 0.25,
    "half": 0.5,
    "one half": 0.5,
    "three eighths": 0.375,
    "three-eighths": 0.375,
    "five eighths": 0.625,
    "five-eighths": 0.625,
}


def normalize_measurement(value: object, default_unit: str = "inch") -> float | None:
    """Normalize a linear measurement to decimal inches."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return round(float(value), 4)

    text = str(value).strip().lower()
    if not text:
        return None

    text = _replace_unicode_fractions(text)
    unit = _detect_unit(text, default_unit)
    number = _parse_number(text)
    if number is None:
        return None

    if unit == "mm":
        number = number / 25.4
    elif unit == "cm":
        number = number / 2.54
    elif unit == "ft":
        number = number * 12
    return round(number, 4)


def normalize_quantity(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)

    text = str(value).strip().lower()
    if not text:
        return None
    if re.search(r"\b(around|roughly|about|between|several|somewhere|var(y|ies)|approx)\b", text):
        return None

    match = re.search(r"\b(?:qty|quantity|x)?\s*(\d+)\b", text)
    if match:
        qty = int(match.group(1))
        return qty if qty > 0 else None

    for word, qty in WORD_NUMBERS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            return qty
    return None


def split_dimension_pair(value: str) -> tuple[str, str] | None:
    text = _replace_unicode_fractions(value.lower())
    text = re.sub(r"\bby\b", "x", text)
    text = text.replace("*", "x").replace("×", "x")
    parts = [part.strip(" ,") for part in re.split(r"\s+x\s+", text, maxsplit=1)]
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    return None


def parse_measurements_in_text(value: object) -> list[float]:
    if value is None:
        return []
    text = _replace_unicode_fractions(str(value).lower())
    unit = _detect_unit(text, "inch")
    measurements: list[float] = []
    for match in re.finditer(r"\d+\s*-\s*\d+/\d+|\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+", text):
        number = _parse_number(match.group(0))
        if number is None:
            continue
        if unit == "mm":
            number = number / 25.4
        elif unit == "cm":
            number = number / 2.54
        elif unit == "ft":
            number = number * 12
        measurements.append(round(number, 4))
    return measurements


def _replace_unicode_fractions(text: str) -> str:
    for frac, repl in UNICODE_FRACTIONS.items():
        text = text.replace(frac, repl)
    return text


def _detect_unit(text: str, default_unit: str) -> str:
    if re.search(r"\d\s*mm\b|\bmm\b|millimeter", text):
        return "mm"
    if re.search(r"\d\s*cm\b|\bcm\b|centimeter", text):
        return "cm"
    if re.search(r"\d\s*ft\b|\bft\b|feet|foot|'", text):
        return "ft"
    if re.search(r"\d\s*in\b|\bin\b|inch|inches|\"", text):
        return "inch"
    return default_unit


def _parse_number(text: str) -> float | None:
    cleaned = text.replace('"', " ").replace("'", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    for words, value in WORD_FRACTIONS.items():
        if words in cleaned:
            return value

    mixed_dash = re.search(r"(\d+)\s*-\s*(\d+/\d+)", cleaned)
    if mixed_dash:
        return float(int(mixed_dash.group(1)) + Fraction(mixed_dash.group(2)))

    mixed_space = re.search(r"(\d+)\s+(\d+/\d+)", cleaned)
    if mixed_space:
        return float(int(mixed_space.group(1)) + Fraction(mixed_space.group(2)))

    frac = re.search(r"(?<![\d.])(\d+/\d+)", cleaned)
    if frac:
        return float(Fraction(frac.group(1)))

    decimal = re.search(r"\d*\.\d+|\d+", cleaned)
    if decimal:
        return float(decimal.group(0))

    for word, value in WORD_NUMBERS.items():
        if re.search(rf"\b{re.escape(word)}\b", cleaned):
            return float(value)
    return None
