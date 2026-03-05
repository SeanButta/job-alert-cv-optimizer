#!/usr/bin/env bash
set -e
python -m pip install -r requirements.txt
pytest -q
python - <<'PY'
from app.main import seed, run_demo
print(seed())
print(run_demo())
PY
