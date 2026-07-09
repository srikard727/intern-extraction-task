import unittest
from datetime import datetime, timezone

from agent_rfq_extractor.agents import AgentContext, AgentRegistry, BaseAgent, ExtractorAgent
from agent_rfq_extractor.models import EmailRecord, InboundEmail


class EchoAgent(BaseAgent[str, str]):
    name = "echo"

    def execute(self, payload: str, context: AgentContext) -> str:
        context.metadata["seen"] = payload
        return payload


class FailureAgent(BaseAgent[str, str]):
    name = "failure"

    def execute(self, payload: str, context: AgentContext) -> str:
        raise ValueError("boom")


class FakeGraph:
    model = "fake-model"

    def process_email(self, email: InboundEmail) -> EmailRecord:
        return EmailRecord(
            email_id=email.email_id,
            conv_id=email.conv_id,
            from_email=email.from_email,
            to_email=email.to_email,
            subject=email.subject,
            body_text=email.body_text,
            emailbody_variant=email.emailbody_variant,
            received_at=email.received_at,
            has_attachments=email.has_attachments,
            attachments=[],
            extracted_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
            items=[],
            review=None,
            llm_model=self.model,
        )


class AgentTests(unittest.TestCase):
    def test_registry_creates_registered_agent(self):
        registry = AgentRegistry()
        registry.register(EchoAgent)

        agent = registry.create("echo")

        self.assertIsInstance(agent, EchoAgent)
        self.assertEqual(registry.names(), ["echo"])

    def test_base_agent_wraps_success_result(self):
        result = EchoAgent().run("hello")

        self.assertEqual(result.agent_name, "echo")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.require_output(), "hello")
        self.assertEqual(result.context.metadata["seen"], "hello")
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_base_agent_wraps_failure_result(self):
        result = FailureAgent().run("hello")

        self.assertEqual(result.status, "failed")
        self.assertIsNone(result.output)
        self.assertIn("ValueError: boom", result.error or "")

    def test_extractor_agent_wraps_graph_contract(self):
        email = InboundEmail(
            email_id="fixture-001",
            conv_id="fixture-thread-001",
            subject="RFQ",
            body_text='1/4" clear tempered 12 x 24',
            has_attachments=False,
        )
        agent = ExtractorAgent(graph=FakeGraph())

        result = agent.run(email)

        record = result.require_output()
        self.assertEqual(result.agent_name, "extractor")
        self.assertEqual(result.status, "completed")
        self.assertEqual(record.email_id, "fixture-001")
        self.assertEqual(record.llm_model, "fake-model")
        self.assertEqual(result.context.metadata["email_id"], "fixture-001")
        self.assertEqual(result.metadata["item_count"], 0)


if __name__ == "__main__":
    unittest.main()
