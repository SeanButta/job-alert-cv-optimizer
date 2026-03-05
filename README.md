# job-alert-cv-optimizer

Automated job alert + CV optimization MVP.

## What it does
- Ingests sample Telegram job posts (adapter scaffolded for real channels).
- Normalizes and deduplicates by `external_id`.
- Matches listings against resume + preferences.
- Sends mock alerts (email/SMS/Telegram/WhatsApp abstraction point).
- Generates CV recommendations and returns a mock Google Doc link.

## Stack
- Python, FastAPI, SQLAlchemy, SQLite, pytest.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then:
```bash
curl -X POST http://127.0.0.1:8000/seed
curl -X POST http://127.0.0.1:8000/run-demo
```

## Tests
```bash
pytest -q
```

## Notes
- All outbound notifications + Google Docs are mocked by default.
- Toggle real integrations with env vars and provider implementations in `app/services/notifier.py` and `app/services/docs.py`.
