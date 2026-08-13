# Architecture

The Glass RFQ Extraction System reads RFQ emails, extracts one structured glass
unit per requested item, stores searchable records, and exposes the results
through API and browser review views.

## Runtime Flow

```text
Gmail or fixture input
  -> RFQPipeline
  -> AgentWorkflow
  -> ExtractorAgent
  -> LangGraph extractor graph
  -> quality normalization and review rules
  -> SQLite/PostgreSQL + JSON export
  -> FastAPI JSON endpoints and /view UI
```

## Main Components

- `agent_rfq_extractor/gmail_client.py`: reads Gmail messages, visible HTML or
  plain bodies, chronological thread context, and text-capable attachments.
- `agent_rfq_extractor/pipeline.py`: owns input loading, workflow execution,
  persistence, and JSON export.
- `agent_rfq_extractor/agents/`: reusable agent base class, registry, workflow,
  and the registered `ExtractorAgent`.
- `agent_rfq_extractor/graph.py`: LangGraph extraction flow.
- `agent_rfq_extractor/quality.py`: deterministic normalization, required-field
  checks, human-review rules, and output cleanup.
- `database/storage.py`: SQLite persistence for emails, extracted items, and
  agent execution logs.
- `database/postgres.py`: PostgreSQL implementation for the same persistence
  contract.
- `agent_rfq_extractor/api.py`: FastAPI endpoints, Celery task endpoints, and
  lightweight HTML review UI.

## Agent Contract

The current workflow has one real agent:

```text
InboundEmail -> ExtractorAgent -> EmailRecord
```

`BaseAgent` wraps execution timing, status, errors, metadata, and the
`AgentResult` envelope. `AgentRegistry` registers named agent factories, and
`AgentWorkflow` runs agents in order. Each `AgentResult` is persisted to
`agent_runs` with agent name, status, model, timestamps, duration, email id,
review status, item count, error, metadata, and context.

The future multi-agent path is intentionally simple: add another `BaseAgent`
subclass, register it, and include it after `extractor` in the workflow.

## Persistence

SQLite is the default local store. PostgreSQL is enabled when `DATABASE_URL` is
set.

- `emails`: one stored message/RFQ result.
- `items`: one row per extracted glass unit.
- `agent_runs`: one row per agent execution.

The JSON export mirrors stored email records and keeps quote data under
`extraction.glass_type_groups`. Exported `glass_units` do not include internal
`field_sources` or raw source keys. Internal provenance is retained in the
`items` table and exposed through the source API and review UI.

## Attachment Scope

Supported attachment text extraction:

- text-layer PDFs
- TXT, CSV, and TSV files
- DOCX files

Image-only attachments and OCR are out of scope for this build.

## Human Review

The extractor does not guess required values. Missing or ambiguous required
fields mark the record as `human_review_required`. Required fields vary by glass
type. The authoritative matrix is `REQUIRED_FIELDS_BY_GLASS_TYPE` in
`models.py`, and `quality.py` uses that same definition for review decisions.
