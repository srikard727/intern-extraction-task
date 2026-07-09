import unittest

from agent_rfq_extractor.agents import (
    AgentContext,
    AgentRegistry,
    AgentWorkflow,
    AgentWorkflowStep,
    BaseAgent,
)


class PrefixAgent(BaseAgent[str, str]):
    name = "prefix"

    def execute(self, payload: str, context: AgentContext) -> str:
        return f"prefix:{payload}"


class SuffixAgent(BaseAgent[str, str]):
    name = "suffix"

    def execute(self, payload: str, context: AgentContext) -> str:
        return f"{payload}:suffix"


class BoomAgent(BaseAgent[str, str]):
    name = "boom"

    def execute(self, payload: str, context: AgentContext) -> str:
        raise ValueError("boom")


class AgentWorkflowTests(unittest.TestCase):
    def test_workflow_runs_agents_in_order(self):
        results = []
        workflow = AgentWorkflow(
            [
                AgentWorkflowStep(PrefixAgent()),
                AgentWorkflowStep(SuffixAgent()),
            ]
        )

        result = workflow.run(
            "glass",
            metadata={"email_id": "email-001"},
            on_result=results.append,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.require_output(), "prefix:glass:suffix")
        self.assertEqual([item.agent_name for item in results], ["prefix", "suffix"])
        self.assertEqual(workflow.agent_names, ["prefix", "suffix"])
        self.assertEqual({item.context.parent_run_id for item in results}, {result.workflow_id})
        self.assertEqual(results[0].context.metadata["workflow_step_index"], 1)
        self.assertEqual(results[1].context.metadata["workflow_step_index"], 2)
        self.assertEqual(results[1].context.metadata["previous_agent"], "prefix")
        self.assertEqual(results[1].context.metadata["email_id"], "email-001")

    def test_workflow_stops_on_failed_agent(self):
        workflow = AgentWorkflow(
            [
                AgentWorkflowStep(BoomAgent()),
                AgentWorkflowStep(SuffixAgent()),
            ]
        )

        result = workflow.run("glass")

        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0].agent_name, "boom")
        self.assertIsNone(result.output)
        with self.assertRaises(RuntimeError):
            result.require_output()

    def test_registry_can_create_workflow(self):
        registry = AgentRegistry()
        registry.register(PrefixAgent)
        registry.register(SuffixAgent)

        workflow = registry.create_workflow(["prefix", "suffix"])
        result = workflow.run("glass")

        self.assertEqual(workflow.agent_names, ["prefix", "suffix"])
        self.assertEqual(result.require_output(), "prefix:glass:suffix")


if __name__ == "__main__":
    unittest.main()
