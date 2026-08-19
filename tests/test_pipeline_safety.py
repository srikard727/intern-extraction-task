import tempfile
import unittest
import shutil
from pathlib import Path

from agent_rfq_extractor.pipeline import RFQPipeline, parse_fixture


class RecordingStore:
    def __init__(self):
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1


class PipelineSafetyTests(unittest.TestCase):
    def test_replace_existing_is_deferred_and_only_runs_once(self):
        pipeline = RFQPipeline.__new__(RFQPipeline)
        pipeline.store = RecordingStore()
        pipeline.replace_existing = True
        pipeline._run_prepared = False

        self.assertEqual(pipeline.store.clear_calls, 0)
        pipeline._prepare_run()
        pipeline._prepare_run()

        self.assertEqual(pipeline.store.clear_calls, 1)

    def test_attachment_demo_fixture_loads_real_text_attachment(self):
        emails = parse_fixture("fixtures/attachment_demo.txt")

        self.assertEqual(len(emails), 1)
        email = emails[0]
        self.assertTrue(email.has_attachments)
        self.assertEqual(len(email.attachments), 1)
        self.assertEqual(email.attachments[0].source, "attachment:glass_schedule.txt")
        self.assertIn("GL-A1", email.attachments[0].text)
        self.assertNotIn("Fixture-Attachment", email.body_text)

    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract is required for OCR fixture validation")
    def test_image_pdf_fixture_loads_real_ocr_attachments(self):
        emails = parse_fixture("fixtures/image_pdf_rfq_emails.txt")

        self.assertEqual(len(emails), 3)
        expected = [
            ("M-101", "48 in x 96 in", "image_rfq_monolithic.pdf"),
            ("I-201", "36 in x 72 in", "image_rfq_insulated.pdf"),
            ("L-301", "60 in x 120 in", "image_rfq_laminated_review.pdf"),
        ]
        for email, (mark, dimensions, filename) in zip(emails, expected, strict=True):
            self.assertTrue(email.has_attachments)
            self.assertNotIn("Fixture-Attachment", email.body_text)
            attachment = email.attachments[0]
            self.assertEqual(attachment.filename, filename)
            self.assertEqual(attachment.extraction_method, "ocr")
            self.assertTrue(attachment.ocr_used)
            self.assertGreaterEqual(attachment.ocr_confidence or 0, 0.90)
            self.assertFalse(attachment.review_required)
            self.assertIn(mark, attachment.text)
            self.assertIn(dimensions, attachment.text)

    def test_fixture_attachment_cannot_escape_fixture_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = Path(tmpdir) / "fixture.txt"
            fixture.write_text(
                "Email: 1\nFixture-Attachment: ../outside.txt\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "must stay inside"):
                parse_fixture(fixture)


if __name__ == "__main__":
    unittest.main()
