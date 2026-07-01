# Glass RFQ Extraction System

This project reads inbound Gmail RFQ messages for glass manufacturing work and converts each email into structured, per-item glass specifications. It persists results to SQLite and exports the same records to JSON.

## What It Extracts

Each email produces one record with quote data under `extraction`. The
`extraction.glass_type_groups` list groups units by `glass_type`, and each group
has a `glass_units` list. Each unit can include:

- mark
- normalized dimensions in decimal inches
- quantity, defaulted to 1 when no definite count is provided
- shape, defaulting to rectangle for normal width x height glass
- TK / HT for monolithic glass
- TK1, TK2, TK3 and HT1, HT2, HT3 for multi-lite glass
- TT / tint or glass type
- color, when separately stated or inferable from a coating such as Warm Grey Spandrel
- glass type, such as monolithic, laminated, insulated, or laminated-insulated
- spacer material and spacer thickness for insulated units
- gas fill for insulated and laminated-insulated units
- interlayer material and interlayer thickness for laminated units
- coating and surface
- edge work or fabrication
- field-level source attribution in SQLite/internal records
- missing fields for human review

The JSON export is typed by `glass_type`, so monolithic items do not carry
irrelevant laminated or insulated fields full of nulls. The quote payload is
formatted like:

```json
{
  "extraction": {
    "glass_type": "monolithic",
    "glass_types": ["monolithic"],
    "is_complete": true,
    "missing_fields": [],
    "glass_type_groups": [
      {
        "glass_type": "monolithic",
        "is_complete": true,
        "glass_units": [
          {
            "width": 68.0,
            "height": 37.0,
            "quantity": 8,
            "unit_of_measurement": "inch",
            "shape": "rectangle",
            "mark": "1/4\" Warm Grey Spandrel Temp",
            "glass_specs": {
              "TK": "1/4\"",
              "HT": "tempered",
              "TT": "spandrel",
              "color": "warm grey"
            },
            "fabrication": {
              "coatings": "Warm Grey Spandrel"
            },
            "found_fields": ["TK", "HT", "dimensions"],
            "missing_fields": [],
            "is_complete": true,
            "field_confidence": {
              "TK": 0.97,
              "HT": 0.93,
              "TT": 0.95,
              "color": 0.95
            }
          }
        ]
      }
    ]
  }
}
```

SQLite keeps common searchable columns and stores the type-specific item payload
in `items.spec_json`.

`field_confidence` is populated by deterministic downstream scoring for fields
that are actually present in `glass_specs`. Claude is not asked to invent
confidence scores.

The extractor uses Claude for semantic reading, then applies Python quality checks so required missing fields are flagged rather than guessed. LangGraph orchestrates the per-email flow in `agent_rfq_extractor/graph.py`; Pydantic schemas stay in `models.py`, and normalization/validation stays in `quality.py`.

## Orchestration

Each email runs through this LangGraph flow:

```text
prepare -> extract -> normalize -> review -> assemble
                    \-> failure
```

The pipeline still owns Gmail/fixture loading and SQLite/JSON persistence. The graph owns the per-email extraction path.

## Setup

Create `.env` with:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-opus-4-8
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

For Gmail messages with an HTML body, `body_text` is populated from the visible
HTML text and `emailbody_variant` is set to `html`. Plain-text-only messages and
fixture emails use `plain`.

## Run Against Gmail

```bash
.venv/bin/python -m agent_rfq_extractor --limit 30
```

Useful options:

```bash
.venv/bin/python -m agent_rfq_extractor \
  --query 'in:inbox newer_than:30d {subject:RFQ subject:"Request for Quote"}' \
  --limit 30 \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --replace-existing
```

To update only specific Gmail messages, pass Gmail message IDs and do not use
`--replace-existing`:

```bash
.venv/bin/python -m agent_rfq_extractor \
  --email-id 19ead53eeef26caa \
  --email-id 19ead53f61f7d179 \
  --db database/rfq_results.db \
  --json outputs/rfq_extractions.json
```

You can also pass a comma-separated list:

```bash
.venv/bin/python -m agent_rfq_extractor \
  --email-ids 19ead53eeef26caa,19ead53f61f7d179
```

Without `--replace-existing`, records are upserted: only those emails are
re-extracted, and the rest of the existing database remains in place.

## Seed Gmail Test Emails

`rfq_sender.py` can send the sample messages into Gmail. By default each RFQ
sample becomes its own Gmail conversation, and the reply count varies with the
repeating pattern `1,2,0`. That creates some one-reply conversations, some
two-reply conversations, and some standalone single-email conversations:

```bash
.venv/bin/python rfq_sender.py
```

Use `--follow-up-pattern` to control the variety, or `--follow-ups` when every
sample should use the same reply count:

```bash
.venv/bin/python rfq_sender.py --follow-up-pattern 0,1,2,1
.venv/bin/python rfq_sender.py --follow-ups 0
.venv/bin/python rfq_sender.py --follow-ups 2
```

In extraction output, `email_id` is the individual Gmail message id. `conv_id`
is labeled from Gmail's thread id as `gmail-thread:<threadId>`, so replies in
the same conversation share the same `conv_id` while keeping distinct
`email_id` values. When extracting a Gmail message, the pipeline also supplies
the chronological Gmail thread to Claude, so follow-up replies can clarify or
correct the original RFQ instead of being treated as empty standalone requests.

## Local Fixture Mode

`Emails.txt` can be used for local checks without Gmail:

```bash
.venv/bin/python -m agent_rfq_extractor --source fixture --fixture Emails.txt --limit 5
```

## Human Review Rules

Quantity is defaulted to 1 when the message does not provide a definite count.
Missing quantity no longer blocks extraction.

Required fields depend on glass type:

- Monolithic requires dimensions, TK, and HT. HT is not mandatory for mirrors.
- Laminated requires dimensions, TK1, TK2, interlayer_thickness, interlayer_material, HT1, and HT2.
- Insulated requires dimensions, TK1, TK2, spacer_material, spacer_thickness, HT1, and HT2.
- Laminated-insulated requires dimensions, TK1, TK2, TK3, HT1, HT2, HT3, interlayer_material, interlayer_thickness, spacer_material, spacer_thickness, and laminated_lite.

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
