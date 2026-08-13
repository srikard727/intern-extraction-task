from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_rfq_extractor.agents.base import AgentContext, AgentResult
from agent_rfq_extractor.models import Dimensions, EmailRecord, RFQItem
from database.storage import ExtractionStore
from scripts.import_sqlite_results import copy_results


class ImportResultsTests(unittest.TestCase):
    def test_copy_preserves_records_sources_and_agent_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = ExtractionStore(root / "source.db")
            target = ExtractionStore(root / "target.db")
            output = root / "target.json"
            try:
                record = _record()
                source.upsert_record(record)
                source.record_agent_run(_run(record))

                counts = copy_results(source, target, output, replace=True)

                self.assertEqual(counts, {"emails": 1, "items": 1, "agent_runs": 1})
                self.assertEqual(target.get_email("email-001")["status"], "completed")
                sources = target.list_item_sources("email-001")
                self.assertEqual(sources[0]["field_sources"]["TK"], "body")
                self.assertEqual(target.list_agent_runs()[0]["model"], "claude-opus-4-8")
                self.assertTrue(output.exists())
            finally:
                target.close()
                source.close()


def _record() -> EmailRecord:
    return EmailRecord(
        email_id="email-001",
        conv_id="fixture-conversation:001",
        from_email="buyer@example.com",
        to_email="sales@example.com",
        subject="RFQ",
        body_text='Quote 24" x 36" clear tempered.',
        emailbody_variant="plain",
        received_at="2026-08-12T10:00:00+00:00",
        has_attachments=False,
        extracted_at="2026-08-12T10:00:01+00:00",
        status="completed",
        items=[
            RFQItem(
                dimensions=Dimensions(width=24, height=36),
                quantity=1,
                glass_type="monolithic",
                TK='1/4"',
                HT="tempered",
                TT="clear",
                field_sources={
                    "dimensions": "body",
                    "quantity": "default",
                    "glass_type": "body",
                    "TK": "body",
                    "HT": "body",
                    "TT": "body",
                },
            )
        ],
        review=None,
        attachments=[],
        llm_model="claude-opus-4-8",
    )


def _run(record: EmailRecord) -> AgentResult[EmailRecord]:
    return AgentResult[EmailRecord](
        agent_name="extractor",
        status="completed",
        output=record,
        started_at="2026-08-12T10:00:00+00:00",
        finished_at="2026-08-12T10:00:01+00:00",
        duration_ms=1000,
        context=AgentContext(
            run_id="run-001",
            metadata={"email_id": "email-001"},
        ),
        metadata={
            "email_id": "email-001",
            "conv_id": "fixture-conversation:001",
            "item_count": 1,
            "review_required": False,
            "llm_model": "claude-opus-4-8",
        },
    )


if __name__ == "__main__":
    unittest.main()
