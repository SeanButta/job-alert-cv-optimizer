# job-alert-cv-optimizer

Automated job alert + CV optimization MVP.

## What it does
- Ingests Telegram job posts (sample adapter by default, real Telegram Bot API via env flag).
- Normalizes and deduplicates by `external_id`.
- Matches listings against resume + preferences.
- Sends alerts through pluggable channels: email, SMS, Telegram, WhatsApp.
- Generates CV recommendations and creates a Google Doc link (mock by default, real Docs API when enabled).

## Stack
- Python, FastAPI, SQLAlchemy, SQLite, pytest.

## Safe defaults
- Real external calls are **OFF** by default.
- Enable selectively via env flags:
  - `ENABLE_REAL_NOTIFICATIONS=true`
  - `ENABLE_REAL_GOOGLE_DOCS=true`
  - `ENABLE_REAL_TELEGRAM_INGEST=true`

## Run locally
```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -q
uvicorn app.main:app --reload
```

Then:
```bash
curl -X POST http://127.0.0.1:8000/seed
curl -X POST http://127.0.0.1:8000/run-demo
```

## Real connector notes
### Telegram ingest
- Set `TELEGRAM_BOT_TOKEN`.
- Add bot to source channel/group and ensure it can receive updates.
- Optional filter: `TELEGRAM_SOURCE_CHAT_ID`.

### Notifications
- Email: SendGrid (`SENDGRID_API_KEY`, `ALERT_FROM_EMAIL`)
- SMS: Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`)
- Telegram send: `TELEGRAM_BOT_TOKEN`
- WhatsApp: Meta Cloud API (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`)

### Google Docs
- Service account JSON path in `GOOGLE_SERVICE_ACCOUNT_JSON`
- Optional share target in `GOOGLE_DOC_SHARE_WITH`

## Files to customize
- `app/adapters/ingestion.py` for additional job board scrapers
- `app/services/matching.py` for richer scoring / LLM rerank
- `app/services/notifier.py` for provider retry/queue hardening
- `app/services/docs.py` for doc template/versioning
