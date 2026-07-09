# Multi-Agent Framework

The RFQ extractor now runs through a reusable agent workflow instead of calling
the extractor graph directly.

## Core Pieces

- `BaseAgent`: common interface for one agent. Each agent implements
  `execute(payload, context)` and receives an `AgentContext`.
- `AgentResult`: standard result envelope with agent name, status, output,
  error, timing, context, and metadata.
- `AgentRegistry`: registers named agent factories and creates agents by name.
- `AgentWorkflow`: runs ordered `AgentWorkflowStep` objects. The output of one
  step becomes the input to the next step.
- `agent_runs`: SQLite execution log table. The workflow calls the persistence
  callback once per agent result.

## Current Workflow

```text
InboundEmail
  -> ExtractorAgent
  -> EmailRecord
```

`ExtractorAgent` is Agent 1. It wraps the existing LangGraph extraction flow:

```text
prepare -> extract -> normalize -> review -> assemble
                    \-> failure
```

## Adding A Future Agent

1. Create a class that inherits from `BaseAgent`.
2. Give it a unique `name`.
3. Implement `execute(payload, context)`.
4. Register it in `build_default_registry()`.
5. Add it to the workflow step list.

Example:

```python
class ReviewAgent(BaseAgent[EmailRecord, EmailRecord]):
    name = "review"

    def execute(self, payload: EmailRecord, context: AgentContext) -> EmailRecord:
        return payload
```

Then:

```python
workflow = AgentWorkflow(
    [
        AgentWorkflowStep(extractor_agent),
        AgentWorkflowStep(review_agent),
    ]
)
```

or through the registry:

```python
workflow = registry.create_workflow(["extractor", "review"])
```

## Stop Rules

By default, a workflow stops when an agent result has status `failed` or
`extraction_failed`. A `human_review_required` result is still a valid output
and can be passed to a future review agent.

## Run Context

Each agent run receives:

- a unique `run_id`
- the shared workflow id as `parent_run_id`
- workflow metadata such as step index, step count, and previous agent status
- email metadata such as `email_id`, `conv_id`, and model when available

This gives each future agent a consistent contract and gives SQLite enough data
to reconstruct what happened in a multi-agent run.
