# Project Notes

This project is an internship RFQ extraction system for glass manufacturing quote requests.

## Assignment Priorities

- Extraction quality is the core of the assignment.
- Return one structured item per requested glass item, never one merged record per email.
- Always return a list of items, including for a single item.
- Normalize dimensions to decimal inches in one place in the code.
- Attribute extracted values to `body` or `attachment:<filename>`.
- Flag incomplete or ambiguous items for human review rather than guessing.
- Required fields vary by glass type:
  - Monolithic: dimensions, TK, HT. HT is not mandatory for mirrors.
  - Laminated: dimensions, TK1, TK2, interlayer_thickness, interlayer_material, HT1, HT2.
  - Insulated/IGU: dimensions, TK1, TK2, spacer_material, spacer_thickness, HT1, HT2.
  - Laminated-insulated: dimensions, TK1, TK2, TK3, HT1, HT2, HT3, interlayer_material, interlayer_thickness, spacer_material, spacer_thickness, laminated_lite.
- Quantity defaults to 1 when the email does not give a definite count.
- Every item has a shape. Use rectangle for ordinary width x height glass, circle for diameter/radius/round glass, and square when only one side is given or shape is unclear.
- JSON output should put quote data under `extraction`, with `glass_type`, `glass_types`, `is_complete`, `missing_fields`, and `glass_type_groups`. Each group has `glass_type`, `is_complete`, and `glass_units`.
- Each `glass_unit` should use `glass_specs`, `fabrication`, `found_fields`, `missing_fields`, `is_complete`, and `field_confidence`; omit fields that do not apply to that glass type instead of filling the JSON with irrelevant nulls.
- Do not include `field_sources` in the exported JSON `glass_units`; keep source attribution in SQLite/internal records only.
- Monolithic spandrel/tinted output separates finish/type and color, for example `TT: "spandrel"` and `color: "warm grey"`.
- Do not ask Claude to fabricate `field_confidence`; only populate it from the deterministic scorer or another real scoring component.
- Keep API keys, Gmail tokens, and credentials out of source control.

## Current Build Direction

- Gmail is the primary input source.
- Gmail HTML bodies are preferred when present: `body_text` stores cleaned visible HTML text and `emailbody_variant` is `html`.
- `email_id` is an individual message id. `conv_id` is a labeled conversation/thread id such as `gmail-thread:<threadId>` and must not be the same string as `email_id`.
- Gmail extraction includes the chronological thread context for each message. Follow-up replies should use earlier messages in the same `conv_id` as the base RFQ and latest replies as clarifications/corrections.
- `rfq_sender.py` should send each sample RFQ as a Gmail conversation with related follow-up replies using `threadId`, `In-Reply-To`, and `References`; do not group unrelated RFQs into the same conversation. The default reply pattern should vary, including standalone single-email conversations.
- Anthropic is the LLM provider, using the current available model from `.env`.
- LangGraph orchestrates the per-email flow in `agent_rfq_extractor/graph.py`.
- SQLite plus JSON export are the persistence/output targets.
- SQLite stores common searchable columns plus type-specific item details in `spec_json`.
- Text-layer PDFs and text attachments are supported. Typed image-only PDFs and common image attachments use local Tesseract OCR with confidence-based human review; handwriting and drawing-aware interpretation remain optional stretch scope.
