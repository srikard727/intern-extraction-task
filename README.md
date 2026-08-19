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

Field-level provenance remains internal to SQLite and is available through
`GET /emails/{email_id}/sources` and the browser detail view. It is intentionally
not duplicated into exported quote JSON.

`field_confidence` is populated by deterministic downstream scoring for fields
that are actually present in `glass_specs`. Claude is not asked to invent
confidence scores.

The extractor uses Claude for semantic reading, then applies Python quality checks so required missing fields are flagged rather than guessed. LangGraph orchestrates the per-email flow in `agent_rfq_extractor/graph.py`; Pydantic schemas stay in `models.py`, and normalization/validation stays in `quality.py`.

## Orchestration

The extraction path is exposed as the first registered agent:

- `BaseAgent` defines the common run contract and wraps timing, status, errors, and metadata.
- `AgentRegistry` registers and creates named agents.
- `AgentWorkflow` runs ordered agent steps and passes each agent output to the next step.
- `ExtractorAgent` is registered as `extractor` and wraps the existing LangGraph RFQ extraction graph.

Each email runs through this LangGraph flow:

```text
prepare -> extract -> normalize -> review -> assemble
                    \-> failure
```

The pipeline still owns Gmail/fixture loading and database/JSON persistence. It
creates the `extractor` agent from the default registry, places it into an
`AgentWorkflow`, and sends each email through that workflow. The graph owns the
per-email extraction path inside the agent. Each agent execution is recorded in
the configured database with run timing, status, model, email id, review status,
item count, error, and metadata.

See `docs/multi_agent_framework.md` for the future-agent plug-in contract.

## Setup

Create `.env` with:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-opus-4-8
GMAIL_CREDENTIALS=credentials.json
GMAIL_TOKEN=token_reader.json
RFQ_DB_PATH=outputs/rfq_extractions.db
RFQ_JSON_PATH=outputs/rfq_extractions.json
```

For PostgreSQL, set:

```bash
DATABASE_URL=postgresql://rfq:rfq@localhost:5432/rfq_extractions
```

For Redis/Celery, set:

```bash
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
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

## Run The API

Start the FastAPI app with:

```bash
.venv/bin/uvicorn agent_rfq_extractor.api:app --host 127.0.0.1 --port 8000 --reload
```

Useful endpoints:

- `GET /`: service metadata, docs link, and browser view link
- `GET /health`: database path, JSON path, model, and row counts
- `GET /view`: browser dashboard for stored extraction results
- `GET /view?status=human_review_required&glass_type=insulated&q=spacer`: filtered dashboard view
- `GET /view/emails/{email_id}`: browser detail view for one extraction
- `GET /emails`: stored extraction email summaries
- `GET /emails/{email_id}`: full stored extraction JSON for one email
- `GET /emails/{email_id}/sources`: internal per-field provenance for one email
- `GET /agent-runs`: agent execution logs
- `GET /agent-runs/{run_id}`: one agent execution log
- `POST /extract/fixture`: run fixture extraction through the agent workflow
- `POST /extract/gmail`: run Gmail extraction through the agent workflow
- `POST /tasks/extract/fixture`: queue fixture extraction through Celery
- `POST /tasks/extract/gmail`: queue Gmail extraction through Celery
- `GET /tasks/{task_id}`: Celery task status/result

## Run The Platform

Docker Compose starts PostgreSQL, Redis, the API, and a Celery worker:

```bash
docker compose up --build
```

The API and worker run as an unprivileged `app` user and share the
`rfq_outputs` named volume. PostgreSQL and RFQ outputs therefore survive
container replacement. The default Compose file does not mount Gmail secrets.

For Gmail extraction in Docker, mount the OAuth files read-only with the
credential override:

```bash
GMAIL_CREDENTIALS_PATH="$PWD/credentials.json" \
GMAIL_TOKEN_PATH="$PWD/token_reader.json" \
docker compose -f docker-compose.yml -f docker-compose.gmail.yml up --build
```

An expired token can refresh in memory, but the read-only mount intentionally
prevents the container from modifying the host token. Refresh or replace the
host token outside Docker when persistence is needed.

Seed the running PostgreSQL demo from the accepted SQLite results without an
LLM call:

```bash
.venv/bin/python scripts/import_sqlite_results.py \
  --source-db outputs/rfq_extractions.db \
  --database-url postgresql://rfq:rfq@127.0.0.1:5432/rfq_extractions \
  --json /tmp/rfq_postgres_export.json \
  --replace
docker compose cp \
  /tmp/rfq_postgres_export.json \
  api:/app/outputs/rfq_extractions.json
```

See `docs/platform.md` for PostgreSQL, Redis, Celery, and Docker details.

## Run The Fixture Demo

Refresh the provided fixture extraction outputs:

```bash
.venv/bin/python -m agent_rfq_extractor \
  --source fixture \
  --fixture Emails.txt \
  --limit 100 \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --replace-existing
```

Audit the regenerated JSON and SQLite outputs:

```bash
.venv/bin/python scripts/audit_extraction_outputs.py \
  --json outputs/rfq_extractions.json \
  --db outputs/rfq_extractions.db \
  --fixture-expectations
```

Validate the browser review UI routes:

```bash
.venv/bin/python scripts/validate_ui.py \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --fixture-expectations
```

Run the local final QA checks:

```bash
.venv/bin/python scripts/final_qa.py
```

After Docker Desktop is running, include the Docker image build:

```bash
.venv/bin/python scripts/final_qa.py --docker-build
```

The local test suite includes classification, extraction, API, attachment, and
Celery task coverage. The UI validation script checks rendering and filter
behavior for status, glass type, and search queries.

The fixture acceptance audit compares all 28 provided emails and all 40 expected
items against `tests/fixtures/expected_fixture_extractions.json`; it is not only
a row-count check.

Docker acceptance was revalidated on August 19, 2026: all four services started,
the API became healthy, Redis and Celery responded, PostgreSQL retained its
records, the API and worker ran as non-root, and both processes shared the
output volume. Tesseract 5.5 was available in both application containers, and
all three raster-only RFQ PDFs were OCR'd successfully inside the API image.
The accepted 28-email/40-item/28-run dataset and matching JSON export were
loaded into the live platform. Synchronous and queued extraction paths were
previously validated with rows persisted to PostgreSQL.

Start the API and open the browser view:

```bash
.venv/bin/uvicorn agent_rfq_extractor.api:app --host 127.0.0.1 --port 8000
```

Then visit:

```text
http://127.0.0.1:8000/view
```

For a repeatable text-attachment input, use `fixtures/attachment_demo.txt`.
Its referenced schedule is loaded from `fixtures/attachments/` and passed to
the extractor with `attachment:<filename>` provenance.

For image-only PDF validation, generate or refresh the raster fixtures and run
their three-email package into separate outputs:

```bash
.venv/bin/python scripts/generate_image_pdf_fixtures.py
.venv/bin/python -m agent_rfq_extractor \
  --source fixture \
  --fixture fixtures/image_pdf_rfq_emails.txt \
  --db /tmp/rfq_image_pdf.db \
  --json /tmp/rfq_image_pdf.json \
  --replace-existing
```

PDF pages without a usable text layer are rendered locally and read with
Tesseract. Attachment metadata records `extraction_method`, page counts,
`ocr_confidence`, and any OCR review reason. Fields sourced from OCR are capped
by that measured confidence, and OCR below the configured threshold routes the
email to human review.

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

To target PostgreSQL from the CLI, set `DATABASE_URL` or pass:

```bash
.venv/bin/python -m agent_rfq_extractor \
  --database-url postgresql://rfq:rfq@localhost:5432/rfq_extractions
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

To send the three synthetic image-only PDF examples, use the attachment-aware
fixture option. This command creates Gmail messages and therefore should only
be run against the intended test account:

```bash
.venv/bin/python rfq_sender.py \
  --emails-file fixtures/image_pdf_rfq_emails.txt \
  --follow-ups 0
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
- image-only PDFs through local Tesseract OCR
- PNG, JPEG, TIFF, and WebP images through local Tesseract OCR
- text files / CSV / TSV
- DOCX files

Clean typed image documents are supported. Low-confidence or failed OCR routes
to human review. Handwriting, complex takeoff drawings, and semantic matching
of drawing dimensions to glass cut sizes remain optional vision scope.

See `docs/product_acceptance.md` for the product decision and
`docs/requirement_traceability.md` for the complete A1-K4 task-to-evidence
matrix, remaining delivery confirmations, and optional stretch scope.

## Outputs

- SQLite: `outputs/rfq_extractions.db`
- JSON: `outputs/rfq_extractions.json`

The database has three tables:

- `emails`: one row per Gmail message
- `items`: one row per extracted glass item
- `agent_runs`: one row per agent execution
