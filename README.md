# job-alert-cv-optimizer

Automated job alert + CV optimization MVP.

## What it does

- Ingests job posts from multiple configurable sources (Telegram channels, websites, LinkedIn recruiters).
- **NEW: 16 job platform integrations** with toggleable enable/disable per platform.
- Normalizes and deduplicates jobs by `external_id`, content hash, and link hash.
- **NEW: Weighted scoring model** with skills, title, seniority, location components + explainability.
- Matches listings against resume + preferences with optional LLM reranking.
- Sends alerts through pluggable channels: email, SMS, Telegram, WhatsApp.
- Supports async queue-based notifications with retry and backoff.
- Generates CV recommendations and creates a Google Doc link (mock by default).
- Mobile-friendly dashboard for monitoring jobs, matches, alerts, and source management.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy, SQLite, pytest
- Jinja2 for dashboard templating
- Optional: OpenAI/Anthropic for LLM reranking

## Job Platforms (Ranked by Quality)

Platforms are ranked by data quality, freshness, and signal-to-noise ratio. Priority 1 = best sources (polled first).

| Priority | Platform | Description | Default |
|----------|----------|-------------|---------|
| 1 | **Y Combinator Work at a Startup** | Curated jobs from YC-backed startups with strong growth potential. | ✅ On |
| 2 | **Wellfound (AngelList Talent)** | Startup jobs with salary transparency and equity details upfront. | ✅ On |
| 3 | **a16z Talent** | Jobs from Andreessen Horowitz portfolio companies. | ✅ On |
| 4 | **VC Portfolio Boards** | Aggregated jobs from Sequoia, Greylock, and other top VC portfolios. | ✅ On |
| 5 | **Otta** | Personalized startup job matches with company culture insights. | ✅ On |
| 6 | **Built In** | Tech jobs with detailed company profiles and local market focus. | ✅ On |
| 7 | **Remote OK** | Verified remote jobs with salary data and company remote-work culture. | ✅ On |
| 8 | **We Work Remotely** | Largest remote work community with quality-vetted listings. | ✅ On |
| 9 | **Remotive** | Hand-picked remote jobs in tech, marketing, and customer support. | ✅ On |
| 10 | **Working Nomads** | Remote jobs curated for digital nomads and location-independent workers. | ❌ Off |
| 11 | **FlexJobs** | Vetted remote and flexible jobs, subscription-based with manual feed mode. | ❌ Off |
| 12 | **LinkedIn Jobs** | Massive job marketplace with company insights and easy apply options. | ❌ Off |
| 13 | **Glassdoor** | Job listings paired with company reviews and salary reports. | ❌ Off |
| 14 | **Indeed** | World's largest job aggregator with broad coverage across industries. | ❌ Off |
| 15 | **ZipRecruiter** | AI-powered job matching with one-click apply across multiple boards. | ❌ Off |
| 16 | **Google Jobs** | Aggregated job search across multiple sources via Google's index. | ❌ Off |

> **Tip:** Enable startup-focused boards (1-6) for best signal-to-noise. Large aggregators (12-16) have high volume but more noise.

## Scoring Formula

Jobs are scored against user CVs using a **deterministic weighted model** with optional LLM adjustment:

```
score = (
    0.40 × skills_overlap +
    0.25 × title_alignment +
    0.20 × seniority_fit +
    0.15 × location_fit
) × (1 - exclusion_penalty) × llm_adjustment
```

### Score Components

| Component | Weight | Description |
|-----------|--------|-------------|
| **Skills Overlap** | 40% | Overlap between job requirements and CV skills (keywords, tech stack) |
| **Title Alignment** | 25% | Job title match to CV experience and target roles |
| **Seniority Fit** | 20% | Level alignment: intern → junior → mid → senior → staff → director → C-level |
| **Location Fit** | 15% | Remote/hybrid/location compatibility with user preferences |
| **Exclusion Penalty** | 0 or 100% | Any excluded keyword found = score becomes 0 |
| **LLM Adjustment** | 0.5-1.5× | Optional AI rerank (requires `ENABLE_LLM_RERANKER=true`) |

### Score Breakdown Example

```json
{
  "total_score": 0.78,
  "components": {
    "skills": {"score": 0.85, "matched": ["python", "fastapi", "sql"], "missing": ["kubernetes"]},
    "title": {"score": 0.70, "reason": "Related domain: engineer"},
    "seniority": {"score": 0.80, "job_level": "senior", "cv_level": "mid", "reason": "Close match"},
    "location": {"score": 1.0, "reason": "Remote role matches preference"}
  },
  "exclusion_penalty": 0.0,
  "excluded_found": [],
  "llm_adjustment": 1.0
}
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Job Platforms (16 sources)               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐  │
│  │ YC Startup │ │ Wellfound  │ │   Otta     │ │Remote OK │  │
│  │ a16z       │ │ Built In   │ │ LinkedIn   │ │  Indeed  │  │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────┬─────┘  │
└────────┼──────────────┼──────────────┼─────────────┼────────┘
         │              │              │             │
         ▼              ▼              ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│            Platform Adapters (priority-ordered polling)     │
└─────────────────────────┬───────────────────────────────────┘
                          │
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
│  - Polls enabled sources by platform priority               │
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
│  CV Generator   │◀────│   Scorer         │◀────│   User Prefs    │
│  (Docs API)     │     │   (weighted)     │     │                 │
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

# View dashboard (includes platform toggles + source management)
open http://127.0.0.1:8000/dashboard

# Check queue stats
curl http://127.0.0.1:8000/queue-stats
```

## Platform Management API

```bash
# List all platforms with settings
curl http://127.0.0.1:8000/api/platforms

# Get platform priority order
curl http://127.0.0.1:8000/api/platforms/priority

# Enable a platform
curl -X POST http://127.0.0.1:8000/api/platforms/linkedin_jobs/enable

# Disable a platform
curl -X POST http://127.0.0.1:8000/api/platforms/indeed/disable

# Get single platform info
curl http://127.0.0.1:8000/api/platforms/wellfound
```

## Scoring API

```bash
# Score a job against CV
curl -X POST http://127.0.0.1:8000/api/score \
  -H "Content-Type: application/json" \
  -d '{
    "job_title": "Senior Python Engineer",
    "job_description": "Python, FastAPI, SQL developer needed. Remote.",
    "job_company": "TechCorp",
    "cv_text": "Senior Python developer with FastAPI and SQL experience",
    "required_keywords": ["python"],
    "excluded_keywords": ["solidity"],
    "user_prefers_remote": true
  }'

# Get scoring weights and formula
curl http://127.0.0.1:8000/api/score/weights
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
- **Overview**: Stats, queue status, scoring formula
- **Platforms**: Toggle job platforms on/off, see descriptions and status
- **Sources**: Add/edit/delete custom sources (Telegram, websites)
- **Jobs**: Recent ingested job posts
- **Matches**: Matches with scores and doc links
- **Alerts**: Notification statuses per channel

**Platform Management UI:**
- Toggle switches for each platform
- One-sentence description for each platform
- Status indicator (enabled/disabled, last checked)
- Priority ranking displayed

**Source Management UI:**
- Add Telegram channels (paste `@channel` or `t.me/channel` link)
- Add website URLs for job page scraping
- Track LinkedIn recruiters (compliance-safe passive tagging)
- Test source connectivity
- Activate/deactivate sources
- View error counts and last check times

JSON API available at `/api/dashboard`.

## Phase 5 Features: Platform Toggles & Scoring

### Platform Toggle Settings

| Type | Description | Polling | Notes |
|------|-------------|---------|-------|
| `wellfound` | Wellfound (AngelList Talent) | Active | Startup jobs |
| `yc_work_at_startup` | YC Work at a Startup | Active | YC portfolio |
| `otta` | Otta | Active | Requires auth |
| `built_in` | Built In | Active | Local tech hubs |
| `a16z_talent` | a16z Talent | Active | a16z portfolio |
| `vc_portfolio_boards` | VC Portfolio Boards | Active | Generic VC adapter |
| `linkedin_jobs` | LinkedIn Jobs | Active | Compliance-sensitive |
| `indeed` | Indeed | Active | High volume |
| `ziprecruiter` | ZipRecruiter | Active | Requires auth |
| `glassdoor` | Glassdoor | Active | Requires auth |
| `google_jobs` | Google Jobs | Aggregator | May duplicate |
| `remote_ok` | Remote OK | RSS feed | Remote jobs |
| `we_work_remotely` | We Work Remotely | RSS feed | Remote jobs |
| `flexjobs` | FlexJobs | Manual | Subscription |
| `remotive` | Remotive | RSS feed | Remote jobs |
| `working_nomads` | Working Nomads | RSS feed | Digital nomads |

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
| `app/models/platforms.py` | **NEW: Platform definitions and priority ranking** |
| `app/models/platform_settings.py` | **NEW: Platform toggle settings model** |
| `app/api/platforms.py` | **NEW: Platform toggle + scoring API** |
| `app/services/scoring.py` | **NEW: Weighted scoring model with explainability** |
| `app/adapters/platform_adapters.py` | **NEW: Platform adapters (scaffolds)** |
| `app/adapters/ingestion.py` | Legacy Telegram adapter |
| `app/adapters/source_adapters.py` | Source adapters for Telegram/website/LinkedIn |
| `app/api/sources.py` | Source CRUD API |
| `app/models/sources.py` | JobSource data model |
| `app/services/source_poller.py` | Background source polling worker |
| `app/services/matching.py` | Legacy scoring (now wraps scoring.py) |
| `app/services/reranker.py` | LLM prompts |
| `app/services/notifier.py` | Notification channels |
| `app/services/docs.py` | Doc templates |
| `app/templates/dashboard.html` | Dashboard UI with platform toggles |

## Testing

```bash
# Run all tests
python3 -m pytest -v

# Run specific test files
python3 -m pytest tests/test_platforms.py -v   # NEW: Platform tests
python3 -m pytest tests/test_scoring.py -v     # NEW: Scoring tests
python3 -m pytest tests/test_dedupe.py -v
python3 -m pytest tests/test_queue.py -v
python3 -m pytest tests/test_reranker.py -v
python3 -m pytest tests/test_sources.py -v

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
| **GET** | `/api/platforms` | **List all platforms with settings** |
| **GET** | `/api/platforms/priority` | **Get priority-ordered platform list** |
| **GET** | `/api/platforms/{platform}` | **Get single platform info** |
| **POST** | `/api/platforms/{platform}/enable` | **Enable platform** |
| **POST** | `/api/platforms/{platform}/disable` | **Disable platform** |
| **POST** | `/api/score` | **Score job against CV with breakdown** |
| **GET** | `/api/score/weights` | **Get scoring weights and formula** |
| GET | `/api/sources` | List all sources |
| POST | `/api/sources` | Create new source |
| GET | `/api/sources/{id}` | Get source by ID |
| PUT | `/api/sources/{id}` | Update source |
| DELETE | `/api/sources/{id}` | Delete source |
| POST | `/api/sources/{id}/activate` | Activate source |
| POST | `/api/sources/{id}/deactivate` | Deactivate source |
| POST | `/api/sources/{id}/test` | Test source connectivity |

## Data Models

### PlatformSetting

```python
class PlatformSetting:
    id: int
    platform: str          # Platform type (wellfound, linkedin_jobs, etc.)
    enabled: bool          # Whether platform is enabled for polling
    user_id: int | None    # Owner (NULL = global setting)
    last_checked: datetime # Last successful check
    last_error: str | None # Last error message
    error_count: int       # Consecutive errors
```

### JobSource

```python
class JobSource:
    id: int
    type: str              # telegram_channel | telegram_public | website | linkedin_recruiter
    identifier: str        # Channel/URL/profile identifier
    name: str              # Display name
    status: str            # active | inactive | error
    user_id: int | None    # Owner (NULL = global source)
    config: str | None     # JSON config for source-specific settings
    last_checked: datetime # Last successful check
    last_error: str | None # Last error message
    error_count: int       # Consecutive errors (resets on success)
```

## License

MIT
