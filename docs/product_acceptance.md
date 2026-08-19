# Product Acceptance Review

Review date: August 19, 2026

## Decision

The internship MVP satisfies the required assignment scope and is ready for a
final demonstration.
The core extraction artifacts contain 28 emails, 40 per-item glass records, and
28 agent execution logs. The deterministic acceptance audit passes every
provided email against a checked-in expected result.

This decision uses the assignment's minimum required scope as the acceptance
baseline. PostgreSQL, Redis, Celery, Docker Compose, the multi-agent framework,
and the review dashboard exceed that minimum.

The complete A1-K4 schedule mapping is maintained in
`docs/requirement_traceability.md`.

## Requirement Evidence

| Area | Status | Acceptance evidence |
|---|---|---|
| Per-item extraction | Verified | All 28 provided emails are mapped to 40 expected items in `tests/fixtures/expected_fixture_extractions.json`; the audit compares every item. |
| Monolithic extraction | Verified | Dimensions, quantity, TK, HT, TT/color, coating, edge work, and fabrication details are modeled and tested. Mirror HT exception is tested. |
| Laminated extraction | Verified | TK1/TK2, HT1/HT2, TT1/TT2, interlayer material/thickness, missing-field review, and grey tint preservation are tested. |
| Insulated extraction | Verified | Both lites, spacer material/thickness, gas fill, coating, OA-derived spacer behavior, and review rules are implemented. |
| Laminated-insulated extraction | Verified | Three lites, laminated position, interlayer, spacer, gas fill, heat-treatment isolation, and review rules are implemented. |
| Unit normalization | Verified | One module normalizes fractional/decimal inches, mm, cm, m, feet, and architectural feet-plus-inches to decimal inches. Area totals are rejected as dimensions. |
| Quantity policy | Verified | Definite positive counts are retained. Missing or approximate counts default to 1 and are attributed to `default`. |
| Human review | Verified | Missing required fields, ambiguity, approximate specs, empty extraction, failures, and body/attachment conflicts route to review without filling required values. |
| Source attribution | Verified | Field sources are persisted in SQLite and exposed through `/emails/{email_id}/sources` and the review UI. Exported quote JSON intentionally omits internal provenance. |
| Gmail ingestion | Verified by tests | Gmail IDs, labeled conversation IDs, visible HTML preference, chronological thread context, and prior-message attachments are covered. |
| Attachments and OCR | Verified by tests and demo fixtures | TXT, CSV, TSV, DOCX, text-layer PDF, typed image-only PDF, and common raster-image paths are covered. OCR records confidence and routes failed/low-confidence pages to review. |
| Structured output | Verified | Pydantic enforces one email record with grouped item lists, type-specific specs, completion state, review data, and required email metadata. |
| SQLite and JSON | Verified | Counts match, foreign-key integrity passes, exports are atomic, and internal item payloads remain auditable. |
| LangGraph and agent framework | Verified | The extractor runs through LangGraph behind `BaseAgent`, `AgentRegistry`, and `AgentWorkflow`; each run is logged. |
| API and UI | Verified | FastAPI read/extraction/task endpoints and the review dashboard are covered by route and filter validation. A human pass at desktop and mobile widths confirmed responsive layout, internal table scrolling, readable detail sections, and no browser console errors. |
| PostgreSQL/Redis/Celery/Docker | Verified locally | The August 19 Compose rebuild passed API health with 28 emails/40 items/28 runs, Redis `PONG`, Celery worker `pong`, PostgreSQL persistence, and Tesseract 5.5 availability in both application containers. All three raster-only PDFs were OCR'd successfully inside the API container. |
| Documentation and demo | Verified | Setup, architecture, API, deployment, platform, multi-agent, and final demo documents are present. |

## Policy Resolution

The assignment prose says all items require quantity, while its own ground rule
also says missing quantity should default to 1. The implementation follows the
latter rule: quantity is always present, but an absent or ambiguous quantity is
marked with source `default` rather than guessed from a range.

The project policy defines the quoting-critical required fields by construction:

- Monolithic: dimensions, TK, HT; HT is optional for mirrors.
- Laminated: dimensions, TK1, TK2, HT1, HT2, interlayer material, and interlayer thickness.
- Insulated: dimensions, TK1, TK2, HT1, HT2, spacer material, and spacer thickness.
- Laminated-insulated: dimensions, TK1/TK2/TK3, HT1/HT2/HT3, interlayer material/thickness, spacer material/thickness, and laminated-lite position.

TT/color is extracted and preserved, including explicit `clear`, `low-iron`,
color-only tint, mirror, and spandrel. Under the current project rules it is not
used as a universal completion gate because the business-specific matrix above
is authoritative. Ambiguous or TBD tint/color still routes to review when the
model identifies it as unresolved.

## Improvements Added During Acceptance

- Full expected-result audit for all 28 provided emails and 40 items.
- Explicit `clear` TT preservation and specific grey laminate tint preservation.
- Structured `fabrication.details` for holes, cutouts, radii, backing, and other non-edge work.
- Deterministic recovery of grounded fabrication details from stored notes, with
  approximate or pending hole/radius details routed to human review.
- Architectural feet-plus-inches and meter normalization.
- Approximate integer quantity guard (`~15`, `around 20`, or ranges default to 1).
- Source backfill/validation and an internal source endpoint/UI column.
- Prior-thread attachment preservation with originating message ID.
- Safe local attachment fixtures and a repeatable attachment demo input.
- Typed image-only PDF and raster-image OCR through local PDFium/Tesseract,
  including page metadata, measured confidence, confidence-capped extracted
  fields, and deterministic review routing.
- Three realistic raster-only RFQ PDF fixtures and an attachment-aware Gmail
  sample sender.
- Deferred destructive replacement until a run actually starts.
- Atomic JSON export, SQLite foreign-key enforcement, and database integrity checks.
- Fixture path containment in the API.
- Localhost-only Compose ports, API health check, optional `.env`, no reload mode, and no repository bind mount.
- Non-root API/worker containers, capped worker concurrency, and a shared persistent output volume.
- Read-only Gmail credential mounts through an explicit Compose override; the base stack mounts no OAuth secrets.
- Tested SQLite-to-PostgreSQL import for loading accepted records, internal
  provenance, and agent logs into the live demo without another model call.
- Automated checks for Opus defaults, canonical output paths, secret ignores, and manually runnable CI.
- Human desktop/mobile dashboard validation and a read-only live Gmail OAuth
  smoke test; the current 30-day RFQ query returned no matching messages.

## Fresh Model Validation

With explicit authorization on August 19, 2026, all 28 synthetic emails were
extracted again using `claude-opus-4-8`. The run produced 40 separate items and
28 execution logs. Its first strict audit exposed ordinary model wording drift
in seven checks, including `approx`, `seamed`, `grey tinted`, and omitted item
labels. Reusable deterministic normalization rules and five regression tests
were added; replaying the stored Opus response then produced the accepted
8-completed/20-review split and passed the full 28-email/40-item oracle.

A separate Opus run over the three raster-only PDF emails produced four items,
passed JSON/SQLite parity checks, preserved every field source as
`attachment:<filename>`, and correctly routed the intentionally missing
laminated-lite heat treatment to human review.
## Optional Stretch Scope

Typed image-only PDFs and common image files are now supported locally. General
handwriting and drawing-aware vision remain optional stretch work under the
original assignment. Future drawing interpretation needs drawing-specific tests,
especially tests that prevent rough-opening dimensions from being mistaken for
glass cut size.
