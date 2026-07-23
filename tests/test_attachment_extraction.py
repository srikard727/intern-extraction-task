import unittest
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from agent_rfq_extractor.gmail_client import _docx_text, _extract_attachment_text


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


if __name__ == "__main__":
    unittest.main()
