# Glass RFQ Extraction System

This project reads inbound Gmail RFQ messages for glass manufacturing work and converts each email into structured, per-item glass specifications. It persists results to SQLite and exports the same records to JSON.

## What It Extracts

Each email produces one record with a list of items. Each item can include:

- mark
- normalized dimensions in decimal inches
- quantity
- TK / thickness
- HT / heat treatment
- TT / tint or glass type
- makeup type
- airspace / overall thickness
- coating and surface
- edge work or fabrication
- interlayer
- lite makeup
- field-level source attribution
- missing fields for human review

The extractor uses Claude for semantic reading, then applies Python quality checks so required missing fields are flagged rather than guessed.

## Setup

Create `.env` with:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-6
GMAIL_CREDENTIALS=credentials.json
GMAIL_TOKEN=token_reader.json
RFQ_DB_PATH=outputs/rfq_extractions.db
```

Install dependencies:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The Gmail OAuth token needs the readonly scope:

```text
https://www.googleapis.com/auth/gmail.readonly
```

## Run Against Gmail

```bash
.venv/bin/python -m rfq_extractor --limit 30
```

Useful options:

```bash
.venv/bin/python -m rfq_extractor \
  --query 'in:inbox newer_than:30d {subject:RFQ subject:"Request for Quote"}' \
  --limit 30 \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --replace-existing
```

## Local Fixture Mode

`Emails.txt` can be used for local checks without Gmail:

```bash
.venv/bin/python -m rfq_extractor --source fixture --fixture Emails.txt --limit 5
```

## Human Review Rules

All items require dimensions, quantity, TK, and HT.

Additional requirements depend on makeup:

- Monolithic requires TT/color.
- Laminated requires an interlayer or explicit interlayer note.
- Insulated requires airspace or overall thickness sufficient to derive it, plus both lites' makeup.
- Laminated-insulated requires laminated-lite detail, interlayer, airspace or overall thickness, and inboard lite detail.

If any required value is missing or ambiguous, the record status becomes `human_review_required`.

## Attachments

The current build supports text extraction from:

- text-layer PDFs
- text files / CSV / TSV
- DOCX files

Image-only attachments are intentionally out of scope for now.

## Outputs

- SQLite: `outputs/rfq_extractions.db`
- JSON: `outputs/rfq_extractions.json`

The database has two tables:

- `emails`: one row per Gmail message
- `items`: one row per extracted glass item
