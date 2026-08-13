# Product Acceptance Review

Review date: August 12, 2026

## Decision

The internship MVP satisfies the required assignment scope and is ready for a
final demonstration, subject to the two external confirmations listed below.
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
| Text attachments | Verified by tests and demo fixture | TXT, CSV, TSV, DOCX, and text-layer PDF paths are covered. `fixtures/attachment_demo.txt` provides a repeatable source-attributed attachment demo. |
| Structured output | Verified | Pydantic enforces one email record with grouped item lists, type-specific specs, completion state, review data, and required email metadata. |
| SQLite and JSON | Verified | Counts match, foreign-key integrity passes, exports are atomic, and internal item payloads remain auditable. |
| LangGraph and agent framework | Verified | The extractor runs through LangGraph behind `BaseAgent`, `AgentRegistry`, and `AgentWorkflow`; each run is logged. |
| API and UI | Verified | FastAPI read/extraction/task endpoints and the review dashboard are covered by route and filter validation. |
| PostgreSQL/Redis/Celery/Docker | Verified locally | Compose/image rebuild, API health, non-root execution, shared output persistence, Redis/Celery connectivity, PostgreSQL persistence, synchronous extraction, and queued extraction have been validated. |
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
- Deferred destructive replacement until a run actually starts.
- Atomic JSON export, SQLite foreign-key enforcement, and database integrity checks.
- Fixture path containment in the API.
- Localhost-only Compose ports, API health check, optional `.env`, no reload mode, and no repository bind mount.
- Non-root API/worker containers, capped worker concurrency, and a shared persistent output volume.
- Read-only Gmail credential mounts through an explicit Compose override; the base stack mounts no OAuth secrets.
- Tested SQLite-to-PostgreSQL import for loading accepted records, internal
  provenance, and agent logs into the live demo without another model call.
- Automated checks for Opus defaults, canonical output paths, secret ignores, and manually runnable CI.

## External Confirmations

Two checks cannot be completed from deterministic local data alone:

1. A fresh 28-email Anthropic Opus extraction requires explicit authorization
   to transmit the synthetic fixture contents to Anthropic. The acceptance run
   instead replayed the already stored Opus output through the current quality
   layer and passed the full oracle.
2. GitHub Actions must be observed after the pending workflow commit is pushed.
   Local workflow content and project checks are valid, but the remote run is an
   external repository state.

## Optional Stretch Scope

Image-only scans, photographs, handwritten takeoffs, and drawing-aware vision
remain optional stretch work under the original assignment. They are not
required for MVP acceptance. If pursued, the preferred implementation is a
vision-capable model with drawing-specific tests, especially tests that prevent
rough-opening dimensions from being mistaken for glass cut size.
