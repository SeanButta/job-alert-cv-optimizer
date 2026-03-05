# job-alert-cv-optimizer

Automated job alert + CV optimization MVP.

## What it does

- Ingests job posts from multiple configurable sources (Telegram channels, websites, LinkedIn recruiters).
- Normalizes and deduplicates jobs by `external_id`, content hash, and link hash.
- Matches listings against resume + preferences with optional LLM reranking.
- Sends alerts through pluggable channels: email, SMS, Telegram, WhatsApp.
- Supports async queue-based notifications with retry and backoff.
- Generates CV recommendations and creates a Google Doc link (mock by default).
- Mobile-friendly dashboard for monitoring jobs, matches, alerts, and source management.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy, SQLite, pytest
- Jinja2 for dashboard templating
- Optional: OpenAI/Anthropic for LLM reranking

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Job Sources (User-Configurable)          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   Telegram   │  │   Website    │  │ LinkedIn Recruiter│  │
│  │   Channels   │  │   URLs       │  │ (passive tagging) │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬─────────┘  │
└─────────┼─────────────────┼────────────────────┼────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│              Source Poller Worker (Background)              │
│  - Polls enabled sources periodically                       │
│  - Tags jobs with recruiter info when matched               │
│  - Integrates with dedupe pipeline                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Source Adapter │────▶│   Dedupe         │────▶│   JobPost DB    │
│  (per type)     │     │   (hash-based)   │     │                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CV Generator   │◀────│   Matcher        │◀────│   User Prefs    │
│  (Docs API)     │     │   + LLM Rerank   │     │                 │
└────────┬────────┘     └────────┬─────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Generated Doc  │     │   Alert Queue    │────▶│   Notify Worker │
│  (Google Docs)  │     │   (SQLite)       │     │   (retry+backoff)
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Safe defaults

Real external calls are **OFF** by default. Enable selectively via env flags:

| Flag | Description |
|------|-------------|
| `ENABLE_REAL_NOTIFICATIONS=true` | Enable real email/SMS/Telegram/WhatsApp sends |
| `ENABLE_REAL_GOOGLE_DOCS=true` | Create real Google Docs (needs service account) |
| `ENABLE_REAL_TELEGRAM_INGEST=true` | Fetch from Telegram Bot API (legacy flag) |
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

# View dashboard (includes source management)
open http://127.0.0.1:8000/dashboard

# Check queue stats
curl http://127.0.0.1:8000/queue-stats
```

## Workers

### Notification Queue Worker

For async notification processing:

```bash
# Start the worker (runs forever by default)
python scripts/run_worker.py

# With options
python scripts/run_worker.py --poll-interval 10 --batch-size 5

# Run for limited iterations (useful for testing)
python scripts/run_worker.py --max-iterations 100
```

### Source Poller Worker

For periodic job source polling:

```bash
# Start the source poller (runs forever by default)
python scripts/run_source_poller.py

# With options
python scripts/run_source_poller.py --poll-interval 300  # 5 minutes

# Run for limited iterations (useful for testing)
python scripts/run_source_poller.py --max-iterations 10
```

Environment variables for source polling:
- `SOURCE_POLL_INTERVAL_SECONDS` - Seconds between poll cycles (default: 300)
- `SOURCE_MIN_CHECK_INTERVAL_SECONDS` - Min seconds between checking same source (default: 60)
- `SOURCE_MAX_ERRORS` - Consecutive errors before auto-disable (default: 5)

## Dashboard

Access the mobile-friendly dashboard at `/dashboard`:

**Tabs:**
- **Overview**: Stats, queue status
- **Sources**: Add/edit/delete job sources with activate/deactivate controls
- **Jobs**: Recent ingested job posts
- **Matches**: Matches with scores and doc links
- **Alerts**: Notification statuses per channel

**Source Management UI:**
- Add Telegram channels (paste `@channel` or `t.me/channel` link)
- Add website URLs for job page scraping
- Track LinkedIn recruiters (compliance-safe passive tagging)
- Test source connectivity
- Activate/deactivate sources
- View error counts and last check times

JSON API available at `/api/dashboard`.

## Phase 3 Features: User-Configurable Sources

### Job Source Types

| Type | Description | Polling | Notes |
|------|-------------|---------|-------|
| `telegram_channel` | Telegram channels/groups | Active | Requires bot in channel |
| `website` | Web pages with job listings | Active | Basic HTML parsing scaffold |
| `linkedin_recruiter` | LinkedIn recruiter tracking | Passive | Tags jobs from other sources |

### Source Management API

```bash
# List all sources
curl http://127.0.0.1:8000/api/sources

# Filter by type
curl "http://127.0.0.1:8000/api/sources?type=telegram_channel"

# Create Telegram channel source
curl -X POST http://127.0.0.1:8000/api/sources \
  -H "Content-Type: application/json" \
  -d '{"type": "telegram_channel", "identifier": "@jobchannel", "name": "Job Channel"}'

# Create website source
curl -X POST http://127.0.0.1:8000/api/sources \
  -H "Content-Type: application/json" \
  -d '{"type": "website", "identifier": "https://example.com/jobs"}'

# Create LinkedIn recruiter (with company config)
curl -X POST http://127.0.0.1:8000/api/sources \
  -H "Content-Type: application/json" \
  -d '{"type": "linkedin_recruiter", "identifier": "linkedin.com/in/recruiter", "config": {"company": "Acme Corp"}}'

# Activate/deactivate source
curl -X POST http://127.0.0.1:8000/api/sources/1/activate
curl -X POST http://127.0.0.1:8000/api/sources/1/deactivate

# Test source connectivity
curl -X POST http://127.0.0.1:8000/api/sources/1/test

# Delete source
curl -X DELETE http://127.0.0.1:8000/api/sources/1
```

### Telegram Channel Source

**Setup:**
1. Create a Telegram bot via @BotFather
2. Set `TELEGRAM_BOT_TOKEN` environment variable
3. Add bot to your job channel as admin
4. Add channel in dashboard: `@channelname` or `t.me/channelname`

**Limitations:**
- Bot only sees messages sent after being added
- `getUpdates` has 100-message limit per call
- For high-volume channels, consider webhooks (not yet implemented)
- Private channels require invite link or numeric ID

**Identifier formats:**
- `@channelname`
- `t.me/channelname`
- `https://t.me/channelname`
- `-1001234567890` (numeric ID)

### Website Source

**Setup:**
1. Add website URL in dashboard
2. Configure selectors in config JSON (optional)

**Current limitations (scaffold implementation):**
- Basic HTML link extraction only
- No JavaScript rendering (SPAs won't work)
- May be blocked by anti-bot measures
- Respects basic rate limiting

**Production upgrade path:**
- Add BeautifulSoup/lxml for proper HTML parsing
- Add Playwright for JavaScript rendering
- Add rotating proxies for blocked sites
- Add site-specific adapters for major job boards

### LinkedIn Recruiter Tracking

**Compliance-safe mode:**
- Does NOT scrape LinkedIn (ToS violation)
- Passively tags jobs from other sources when recruiter name/company matches
- Stores recruiter metadata for manual tracking

**Setup:**
1. Add recruiter profile URL or name in dashboard
2. Optionally set company name in config
3. Jobs mentioning the recruiter's company will be auto-tagged

**How it works:**
- When source poller ingests jobs from Telegram/website sources
- It checks if job description or company matches tracked recruiters
- Matching jobs get `[Recruiter: Name]` prefix in description

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
- Configure sources via dashboard or API

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
| `app/adapters/ingestion.py` | Legacy Telegram adapter |
| `app/adapters/source_adapters.py` | **NEW:** Source adapters for all source types |
| `app/api/sources.py` | **NEW:** Source CRUD API |
| `app/models/sources.py` | **NEW:** JobSource data model |
| `app/services/source_poller.py` | **NEW:** Background source polling worker |
| `app/services/matching.py` | Customize scoring logic |
| `app/services/reranker.py` | Tune LLM prompts |
| `app/services/notifier.py` | Add notification channels |
| `app/services/docs.py` | Customize doc templates |
| `app/templates/dashboard.html` | Dashboard UI with source management |

## Testing

```bash
# Run all tests
python3 -m pytest -v

# Run specific test files
python3 -m pytest tests/test_dedupe.py -v
python3 -m pytest tests/test_queue.py -v
python3 -m pytest tests/test_reranker.py -v
python3 -m pytest tests/test_sources.py -v  # NEW: Source tests

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
| **GET** | `/api/sources` | **List all sources** |
| **POST** | `/api/sources` | **Create new source** |
| **GET** | `/api/sources/{id}` | **Get source by ID** |
| **PUT** | `/api/sources/{id}` | **Update source** |
| **DELETE** | `/api/sources/{id}` | **Delete source** |
| **POST** | `/api/sources/{id}/activate` | **Activate source** |
| **POST** | `/api/sources/{id}/deactivate` | **Deactivate source** |
| **POST** | `/api/sources/{id}/test` | **Test source connectivity** |

## Data Model: JobSource

```python
class JobSource:
    id: int
    type: str              # telegram_channel | website | linkedin_recruiter
    identifier: str        # Channel/URL/profile identifier
    name: str              # Display name
    status: str            # active | inactive | error
    user_id: int | None    # Owner (NULL = global source)
    config: str | None     # JSON config for source-specific settings
    last_checked: datetime # Last successful check
    last_error: str | None # Last error message
    error_count: int       # Consecutive errors (resets on success)
    created_at: datetime
    updated_at: datetime
```

## License

MIT
