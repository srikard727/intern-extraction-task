# Deployment Guide

This project can run locally with SQLite or as a Docker Compose platform with
PostgreSQL, Redis, FastAPI, and a Celery worker.

## Prerequisites

- Python 3.12
- Tesseract OCR 5 for image-only attachments
- Docker Desktop or Docker Engine with Compose
- Anthropic API key
- Gmail OAuth credentials and token for Gmail extraction

Keep `.env`, Gmail tokens, and API keys out of source control.

Install Tesseract for a local non-Docker run:

```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install -y tesseract-ocr
```

The Docker image installs Tesseract automatically.

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
RFQ_OCR_ENABLED=true
RFQ_OCR_REVIEW_THRESHOLD=0.90
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

Compose binds PostgreSQL, Redis, and the API to `127.0.0.1` for local/demo use.
The API image runs without development reload or a source-tree bind mount, and
`.env` is optional for Compose configuration validation in CI. Live extraction
still requires `ANTHROPIC_API_KEY` at runtime. API and worker processes run as
the unprivileged `app` user and share the `rfq_outputs` named volume. PostgreSQL
uses its own named volume.

The default stack deliberately does not mount Gmail OAuth files. To enable
Gmail extraction, provide the local paths through the read-only override:

```bash
GMAIL_CREDENTIALS_PATH="$PWD/credentials.json" \
GMAIL_TOKEN_PATH="$PWD/token_reader.json" \
docker compose -f docker-compose.yml -f docker-compose.gmail.yml up --build
```

The OAuth files appear under `/run/secrets` in the API and worker. If Google
refreshes an expired token, the process can use it in memory but cannot persist
it through the read-only mount; refresh the host token outside Docker when
needed.

Useful checks:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/view
http://127.0.0.1:8000/docs
```

To load the already accepted SQLite fixture records into the running PostgreSQL
demo without calling Anthropic again:

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

This copies emails, per-item internal provenance, and agent execution logs. It
is a destructive replacement of the target demo database only; the source
SQLite artifacts are read-only inputs. The second command synchronizes the
generated export into the named output volume shared by API and worker.

Stop the platform:

```bash
docker compose down
```

Latest infrastructure validation on August 12, 2026:

- A clean image rebuild and forced container replacement succeeded.
- PostgreSQL, Redis, API, and worker started; the API reported healthy.
- Redis returned `PONG` and one Celery node returned `pong` at concurrency 2.
- API and worker ran as uid/gid `999(app)`, not root.
- The API wrote a marker that the worker read from the shared output volume.
- `GET /health` reported `claude-opus-4-8`; `GET /view` returned HTTP 200.
- The tested import loaded 28 emails, 40 items, and 28 agent runs into
  PostgreSQL; API and worker both read the matching 28-record JSON export.
- Synchronous and queued extraction paths were previously validated against
  PostgreSQL with a one-email smoke fixture.

## Validation

Run the local final QA suite:

```bash
.venv/bin/python scripts/final_qa.py
```

When Docker Desktop is running, include the image build:

```bash
.venv/bin/python scripts/final_qa.py --docker-build
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

The UI validation checks dashboard rendering, detail pages, human-review pages,
and filter behavior for status, glass type, and search queries.

The final QA command also checks the Opus default, canonical output paths,
secret-ignore patterns, Compose safety settings, and the manual GitHub Actions
trigger. It validates both the base Compose file and the Gmail credential
override.

## Celery Worker Test Coverage

The local test suite includes task-level Celery coverage in eager execution
mode. These tests verify that:

- fixture tasks execute `RFQPipeline` and return extraction summaries
- Gmail tasks use explicit message IDs when provided
- Gmail tasks fall back to search query extraction when message IDs are absent
- pipelines are closed even when validation fails

Live Redis/worker validation is still covered by Docker Compose rather than by
the isolated unit tests.

## CI

GitHub Actions runs:

- Python unit tests
- Python compile checks
- JSON/SQLite extraction audit
- `/view` UI validation
- Docker Compose config validation
- Gmail credential override validation
- Docker image build

The bundled PostgreSQL password and unauthenticated localhost API are demo
defaults, not a production security posture. A production deployment must use
managed secrets, authentication/authorization, TLS, restricted service
networks, backups, and monitoring.
