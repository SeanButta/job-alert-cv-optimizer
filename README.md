# job-alert-cv-optimizer

Automated job alert + CV optimization MVP.

## What it does

- Ingests Telegram job posts (sample adapter by default, real Telegram Bot API via env flag).
- Normalizes and deduplicates jobs by `external_id`, content hash, and link hash.
- Matches listings against resume + preferences with optional LLM reranking.
- Sends alerts through pluggable channels: email, SMS, Telegram, WhatsApp.
- Supports async queue-based notifications with retry and backoff.
- Generates CV recommendations and creates a Google Doc link (mock by default).
- Mobile-friendly dashboard for monitoring jobs, matches, and alerts.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy, SQLite, pytest
- Jinja2 for dashboard templating
- Optional: OpenAI/Anthropic for LLM reranking

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Job Sources    │────▶│   Ingestion      │────▶│   Dedupe        │
│  (Telegram...)  │     │   Adapter        │     │   (hash-based)  │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CV Generator   │◀────│   Matcher        │◀────│   JobPost DB    │
│  (Docs API)     │     │   + LLM Rerank   │     │                 │
└────────┬────────┘     └────────┬─────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Generated Doc  │     │   Alert Queue    │────▶│   Worker        │
│  (Google Docs)  │     │   (SQLite)       │     │   (retry+backoff)
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Notifications  │
                                                 │  Email/SMS/TG/WA│
                                                 └─────────────────┘
```

## Safe defaults

Real external calls are **OFF** by default. Enable selectively via env flags:

| Flag | Description |
|------|-------------|
| `ENABLE_REAL_NOTIFICATIONS=true` | Enable real email/SMS/Telegram/WhatsApp sends |
| `ENABLE_REAL_GOOGLE_DOCS=true` | Create real Google Docs (needs service account) |
| `ENABLE_REAL_TELEGRAM_INGEST=true` | Fetch from Telegram Bot API |
| `ENABLE_QUEUE_NOTIFICATIONS=true` | Use async queue instead of sync dispatch |
| `ENABLE_LLM_RERANKER=true` | Enable LLM-based match reranking |

## Run locally

```bash
# Install dependencies
python3 -m pip install -r requirements.txt

# Run tests
python3 -m pytest -v

# Start the API server
uvicorn app.main:app --reload
```

Then:
```bash
# Seed demo user
curl -X POST http://127.0.0.1:8000/seed

# Run demo flow (ingest -> match -> notify)
curl -X POST http://127.0.0.1:8000/run-demo

# View dashboard
open http://127.0.0.1:8000/dashboard

# Check queue stats
curl http://127.0.0.1:8000/queue-stats
```

## Queue Worker

For async notification processing:

```bash
# Start the worker (runs forever by default)
python scripts/run_worker.py

# With options
python scripts/run_worker.py --poll-interval 10 --batch-size 5

# Run for limited iterations (useful for testing)
python scripts/run_worker.py --max-iterations 100
```

Or via module:
```bash
python -m app.services.worker --poll-interval 5
```

## Dashboard

Access the mobile-friendly dashboard at `/dashboard`:

- **Stats**: Total jobs, matches, alerts sent, queue status
- **Recent Jobs**: Latest ingested job posts
- **Recent Matches**: Matches with scores and doc links
- **Alert Deliveries**: Notification statuses per channel
- **Queue Status**: Pending, processing, completed, failed counts

JSON API available at `/api/dashboard`.

## Phase 2 Features

### Strong Deduplication

Jobs are deduplicated by three criteria:
1. `external_id` - Original source ID
2. `content_hash` - SHA-256 of normalized title+description+company
3. `link_hash` - SHA-256 of normalized job link (removes tracking params)

Alerts are deduplicated per user+job+channel via idempotency keys.

### Queue + Retry Worker

SQLite-backed job queue for notification tasks:
- Configurable max attempts (default: 3)
- Exponential backoff with jitter
- Status tracking: pending → processing → completed/failed
- Automatic alert status updates

### LLM Reranker

Optional LLM-based match reranking (disabled by default):
- Supports OpenAI and Anthropic APIs
- Falls back to deterministic scoring on error
- Controlled by `ENABLE_LLM_RERANKER` flag

## Connector Configuration

### Telegram ingest
- Set `TELEGRAM_BOT_TOKEN`
- Add bot to source channel/group
- Optional filter: `TELEGRAM_SOURCE_CHAT_ID`

### Notifications
- **Email**: SendGrid (`SENDGRID_API_KEY`, `ALERT_FROM_EMAIL`)
- **SMS**: Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`)
- **Telegram send**: `TELEGRAM_BOT_TOKEN`
- **WhatsApp**: Meta Cloud API (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`)

### Google Docs
- Service account JSON path in `GOOGLE_SERVICE_ACCOUNT_JSON`
- Optional share target in `GOOGLE_DOC_SHARE_WITH`

### LLM Reranker
- OpenAI: `OPENAI_API_KEY`, `LLM_RERANKER_MODEL` (default: gpt-4o-mini)
- Anthropic: `ANTHROPIC_API_KEY`, `LLM_RERANKER_MODEL_ANTHROPIC` (default: claude-3-haiku)

## Files to customize

| File | Purpose |
|------|---------|
| `app/adapters/ingestion.py` | Add job board scrapers |
| `app/services/matching.py` | Customize scoring logic |
| `app/services/reranker.py` | Tune LLM prompts |
| `app/services/notifier.py` | Add notification channels |
| `app/services/docs.py` | Customize doc templates |
| `app/templates/dashboard.html` | Customize dashboard UI |

## Testing

```bash
# Run all tests
python3 -m pytest -v

# Run specific test files
python3 -m pytest tests/test_dedupe.py -v
python3 -m pytest tests/test_queue.py -v
python3 -m pytest tests/test_reranker.py -v

# Run with coverage
python3 -m pytest --cov=app --cov-report=term-missing
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/seed` | Create demo user with resume/preferences |
| POST | `/run-demo` | Run full ingestion→match→notify flow |
| GET | `/queue-stats` | Get notification queue statistics |
| GET | `/dashboard` | Mobile-friendly HTML dashboard |
| GET | `/api/dashboard` | Dashboard data as JSON |

## License

MIT
