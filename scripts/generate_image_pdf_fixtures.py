from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "fixtures" / "attachments"
PAGE_SIZE = (2550, 3300)


QUOTES = [
    {
        "filename": "image_rfq_monolithic.pdf",
        "rfq": "IMG-MONO-001",
        "project": "Redwood Lobby",
        "due": "August 28, 2026",
        "items": [
            {
                "mark": "M-101",
                "quantity": "4",
                "size": "48 in x 96 in",
                "glass": "Monolithic - 1/2 in clear tempered",
                "fabrication": "Flat polish all edges",
            },
            {
                "mark": "M-102",
                "quantity": "2",
                "size": "30 in x 30 in",
                "glass": "Monolithic - 1/4 in low-iron tempered",
                "fabrication": "Two holes, 1 in diameter",
            },
        ],
        "notes": "Quote each mark separately. Confirm lead time with pricing.",
    },
    {
        "filename": "image_rfq_insulated.pdf",
        "rfq": "IMG-IGU-002",
        "project": "Harbor Office",
        "due": "August 28, 2026",
        "items": [
            {
                "mark": "I-201",
                "quantity": "3",
                "size": "36 in x 72 in",
                "glass": (
                    "Insulated unit - 1/4 in clear tempered / 1/2 in black "
                    "aluminum spacer with argon / 1/4 in clear tempered"
                ),
                "fabrication": "Seamed edges; rectangular unit",
            },
        ],
        "notes": "Provide unit pricing and current production lead time.",
    },
    {
        "filename": "image_rfq_laminated_review.pdf",
        "rfq": "IMG-LAM-003",
        "project": "Civic Stair Guard",
        "due": "August 29, 2026",
        "items": [
            {
                "mark": "L-301",
                "quantity": "1",
                "size": "60 in x 120 in",
                "glass": (
                    "Laminated - 1/4 in clear heat strengthened + 0.060 in PVB "
                    "+ 1/4 in clear; second-lite heat treatment to be confirmed"
                ),
                "fabrication": "Flat polish all edges",
            },
        ],
        "notes": "Do not assume the second-lite heat treatment. Flag it for review.",
    },
]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for quote in QUOTES:
        output = OUTPUT_DIR / quote["filename"]
        _draw_quote(quote).save(output, "PDF", resolution=300.0)
        print(output.relative_to(PROJECT_ROOT))
    return 0


def _draw_quote(quote: dict) -> Image.Image:
    image = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(image)
    regular = _font(42)
    small = _font(34)
    medium = _font(48, bold=True)
    title = _font(78, bold=True)
    navy = "#17324d"
    teal = "#147d78"
    line = "#c8d4df"
    soft = "#f3f7fa"

    draw.rectangle((0, 0, PAGE_SIZE[0], 250), fill=navy)
    draw.text((150, 78), "CLEARVIEW ARCHITECTURAL GLASS", font=medium, fill="white")
    draw.text((150, 350), "REQUEST FOR QUOTATION", font=title, fill=navy)
    draw.text((150, 480), f"RFQ: {quote['rfq']}", font=medium, fill=teal)

    metadata = [
        ("Project", quote["project"]),
        ("Quote due", quote["due"]),
        ("Prepared for", "Glass Fabrication Sales Team"),
    ]
    y = 620
    for label, value in metadata:
        draw.text((150, y), f"{label}:", font=small, fill="#526477")
        draw.text((430, y), value, font=small, fill="#17212b")
        y += 62

    y = 880
    for index, item in enumerate(quote["items"], start=1):
        box_height = 720 if len(item["glass"]) > 80 else 620
        draw.rounded_rectangle(
            (150, y, 2400, y + box_height),
            radius=18,
            fill=soft,
            outline=line,
            width=4,
        )
        draw.rectangle((150, y, 2400, y + 100), fill=teal)
        draw.text(
            (200, y + 24),
            f"ITEM {index} - MARK {item['mark']}",
            font=medium,
            fill="white",
        )
        current = y + 145
        current = _field(draw, "Quantity", item["quantity"], current, regular)
        current = _field(draw, "Size", item["size"], current, regular)
        current = _wrapped_field(draw, "Glass", item["glass"], current, regular)
        _wrapped_field(draw, "Fabrication", item["fabrication"], current, regular)
        y += box_height + 90

    notes_top = min(y, 2830)
    draw.line((150, notes_top, 2400, notes_top), fill=line, width=4)
    draw.text((150, notes_top + 55), "NOTES", font=medium, fill=navy)
    _wrapped_text(draw, quote["notes"], (150, notes_top + 135), regular, 82, "#17212b")
    draw.text(
        (150, 3160),
        "Synthetic image-only RFQ fixture for extraction validation",
        font=small,
        fill="#667788",
    )
    return image


def _field(draw, label: str, value: str, y: int, font) -> int:
    draw.text((210, y), f"{label}:", font=font, fill="#526477")
    draw.text((520, y), value, font=font, fill="#17212b")
    return y + 90


def _wrapped_field(draw, label: str, value: str, y: int, font) -> int:
    draw.text((210, y), f"{label}:", font=font, fill="#526477")
    lines = _wrap(value, 66)
    for index, line in enumerate(lines):
        draw.text((520, y + index * 62), line, font=font, fill="#17212b")
    return y + max(90, len(lines) * 62 + 28)


def _wrapped_text(draw, value: str, position: tuple[int, int], font, width: int, fill: str) -> None:
    x, y = position
    for index, line in enumerate(_wrap(value, width)):
        draw.text((x, y + index * 58), line, font=font, fill=fill)


def _wrap(value: str, width: int) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _font(size: int, bold: bool = False):
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


if __name__ == "__main__":
    raise SystemExit(main())
