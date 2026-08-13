# FastAPI Setup

Start the API:

```bash
.venv/bin/uvicorn agent_rfq_extractor.api:app --host 127.0.0.1 --port 8000 --reload
```

The app uses:

- `RFQ_DB_PATH` or `outputs/rfq_extractions.db`
- `RFQ_JSON_PATH` or `outputs/rfq_extractions.json`
- `ANTHROPIC_MODEL` or the project default model

## Read Endpoints

- `GET /health`
- `GET /`
- `GET /view`
- `GET /view?status=<status>&glass_type=<type>&q=<search>`
- `GET /view/emails/{email_id}`
- `GET /emails?limit=100&offset=0`
- `GET /emails/{email_id}`
- `GET /emails/{email_id}/sources`
- `GET /agent-runs?limit=100&offset=0`
- `GET /agent-runs?email_id=<email_id>`
- `GET /agent-runs/{run_id}`
- `GET /tasks/{task_id}`

## Extraction Endpoints

Run a fixture file:

```json
POST /extract/fixture
{
  "fixture_path": "Emails.txt",
  "limit": 5,
  "replace_existing": false,
  "model": null
}
```

Run Gmail search:

```json
POST /extract/gmail
{
  "query": "in:inbox newer_than:30d {subject:RFQ subject:\"Request for Quote\"}",
  "limit": 30,
  "email_ids": [],
  "replace_existing": false,
  "credentials_path": null,
  "token_path": null,
  "model": null
}
```

Pass `email_ids` to reprocess specific Gmail messages. If `email_ids` is empty,
the API uses the Gmail search query and limit.

## Browser View

Open the stored extraction results in a browser:

```text
GET /view
```

The dashboard includes summary cards, status and glass-type filters, text
search, the email queue, item counts, attachment counts, missing fields, and
human-review status.

Filter examples:

```text
GET /view?status=human_review_required
GET /view?glass_type=insulated
GET /view?status=human_review_required&glass_type=insulated&q=spacer
```

Open one stored extraction:

```text
GET /view/emails/{email_id}
```

The HTML view reads from the same configured database as the JSON endpoints and
shows status, email metadata, body text, attachment info, extracted units,
missing fields, human-review flags, fabrication details, and agent execution
logs. It also shows internal field provenance. The separate source endpoint
returns the same provenance without adding it to the exported quote JSON.

## Queued Extraction

The same request bodies can be sent to Celery-backed endpoints:

- `POST /tasks/extract/fixture`
- `POST /tasks/extract/gmail`

The response includes a `task_id`. Poll task status with:

```text
GET /tasks/{task_id}
```

## UI Validation

Run the repeatable UI route check against the stored fixture outputs:

```bash
.venv/bin/python scripts/validate_ui.py \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --fixture-expectations
```
