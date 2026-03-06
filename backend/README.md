# Backend

FastAPI service + the HowlHouse game engine.

## Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .

pytest
uvicorn howlhouse.api.main:app --reload --port 8000
```
