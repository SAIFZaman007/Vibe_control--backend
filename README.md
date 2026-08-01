# Vibe Control — Backend (FastAPI)

FastAPI + SQLAlchemy + SQLite + JWT. Managed with **uv**.

## Run

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"   # -> SECRET_KEY in .env
uv sync
uv run uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## AI engine

`STYLE_ENGINE` in `.env`:
- `pillow` — default, no extra install
- `tfhub` — real neural style transfer: `uv sync --extra ai`
- `replicate` — paid API: `uv sync --extra paid` + set `REPLICATE_API_TOKEN`

## Layout

- `app/config.py` — settings
- `app/database.py` — engine/session
- `app/models/` — ORM models
- `app/schemas/` — Pydantic models
- `app/core/` — JWT, hashing, auth dependencies
- `app/routers/` — auth, users, images, filters
- `app/services/` — style transfer, style catalog, storage, email

See the root `README.md` for full details and deployment.
