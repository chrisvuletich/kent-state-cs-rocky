# Rocky Backend (Backend Developer Guide)

This README is for developers working in the Flask backend under `rocky-backend`.

## What this project owns

- API endpoints and authorization enforcement.
- Role-based access to users/courses/analytics data.
- Database reads/writes (Mongita for local fallback, MongoDB for production).
- Seeded fixture ingestion under `seed-data`.

## Prerequisites

- Python 3.11+
- pip

## Environment setup

Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Environment variables

Copy `.env.example` to `.env`, then set values for your target environment.

Core variables:

- `ROCKY_APP_ENV`: `development` | `testing` | `production`
- `ROCKY_DB_BACKEND`: `mongita` | `mongodb`
- `ROCKY_MONGODB_URI`: required in production
- `ROCKY_DB_NAME`: database name
- `ROCKY_MONGITA_PATH`: local data directory shared with `api-rocky`
- `ROCKY_API_HOST` and `ROCKY_API_PORT`: backend bind settings

Security-related toggles:

- `ROCKY_ENABLE_DB_INSPECTOR`: should be `false` in production
- `ROCKY_ENABLE_MICROSOFT_OAUTH`: optional development override, ignored in production/testing

Auth mode behavior:

- development: preview login by default; Microsoft OAuth enabled when `ROCKY_ENABLE_MICROSOFT_OAUTH=true`
- testing: preview login only
- production: Microsoft OAuth only

Production baseline:

- `ROCKY_APP_ENV=production`
- `ROCKY_DB_BACKEND=mongodb`
- `ROCKY_MONGODB_URI` set to valid credentials
- `ROCKY_ENABLE_DB_INSPECTOR=false`

## Run backend

```powershell
python main.py
```

Default URL: `http://127.0.0.1:5001`

The canonical widget catalog lives in `seed-data/widgets/widgets.json` and is exposed through the widget endpoint.

Health check: `GET /health`

## Seed data and seeding flow

Seed fixtures are backend-owned in `seed-data`:

- `seed-data/account/users.json`
- `seed-data/courses/courses.json`
- `seed-data/analytics/kpis.json`
- `seed-data/analytics/activity.json`
- `seed-data/widgets/widgets.json`
- `seed-data/help/faq.json`

Seeding code lives in:

- `seed-data/seed_data.py` (shared seeding logic)
- `seed_from_backend.py` (shared seeding script entrypoint)

Run seeding:

```powershell
python seed_from_backend.py
```

## Tests

From repository root:

```powershell
python -m unittest discover -s run-test/backend -p "test_*.py" -v
```

## Development guardrails

- Keep authorization checks in backend routes, not only frontend.
- Treat frontend-provided role/email headers as session-context data from trusted proxy routes.
- Add validation in `backend/validation.py` for any new mutable endpoint payloads.
- Keep private data access in backend code paths only.
