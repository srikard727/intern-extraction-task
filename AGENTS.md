# Project Notes

This project is an internship RFQ extraction system for glass manufacturing quote requests.

## Assignment Priorities

- Extraction quality is the core of the assignment.
- Return one structured item per requested glass item, never one merged record per email.
- Always return a list of items, including for a single item.
- Normalize dimensions to decimal inches in one place in the code.
- Attribute extracted values to `body` or `attachment:<filename>`.
- Flag incomplete or ambiguous items for human review rather than guessing.
- Required fields vary by makeup:
  - All items: dimensions, quantity, TK, HT.
  - Monolithic: TT/color.
  - Insulated/IGU: airspace or overall thickness sufficient to derive it, plus lite makeup.
  - Laminated: interlayer or explicit note.
  - Laminated-insulated: laminated lite details, airspace/OA, and inboard lite details.
- Keep API keys, Gmail tokens, and credentials out of source control.

## Current Build Direction

- Gmail is the primary input source.
- Anthropic is the LLM provider, using the current available model from `.env`.
- SQLite plus JSON export are the persistence/output targets.
- Image-only attachments are out of scope for now; text-layer PDFs and text attachments can be supported.
