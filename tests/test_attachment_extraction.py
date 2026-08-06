import unittest
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

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

            def extract_text(self):
                return self.text

        class FakePdf:
            pages = [FakePage("Quote page 1"), FakePage("GL-1 insulated unit")]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        with patch("agent_rfq_extractor.gmail_client.pdfplumber.open", return_value=FakePdf()):
            text, error = _extract_attachment_text("quote.pdf", "application/pdf", b"%PDF-1.4")

        self.assertIsNone(error)
        self.assertEqual(text, "Quote page 1\nGL-1 insulated unit")

    def test_unsupported_image_attachment_stays_out_of_scope(self):
        text, error = _extract_attachment_text("photo.png", "image/png", b"\x89PNG")

        self.assertEqual(text, "")
        self.assertEqual(error, "Unsupported attachment type: image/png")

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
