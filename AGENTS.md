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
  - Laminated-insulated: dimensions, TK1, TK2, TK3, HT1, HT2, HT3, interlayer_material, interlayer_thickness, spacer_material, spacer_thickness, laminate_lite.
- Quantity defaults to 1 when the email does not give a definite count.
- Every item has a shape. Use rectangle for ordinary width x height glass, circle for diameter/radius/round glass, and square when only one side is given or shape is unclear.
- JSON output should be typed by `glass_type`; omit fields that do not apply to that glass type instead of filling the JSON with irrelevant nulls.
- Keep API keys, Gmail tokens, and credentials out of source control.

## Current Build Direction

- Gmail is the primary input source.
- Anthropic is the LLM provider, using the current available model from `.env`.
- LangGraph orchestrates the per-email flow in `agent_rfq_extractor/graph.py`.
- SQLite plus JSON export are the persistence/output targets.
- SQLite stores common searchable columns plus type-specific item details in `spec_json`.
- Image-only attachments are out of scope for now; text-layer PDFs and text attachments can be supported.
