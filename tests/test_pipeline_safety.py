import tempfile
import unittest
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
