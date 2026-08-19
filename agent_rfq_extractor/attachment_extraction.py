from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from io import BytesIO, StringIO
from statistics import fmean
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pdfplumber
from PIL import Image, ImageOps, UnidentifiedImageError


OCR_REVIEW_THRESHOLD = 0.90
DEFAULT_OCR_DPI = 300
DEFAULT_MAX_OCR_PAGES = 20
DEFAULT_MAX_IMAGE_PIXELS = 25_000_000
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")


@dataclass(frozen=True)
class AttachmentExtraction:
    text: str = ""
    error: str | None = None
    extraction_method: str | None = None
    ocr_used: bool = False
    ocr_confidence: float | None = None
    page_count: int | None = None
    ocr_page_count: int = 0
    review_required: bool = False
    review_reason: str | None = None


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None
    word_count: int


def extract_attachment(
    filename: str,
    mime_type: str | None,
    raw_bytes: bytes,
) -> AttachmentExtraction:
    lower = filename.lower()
    ocr_candidate = (
        mime_type == "application/pdf"
        or lower.endswith(".pdf")
        or (mime_type or "").startswith("image/")
        or lower.endswith(IMAGE_EXTENSIONS)
    )
    try:
        if mime_type == "application/pdf" or lower.endswith(".pdf"):
            return _extract_pdf(raw_bytes)
        if lower.endswith(".docx"):
            return AttachmentExtraction(
                text=docx_text(raw_bytes),
                extraction_method="text",
            )
        if (mime_type or "").startswith("text/") or lower.endswith((".txt", ".csv", ".tsv")):
            return AttachmentExtraction(
                text=raw_bytes.decode("utf-8", errors="replace").strip(),
                extraction_method="text",
            )
        if (mime_type or "").startswith("image/") or lower.endswith(IMAGE_EXTENSIONS):
            return _extract_image(raw_bytes)
        return AttachmentExtraction(
            error=f"Unsupported attachment type: {mime_type or lower}"
        )
    except Exception as exc:  # pragma: no cover - final guard for malformed external files
        return AttachmentExtraction(
            error=f"{type(exc).__name__}: {exc}",
            extraction_method="ocr" if ocr_candidate else None,
            review_required=ocr_candidate,
            review_reason=(
                "The image-based attachment could not be processed; verify it manually."
                if ocr_candidate
                else None
            ),
        )


def extract_attachment_text(
    filename: str,
    mime_type: str | None,
    raw_bytes: bytes,
) -> tuple[str, str | None]:
    result = extract_attachment(filename, mime_type, raw_bytes)
    return result.text, result.error


def docx_text(raw_bytes: bytes) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(BytesIO(raw_bytes)) as docx:
        root = ET.fromstring(docx.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        parts = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
        if parts:
            paragraphs.append("".join(parts))
    return "\n".join(paragraphs).strip()


def _extract_pdf(raw_bytes: bytes) -> AttachmentExtraction:
    native_pages: list[tuple[int, str]] = []
    ocr_pages: list[tuple[int, str]] = []
    confidences: list[tuple[float, int]] = []
    errors: list[str] = []
    ocr_attempt_count = 0
    max_pages = _positive_int_env("RFQ_OCR_MAX_PAGES", DEFAULT_MAX_OCR_PAGES)

    with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
        page_count = len(pdf.pages)
        for index, page in enumerate(pdf.pages, start=1):
            native_text = (page.extract_text() or "").strip()
            if not _page_needs_ocr(page, native_text):
                if native_text:
                    native_pages.append((index, native_text))
                continue

            if ocr_attempt_count >= max_pages:
                errors.append(
                    f"OCR page limit reached ({max_pages}); page {index} was not processed."
                )
                continue

            ocr_attempt_count += 1
            try:
                image = page.to_image(
                    resolution=_positive_int_env("RFQ_OCR_DPI", DEFAULT_OCR_DPI),
                    antialias=True,
                ).original
                ocr = _ocr_image(image)
            except Exception as exc:
                errors.append(f"OCR failed on page {index}: {type(exc).__name__}: {exc}")
                continue

            if ocr.text:
                ocr_pages.append((index, ocr.text))
                if ocr.confidence is not None:
                    confidences.append((ocr.confidence, max(ocr.word_count, 1)))
            else:
                errors.append(f"OCR found no usable text on page {index}.")

    text = _combine_pdf_text(native_pages, ocr_pages, page_count)
    confidence = _weighted_confidence(confidences)
    review_reason = (
        _ocr_review_reason(confidence, errors, len(ocr_pages))
        if ocr_attempt_count or not native_pages
        else None
    )
    method = _pdf_method(native_pages, ocr_pages, ocr_attempt_count)
    return AttachmentExtraction(
        text=text,
        error=" ".join(errors) or None,
        extraction_method=method,
        ocr_used=bool(ocr_pages),
        ocr_confidence=confidence,
        page_count=page_count,
        ocr_page_count=ocr_attempt_count,
        review_required=bool(review_reason),
        review_reason=review_reason,
    )


def _extract_image(raw_bytes: bytes) -> AttachmentExtraction:
    try:
        with Image.open(BytesIO(raw_bytes)) as source:
            image = source.copy()
    except (UnidentifiedImageError, OSError) as exc:
        return AttachmentExtraction(
            error=f"UnidentifiedImageError: {exc}",
            extraction_method="ocr",
            page_count=1,
            review_required=True,
            review_reason="The image attachment could not be decoded for OCR.",
        )

    try:
        result = _ocr_image(image)
    except Exception as exc:
        return AttachmentExtraction(
            error=f"OCR failed: {type(exc).__name__}: {exc}",
            extraction_method="ocr",
            page_count=1,
            review_required=True,
            review_reason="OCR failed for an image attachment; verify the source manually.",
        )

    review_reason = _ocr_review_reason(result.confidence, [], 1 if result.text else 0)
    return AttachmentExtraction(
        text=result.text,
        extraction_method="ocr",
        ocr_used=bool(result.text),
        ocr_confidence=result.confidence,
        page_count=1,
        ocr_page_count=1 if result.text else 0,
        review_required=bool(review_reason),
        review_reason=review_reason,
        error=None if result.text else "OCR found no usable text in the image.",
    )


def _page_needs_ocr(page, native_text: str) -> bool:
    if not native_text:
        return True
    alphanumeric_count = len(re.sub(r"[^A-Za-z0-9]", "", native_text))
    images = getattr(page, "images", []) or []
    return bool(images and alphanumeric_count < 20)


def _ocr_image(image: Image.Image) -> OCRResult:
    if not _boolean_env("RFQ_OCR_ENABLED", True):
        raise RuntimeError("OCR is disabled by RFQ_OCR_ENABLED")
    executable = shutil.which(os.getenv("TESSERACT_CMD", "tesseract"))
    if not executable:
        raise RuntimeError("Tesseract executable was not found")

    prepared = _prepare_image(image)
    buffer = BytesIO()
    prepared.save(buffer, format="PNG", optimize=True)
    command = [
        executable,
        "stdin",
        "stdout",
        "-l",
        os.getenv("RFQ_OCR_LANGUAGE", "eng"),
        "--psm",
        os.getenv("RFQ_OCR_PAGE_SEGMENTATION", "6"),
        "tsv",
    ]
    completed = subprocess.run(
        command,
        input=buffer.getvalue(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=float(os.getenv("RFQ_OCR_TIMEOUT_SECONDS", "60")),
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Tesseract exited with code {completed.returncode}")
    return _parse_tesseract_tsv(completed.stdout.decode("utf-8", errors="replace"))


def _prepare_image(image: Image.Image) -> Image.Image:
    prepared = ImageOps.exif_transpose(image)
    prepared = ImageOps.autocontrast(ImageOps.grayscale(prepared))
    max_pixels = _positive_int_env("RFQ_OCR_MAX_IMAGE_PIXELS", DEFAULT_MAX_IMAGE_PIXELS)
    if prepared.width * prepared.height > max_pixels:
        scale = (max_pixels / (prepared.width * prepared.height)) ** 0.5
        prepared = prepared.resize(
            (max(1, int(prepared.width * scale)), max(1, int(prepared.height * scale))),
            Image.Resampling.LANCZOS,
        )
    elif prepared.width < 1600:
        scale = min(2.0, 1600 / max(prepared.width, 1))
        prepared = prepared.resize(
            (int(prepared.width * scale), int(prepared.height * scale)),
            Image.Resampling.LANCZOS,
        )
    return prepared


def _parse_tesseract_tsv(raw_tsv: str) -> OCRResult:
    lines: dict[tuple[str, str, str, str], list[str]] = {}
    confidences: list[float] = []
    critical_confidences: list[float] = []
    for row in csv.DictReader(StringIO(raw_tsv), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row.get("conf") or -1)
        except ValueError:
            confidence = -1
        key = tuple(row.get(field) or "0" for field in ("page_num", "block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(text)
        if confidence >= 0:
            confidences.append(confidence)
            if any(char.isdigit() for char in text) or any(char in text for char in ('/', '"')):
                critical_confidences.append(confidence)

    text = "\n".join(" ".join(words) for words in lines.values()).strip()
    if not confidences:
        confidence = None
    else:
        overall = fmean(confidences)
        critical = fmean(critical_confidences) if critical_confidences else overall
        confidence = round(min(overall, critical) / 100, 3)
    return OCRResult(text=text, confidence=confidence, word_count=len(confidences))


def _combine_pdf_text(
    native_pages: list[tuple[int, str]],
    ocr_pages: list[tuple[int, str]],
    page_count: int,
) -> str:
    pages = [(number, "text", text) for number, text in native_pages]
    pages.extend((number, "OCR", text) for number, text in ocr_pages)
    pages.sort(key=lambda value: value[0])
    if not pages:
        return ""
    if not ocr_pages:
        return "\n".join(text for _, _, text in pages).strip()
    return "\n\n".join(
        f"[Page {number} - {method}]\n{text}"
        for number, method, text in pages
        if text
    ).strip()


def _pdf_method(
    native_pages: list[tuple[int, str]],
    ocr_pages: list[tuple[int, str]],
    ocr_attempt_count: int,
) -> str | None:
    if native_pages and ocr_attempt_count:
        return "text+ocr"
    if ocr_attempt_count:
        return "ocr"
    if native_pages:
        return "text"
    return None


def _weighted_confidence(values: list[tuple[float, int]]) -> float | None:
    if not values:
        return None
    total_weight = sum(weight for _, weight in values)
    return round(sum(score * weight for score, weight in values) / total_weight, 3)


def _ocr_review_reason(
    confidence: float | None,
    errors: list[str],
    ocr_page_count: int,
) -> str | None:
    if errors:
        return "OCR did not process every image page reliably; verify the attachment manually."
    if ocr_page_count < 1:
        return "OCR found no usable text; verify the attachment manually."
    threshold = float(os.getenv("RFQ_OCR_REVIEW_THRESHOLD", str(OCR_REVIEW_THRESHOLD)))
    if confidence is None or confidence < threshold:
        value = "unknown" if confidence is None else f"{confidence:.1%}"
        return f"OCR confidence is {value}, below the {threshold:.0%} review threshold."
    return None


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _boolean_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}
