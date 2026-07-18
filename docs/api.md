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
- `GET /view`
- `GET /view/emails/{email_id}`
- `GET /emails?limit=100&offset=0`
- `GET /emails/{email_id}`
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

Open one stored extraction:

```text
GET /view/emails/{email_id}
```

The HTML view reads from the same configured database as the JSON endpoints and
shows status, item count, glass types, review reason, missing fields, specs, and
fabrication details.

## Queued Extraction

The same request bodies can be sent to Celery-backed endpoints:

- `POST /tasks/extract/fixture`
- `POST /tasks/extract/gmail`

The response includes a `task_id`. Poll task status with:

```text
GET /tasks/{task_id}
```
