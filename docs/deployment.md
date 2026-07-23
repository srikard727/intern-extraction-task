# Deployment Guide

This project can run locally with SQLite or as a Docker Compose platform with
PostgreSQL, Redis, FastAPI, and a Celery worker.

## Prerequisites

- Python 3.12
- Docker Desktop or Docker Engine with Compose
- Anthropic API key
- Gmail OAuth credentials and token for Gmail extraction

Keep `.env`, Gmail tokens, and API keys out of source control.

## Local SQLite Deployment

Install dependencies:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create `.env`:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-opus-4-8
GMAIL_CREDENTIALS=credentials.json
GMAIL_TOKEN=token_reader.json
RFQ_DB_PATH=outputs/rfq_extractions.db
RFQ_JSON_PATH=outputs/rfq_extractions.json
```

Run fixture extraction:

```bash
.venv/bin/python -m agent_rfq_extractor \
  --source fixture \
  --fixture Emails.txt \
  --limit 100 \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --replace-existing
```

Start the API/UI:

```bash
.venv/bin/uvicorn agent_rfq_extractor.api:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/view
```

## Docker Compose Deployment

Start the full platform:

```bash
docker compose up --build
```

Services:

- `postgres`: PostgreSQL database
- `redis`: Celery broker and result backend
- `api`: FastAPI app on `http://127.0.0.1:8000`
- `worker`: Celery worker

Useful checks:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/view
http://127.0.0.1:8000/docs
```

Stop the platform:

```bash
docker compose down
```

## Validation

Run the local final QA suite:

```bash
.venv/bin/python scripts/final_qa.py
```

If Docker is unavailable and you only want Python/API/UI checks:

```bash
.venv/bin/python scripts/final_qa.py --skip-docker
```

Validate only the UI:

```bash
.venv/bin/python scripts/validate_ui.py \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --fixture-expectations
```

## CI

GitHub Actions runs:

- Python unit tests
- Python compile checks
- JSON/SQLite extraction audit
- `/view` UI validation
- Docker Compose config validation
- Docker image build
