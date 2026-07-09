import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_rfq_extractor.agents import (
    AgentContext,
    AgentResult,
    AgentWorkflow,
    AgentWorkflowStep,
    BaseAgent,
)
from agent_rfq_extractor.models import EmailRecord, InboundEmail
from agent_rfq_extractor.pipeline import RFQPipeline
from database.storage import ExtractionStore


class FailingExtractorAgent(BaseAgent[InboundEmail, EmailRecord]):
    name = "extractor"
    model = "fake-model"

    def execute(self, payload: InboundEmail, context: AgentContext) -> EmailRecord:
        raise ValueError("boom")


class AgentRunLoggingTests(unittest.TestCase):
    def test_store_records_agent_run_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ExtractionStore(Path(tmpdir) / "rfq.db")
            try:
                result = AgentResult[EmailRecord](
                    agent_name="extractor",
                    status="human_review_required",
                    output=_record(status="human_review_required"),
                    error=None,
                    started_at="2026-07-08T01:00:00+00:00",
                    finished_at="2026-07-08T01:00:01+00:00",
                    duration_ms=1000,
                    context=AgentContext(
                        run_id="run-001",
                        metadata={"email_id": "email-001", "model": "fake-model"},
                    ),
                    metadata={
                        "email_id": "email-001",
                        "conv_id": "thread-001",
                        "item_count": 0,
                        "review_required": True,
                        "llm_model": "fake-model",
                    },
                )

                store.record_agent_run(result)

                row = store.conn.execute(
                    "SELECT * FROM agent_runs WHERE run_id = ?", ("run-001",)
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["agent_name"], "extractor")
                self.assertEqual(row["status"], "human_review_required")
                self.assertEqual(row["model"], "fake-model")
                self.assertEqual(row["email_id"], "email-001")
                self.assertEqual(row["conv_id"], "thread-001")
                self.assertEqual(row["review_status"], "human_review_required")
                self.assertEqual(row["item_count"], 0)
                self.assertEqual(row["duration_ms"], 1000)
            finally:
                store.close()

    def test_pipeline_logs_agent_failure_before_raising(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ExtractionStore(Path(tmpdir) / "rfq.db")
            pipeline = RFQPipeline.__new__(RFQPipeline)
            pipeline.store = store
            pipeline.extractor_agent = FailingExtractorAgent()
            pipeline.agent_workflow = AgentWorkflow([AgentWorkflowStep(pipeline.extractor_agent)])
            try:
                with self.assertRaises(RuntimeError):
                    pipeline.process_email(
                        InboundEmail(
                            email_id="email-002",
                            conv_id="thread-002",
                            subject="RFQ",
                            body_text="bad input",
                            has_attachments=False,
                        )
                    )

                row = store.conn.execute(
                    "SELECT * FROM agent_runs WHERE email_id = ?", ("email-002",)
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["status"], "failed")
                self.assertEqual(row["email_id"], "email-002")
                self.assertEqual(row["error"], "ValueError: boom")
                self.assertIsNone(row["item_count"])
            finally:
                store.close()


def _record(status: str) -> EmailRecord:
    return EmailRecord(
        email_id="email-001",
        conv_id="thread-001",
        from_email="requester@example.com",
        to_email="sales@example.com",
        subject="RFQ",
        body_text="",
        emailbody_variant="plain",
        received_at=None,
        has_attachments=False,
        extracted_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        items=[],
        review=None,
        attachments=[],
        llm_model="fake-model",
    )


if __name__ == "__main__":
    unittest.main()
