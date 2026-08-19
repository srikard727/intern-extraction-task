# Requirement Traceability Matrix

Review date: August 19, 2026

This matrix maps every scheduled task to concrete repository evidence. `Verified`
means the implementation and its acceptance evidence pass. Typed image-only PDF
OCR was optional under the original MVP scope and is now included as a tested
enhancement; handwriting and drawing interpretation remain optional.

| ID | Requirement | Status | Evidence and remaining check |
|---|---|---|---|
| A1 | Glass type analysis and field identification | Verified | Central Pydantic item model, type-specific fields, prompt rules, and the 40-item acceptance oracle. |
| A2 | Mandatory vs optional fields by glass type | Verified | `REQUIRED_FIELDS_BY_GLASS_TYPE`, mirror exception, deterministic quality rules, and matrix tests. |
| A3 | Human Review business rules | Verified | Missing/ambiguous/conflicting/empty/failed cases route to review; approximate quantity defaults to 1; covered by quality tests and output audit. |
| A4 | Future agent architecture | Verified | Extractor is Agent 1 behind documented contracts; future registration is documented in `docs/multi_agent_framework.md`. |
| B1 | Multi-Agent Framework Design | Verified | `AgentWorkflow` executes registered agents in order and stops on failure. |
| B2 | Agent Base Class and Registry Design | Verified | `BaseAgent`, typed context/result contracts, `AgentRegistry`, and `ExtractorAgent` tests pass. |
| B3 | LangGraph Orchestrator Setup | Verified | Per-email `prepare -> extract -> normalize -> review -> assemble` graph with failure routing. |
| B4 | State Management and Agent Contracts | Verified | Pydantic graph state, email/item models, agent context/result metadata, and contract tests. |
| C1 | FastAPI Project Setup | Verified | Health, read, extraction, task, source, run-log, and HTML routes are implemented and tested. |
| C2 | PostgreSQL Setup and Schema Design | Verified | PostgreSQL schema/store, JSONB payloads, searchable columns, indexes, persistence, and live Compose check. |
| C3 | Redis Setup | Verified | Compose health check and live `PONG` validation. |
| C4 | Celery Queue Framework Setup | Verified | Fixture/Gmail tasks, status endpoint, eager tests, and live worker `pong`; concurrency capped at 2. |
| C5 | Docker Compose Setup | Verified | Four-service stack, health checks, localhost ports, persistent volumes, non-root app containers, and Gmail secret override. |
| D1 | Email data extraction | Verified | Gmail message/thread IDs, metadata, visible HTML, plain fallback, chronological context, and corrections are covered. Read-only live OAuth authentication also passed; the current 30-day RFQ query contained no matching messages. |
| D2 | Attachment data extraction | Verified plus stretch | TXT/CSV/TSV/DOCX/text-layer PDF plus typed image-only PDF/raster OCR, metadata, confidence, originating message ID, review routing, and source attribution are tested. |
| E1 | Email Classification Logic | Verified | All four construction types and mixed packages are covered by fixture tests and the full oracle. |
| E2 | Monolithic Extraction Logic | Verified | Dimensions, quantity, shape, TK, HT/mirror exception, TT/color/spandrel, coatings, and fabrication are covered. |
| E3 | Laminated Extraction Logic | Verified | Lite makeup, heat treatments, tint/color, interlayer material/thickness, and review requirements are covered. |
| E4 | Insulated Extraction Logic | Verified | Two lites, heat treatments, spacer, overall makeup, gas fill, coating, and color placement are covered. |
| E5 | Laminated-Insulated Extraction Logic | Verified | Three lites, laminated position, interlayer, spacer, gas, and heat-treatment isolation are covered. |
| E6 | Attachment Processing Framework | Verified plus stretch | Gmail and fixture attachments use shared parsers and carry `attachment:<filename>` provenance. Image pages use local OCR; failures and low confidence route to review without invented text. |
| E7 | Testing and Improvements | Verified | Full 28-email/40-item oracle, deterministic quality checks, text/image attachment fixtures, fresh Opus validation, and 81 passing tests. |
| F1 | Store Emails | Verified | SQLite and PostgreSQL persist complete email records and support upsert/read/list operations. |
| F2 | Store Extracted Units | Verified | One row per item, type-specific JSON, searchable fields, cascade/foreign-key integrity, and source storage. |
| F3 | Store Agent Execution Logs | Verified | Agent name/status/model/times/duration/email/error/review/item count/context are persisted and exposed. |
| G1 | Main opening page | Verified | `/view` provides queue metrics, navigation, filters, search, and status summaries. |
| G2 | Email and attachments display | Verified | Detail page shows metadata, body, attachment source/message/preview, and empty state. |
| G3 | Extraction Results View | Verified | Grouped glass units, dimensions, specs, fabrication, provenance, missing fields, review reasons, and agent runs are shown. |
| G4 | Validation of UI | Verified | Route/content/filter/empty/error checks pass for all 28 summaries and a complex detail record. A human pass at 1440x1000 and 390x844 confirmed responsive filters, internally scrolling tables, readable detail sections, and no page overflow or console errors. |
| G5 | Fix validation findings | Verified | Responsive table overflow, mobile filter layout, escaped content, fixture path containment, source visibility, and status filters are implemented. |
| H1 | Unit Tests - Classification Logic | Verified | Classification and mixed-package fixture tests pass. |
| H2 | Unit Tests - Extraction Logic | Verified | Type rules, dimensions, quantity, TT cleanup, source, conflict, and storage tests pass. |
| H3 | API Tests | Verified | Health, list/detail/source/run/task/UI/filter/path/error endpoints are covered. |
| H4 | Celery Worker Tests | Verified | Fixture/Gmail dispatch, message IDs/query fallback, failure cleanup, and live worker connectivity are covered. |
| H5 | Testing and Improvements | Verified | 81 tests plus compile, configuration, output-oracle, UI, Compose, and image-build gates pass. |
| I1 | GitHub Actions CI Setup | Verified remotely | `.github/workflows/ci.yml` handles push, PR, and manual runs; the published workflow completed successfully. |
| I2 | Automated Test Pipeline | Verified remotely | CI runs tests, configuration, compile, full output audit, and UI validation successfully. |
| I3 | Docker Build Pipeline | Verified remotely | CI validates base/Gmail Compose and builds the image successfully. |
| I4 | DevOps Testing and Improvements | Verified locally | Secret scans/ignores, non-root containers, localhost binding, named volumes, health checks, and configuration gates pass. |
| J1 | Final Testing and Improvements | Verified | Final QA, 81 tests, fresh Opus 28/40 oracle, fresh image-PDF Opus run, API checks, human desktop/mobile review, Gmail read-only OAuth, rebuilt Docker services, in-container OCR, Redis `PONG`, and Celery worker `pong` pass. |
| K1 | Architecture Documentation | Verified | `docs/architecture.md`, multi-agent design, and product acceptance review describe current boundaries and flow. |
| K2 | API Documentation | Verified | FastAPI OpenAPI plus `docs/api.md` cover synchronous, queued, read, source, and UI routes. |
| K3 | Deployment Guide | Verified | Local SQLite, Compose/PostgreSQL/Redis/Celery, Gmail override, validation, security limits, and shutdown are documented. |
| K4 | End-to-end demo preparation | Verified | `docs/final_demo.md` includes extraction authorization warning, audit, SQLite checks, UI cases, attachment demo, QA, and Docker steps. |

## Delivery Gates

No mandatory implementation or validation task is open locally. The fresh
authorized Opus run and its deterministic acceptance audit passed on August 19,
2026.

Read-only Gmail OAuth authentication passed on August 19, 2026. The configured
30-day RFQ query returned zero matching messages, so no live body or attachment
was available for extraction.
