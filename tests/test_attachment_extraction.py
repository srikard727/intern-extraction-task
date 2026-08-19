import unittest
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from agent_rfq_extractor.attachment_extraction import (
    OCRResult,
    _parse_tesseract_tsv,
    extract_attachment,
)
from agent_rfq_extractor.gmail_client import GmailClient, _docx_text, _extract_attachment_text


class AttachmentExtractionTests(unittest.TestCase):
    def test_text_attachment_extracts_utf8_text(self):
        text, error = _extract_attachment_text(
            "rfq.txt",
            "text/plain",
            b'Need 2 pcs 1/4" clear tempered 12 x 24',
        )

        self.assertIsNone(error)
        self.assertIn("clear tempered", text)

    def test_csv_attachment_extracts_text_by_extension(self):
        text, error = _extract_attachment_text(
            "glass_schedule.csv",
            "application/octet-stream",
            b"mark,width,height\nGL-1,12,24",
        )

        self.assertIsNone(error)
        self.assertIn("GL-1", text)

    def test_docx_attachment_extracts_paragraph_text(self):
        raw_bytes = _minimal_docx("RFQ package", '1/2" clear HS')

        self.assertEqual(_docx_text(raw_bytes), 'RFQ package\n1/2" clear HS')
        text, error = _extract_attachment_text("quote.docx", None, raw_bytes)

        self.assertIsNone(error)
        self.assertIn('1/2" clear HS', text)

    def test_pdf_attachment_uses_text_layer_reader(self):
        class FakePage:
            def __init__(self, text):
                self.text = text
                self.images = []

            def extract_text(self):
                return self.text

        class FakePdf:
            pages = [FakePage("Quote page 1"), FakePage("GL-1 insulated unit")]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        with patch("agent_rfq_extractor.attachment_extraction.pdfplumber.open", return_value=FakePdf()):
            result = extract_attachment("quote.pdf", "application/pdf", b"%PDF-1.4")

        self.assertIsNone(result.error)
        self.assertEqual(result.text, "Quote page 1\nGL-1 insulated unit")
        self.assertEqual(result.extraction_method, "text")
        self.assertFalse(result.review_required)

    def test_malformed_image_attachment_returns_explicit_error(self):
        text, error = _extract_attachment_text("photo.png", "image/png", b"\x89PNG")

        self.assertEqual(text, "")
        self.assertIn("UnidentifiedImageError", error)

    def test_image_only_pdf_uses_ocr_and_records_confidence(self):
        class FakePage:
            images = [{"name": "scan"}]

            def extract_text(self):
                return ""

            def to_image(self, resolution, antialias):
                self.render_options = (resolution, antialias)
                return SimpleNamespace(original=Image.new("RGB", (1200, 1600), "white"))

        class FakePdf:
            pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        with (
            patch("agent_rfq_extractor.attachment_extraction.pdfplumber.open", return_value=FakePdf()),
            patch(
                "agent_rfq_extractor.attachment_extraction._ocr_image",
                return_value=OCRResult(
                    text='M-101 QTY 4 48 in x 96 in 1/2 in clear tempered',
                    confidence=0.96,
                    word_count=12,
                ),
            ),
        ):
            result = extract_attachment("scan.pdf", "application/pdf", b"%PDF-1.4")

        self.assertEqual(result.extraction_method, "ocr")
        self.assertTrue(result.ocr_used)
        self.assertEqual(result.ocr_confidence, 0.96)
        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.ocr_page_count, 1)
        self.assertFalse(result.review_required)
        self.assertIn("[Page 1 - OCR]", result.text)
        self.assertIn("M-101", result.text)

    def test_low_confidence_image_ocr_requires_review(self):
        image = Image.new("RGB", (800, 600), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        with patch(
            "agent_rfq_extractor.attachment_extraction._ocr_image",
            return_value=OCRResult(text="M-1 48 x 96", confidence=0.72, word_count=4),
        ):
            result = extract_attachment("scan.png", "image/png", buffer.getvalue())

        self.assertTrue(result.review_required)
        self.assertIn("72.0%", result.review_reason)

    def test_tesseract_tsv_parser_keeps_lines_and_critical_confidence(self):
        raw = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t96\tM-101\n"
            "5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t94\tQTY\n"
            "5\t1\t1\t1\t1\t3\t0\t0\t1\t1\t88\t4\n"
            "5\t1\t1\t1\t2\t1\t0\t0\t1\t1\t93\tTempered\n"
        )

        result = _parse_tesseract_tsv(raw)

        self.assertEqual(result.text, "M-101 QTY 4\nTempered")
        self.assertEqual(result.word_count, 4)
        self.assertEqual(result.confidence, 0.92)

    def test_gmail_attachment_fetch_extracts_text_and_preview(self):
        raw_text = b"GL-1, 2 pcs, 1/4 clear tempered, 12 x 24"
        service = _fake_gmail_attachment_service("att-1", raw_text)
        client = object.__new__(GmailClient)
        client.service = service

        attachments = client._extract_attachments(
            "message-001",
            {
                "parts": [
                    {
                        "filename": "schedule.txt",
                        "mimeType": "text/plain",
                        "body": {"attachmentId": "att-1"},
                    }
                ]
            },
        )

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].filename, "schedule.txt")
        self.assertEqual(attachments[0].source, "attachment:schedule.txt")
        self.assertTrue(attachments[0].text_extracted)
        self.assertEqual(attachments[0].extraction_method, "text")
        self.assertIn("clear tempered", attachments[0].text)
        self.assertIn("GL-1", attachments[0].text_preview)


def _minimal_docx(*paragraphs: str) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
        + "</w:body></w:document>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as docx:
        docx.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _fake_gmail_attachment_service(attachment_id: str, raw_bytes: bytes):
    data = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")
    request = SimpleNamespace(execute=lambda: {"data": data})
    attachments = SimpleNamespace(
        get=lambda userId, messageId, id: request
        if (userId, messageId, id) == ("me", "message-001", attachment_id)
        else (_raise_assertion("unexpected attachment request"))
    )
    messages = SimpleNamespace(attachments=lambda: attachments)
    users = SimpleNamespace(messages=lambda: messages)
    return SimpleNamespace(users=lambda: users)


def _raise_assertion(message: str):
    raise AssertionError(message)


if __name__ == "__main__":
    unittest.main()
