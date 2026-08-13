# Requirement Traceability Matrix

Review date: August 12, 2026

This matrix maps every scheduled task to concrete repository evidence. `Verified`
means the implementation and its local acceptance evidence pass. `Implemented
locally` means the code is ready but an external delivery confirmation remains.
Optional image/OCR work is excluded from the assignment MVP by the stated scope.

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
| D1 | Email data extraction | Verified in tests | Gmail message/thread IDs, metadata, visible HTML, plain fallback, chronological context, and corrections are covered. A live OAuth mailbox smoke test remains environment-dependent. |
| D2 | Attachment data extraction | Verified for MVP | TXT/CSV/TSV/DOCX/text-layer PDF extraction, metadata, originating message ID, and source attribution are tested. Image-only OCR is optional stretch scope. |
| E1 | Email Classification Logic | Verified | All four construction types and mixed packages are covered by fixture tests and the full oracle. |
| E2 | Monolithic Extraction Logic | Verified | Dimensions, quantity, shape, TK, HT/mirror exception, TT/color/spandrel, coatings, and fabrication are covered. |
| E3 | Laminated Extraction Logic | Verified | Lite makeup, heat treatments, tint/color, interlayer material/thickness, and review requirements are covered. |
| E4 | Insulated Extraction Logic | Verified | Two lites, heat treatments, spacer, overall makeup, gas fill, coating, and color placement are covered. |
| E5 | Laminated-Insulated Extraction Logic | Verified | Three lites, laminated position, interlayer, spacer, gas, and heat-treatment isolation are covered. |
| E6 | Attachment Processing Framework | Verified for MVP | Gmail and fixture attachments use shared parsers and carry `attachment:<filename>` provenance; unsupported images fail explicitly without invented text. |
| E7 | Testing and Improvements | Verified | Full 28-email/40-item oracle, deterministic quality checks, attachment fixtures, and 69 passing tests. |
| F1 | Store Emails | Verified | SQLite and PostgreSQL persist complete email records and support upsert/read/list operations. |
| F2 | Store Extracted Units | Verified | One row per item, type-specific JSON, searchable fields, cascade/foreign-key integrity, and source storage. |
| F3 | Store Agent Execution Logs | Verified | Agent name/status/model/times/duration/email/error/review/item count/context are persisted and exposed. |
| G1 | Main opening page | Verified | `/view` provides queue metrics, navigation, filters, search, and status summaries. |
| G2 | Email and attachments display | Verified | Detail page shows metadata, body, attachment source/message/preview, and empty state. |
| G3 | Extraction Results View | Verified | Grouped glass units, dimensions, specs, fabrication, provenance, missing fields, review reasons, and agent runs are shown. |
| G4 | Validation of UI | Verified automatically | Route/content/filter/empty/error checks pass for all 28 summaries and a complex detail record. A final human desktop/mobile visual pass is recommended. |
| G5 | Fix validation findings | Verified | Responsive table overflow, mobile filter layout, escaped content, fixture path containment, source visibility, and status filters are implemented. |
| H1 | Unit Tests - Classification Logic | Verified | Classification and mixed-package fixture tests pass. |
| H2 | Unit Tests - Extraction Logic | Verified | Type rules, dimensions, quantity, TT cleanup, source, conflict, and storage tests pass. |
| H3 | API Tests | Verified | Health, list/detail/source/run/task/UI/filter/path/error endpoints are covered. |
| H4 | Celery Worker Tests | Verified | Fixture/Gmail dispatch, message IDs/query fallback, failure cleanup, and live worker connectivity are covered. |
| H5 | Testing and Improvements | Verified | 69 tests plus compile, configuration, output-oracle, UI, Compose, and image-build gates pass. |
| I1 | GitHub Actions CI Setup | Implemented locally | `.github/workflows/ci.yml` handles push, PR, and manual runs. Commit/push and observe one remote run. |
| I2 | Automated Test Pipeline | Implemented locally | CI runs tests, configuration, compile, full output audit, and UI validation. Remote run awaits publish. |
| I3 | Docker Build Pipeline | Implemented locally | CI validates base/Gmail Compose and builds the image. Remote run awaits publish; local clean build passes. |
| I4 | DevOps Testing and Improvements | Verified locally | Secret scans/ignores, non-root containers, localhost binding, named volumes, health checks, and configuration gates pass. |
| J1 | Final Testing and Improvements | Verified locally | Final QA, 69 tests, 28/40 oracle, API/UI checks, both Compose configs, live services, and image build pass. A fresh paid Opus rerun requires approval to transmit fixture text. |
| K1 | Architecture Documentation | Verified | `docs/architecture.md`, multi-agent design, and product acceptance review describe current boundaries and flow. |
| K2 | API Documentation | Verified | FastAPI OpenAPI plus `docs/api.md` cover synchronous, queued, read, source, and UI routes. |
| K3 | Deployment Guide | Verified | Local SQLite, Compose/PostgreSQL/Redis/Celery, Gmail override, validation, security limits, and shutdown are documented. |
| K4 | End-to-end demo preparation | Verified | `docs/final_demo.md` includes extraction authorization warning, audit, SQLite checks, UI cases, attachment demo, QA, and Docker steps. |

## Delivery Gates

No mandatory implementation task is open locally. Final delivery still requires:

1. Commit and push the current worktree, then observe the GitHub Actions workflow.
2. Run a fresh full Opus extraction only after authorization to transmit the
   synthetic email fixture to Anthropic and consume API credits.
3. Perform a short human visual check of the dashboard at desktop and mobile
   widths. Automated route, content, and filter validation already passes.

Live Gmail OAuth validation depends on access to the intended mailbox and is
separate from the deterministic fixture acceptance suite.
