# Rocky

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- npm

## First-time setup

### 1. Create a Python virtual environment

From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
```

If you need a different Python executable, use the full path with `&`.

### 2. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Install backend dependencies

```powershell
pip install -r rocky-backend\requirements.txt -r granite-llm-server\requirements.txt
```

### 4. Install frontend dependencies

```powershell
Push-Location rocky-interface
npm install
Pop-Location
```

### 5. Create the environment file

For the complete local stack, copy the root [.env.example](.env.example) to `.env` and replace the example hidden-key secret. The service-level examples are available when a service needs to be run or configured independently.

For production, set `ROCKY_DB_BACKEND=mongodb` and provide `ROCKY_MONGODB_URI`.

### Minimum required variables

Development minimum:

- Root `.env`: keep the development bind, Mongita, Ollama, and shared-path values from [.env.example](.env.example), then replace `ROCKY_HIDDEN_API_KEY_SECRET`.

For development Microsoft OAuth, set:

- [rocky-interface/.env](rocky-interface/.env): `PUBLIC_ENABLE_MICROSOFT_OAUTH=true`, `PUBLIC_MICROSOFT_CLIENT_ID`, the specific `PUBLIC_MICROSOFT_TENANT_ID`, `ROCKY_SESSION_SECRET`, and `ROCKY_INTERNAL_PROXY_SECRET`
- [rocky-backend/.env](rocky-backend/.env): `ROCKY_ENABLE_MICROSOFT_OAUTH=true` and the same `ROCKY_INTERNAL_PROXY_SECRET`

Production minimum:

- [rocky-backend/.env](rocky-backend/.env): `ROCKY_APP_ENV=production`, `ROCKY_DB_BACKEND=mongodb`, `ROCKY_MONGODB_URI`, `ROCKY_INTERNAL_PROXY_SECRET`, `ROCKY_ENABLE_DB_INSPECTOR=false`, `ROCKY_API_HOST`, `ROCKY_API_PORT`
- [rocky-interface/.env](rocky-interface/.env): `PUBLIC_APP_ENV=production`, `PUBLIC_API_BASE_URL`, `PUBLIC_MICROSOFT_CLIENT_ID`, the specific `PUBLIC_MICROSOFT_TENANT_ID`, `ROCKY_SESSION_SECRET`, the same `ROCKY_INTERNAL_PROXY_SECRET`, `ROCKY_WEB_HOST`, `ROCKY_WEB_PORT`, `ROCKY_ALLOWED_HOSTS`

Auth mode behavior:

- Development: preview auth by default; Microsoft OAuth enabled only when override env variables are true.
- Testing: preview auth only.
- Production: Microsoft OAuth only.

Both launchers load `.env` and `.env.local` from the repo root, backend, and frontend directories.

## Running locally

### Development

Run both backend and frontend together:

```powershell
python run-dev.py --mode both
```

Normal startup preserves the existing local database. To load the fixture data explicitly:

```powershell
python run-dev.py --mode both --seed
```

Other modes:

- `python run-dev.py --mode backend`
- `python run-dev.py --mode frontend`

### Production preview

Build the frontend, start the backend in production mode, and launch the frontend preview server:

```powershell
python run-production.py
```

Backend-only production mode:

```powershell
python run-production.py --mode backend
```

## Backend

Backend runs on `http://127.0.0.1:5001` by default.

Useful endpoints:

- `GET /health`
- `GET /users`
- `GET /courses`
- `GET /analytics/current`
- `GET /analytics/summary`
- `GET /analytics/timeseries`
- `GET /analytics/hardware`
- `GET /analytics/breakdown`
- `GET /analytics/requests`
- `GET /widgets/default`
- `GET /help/faq`

Admin-only endpoints require the admin headers passed by the Svelte proxy layer.
The frontend `Analytics` frame consumes these endpoints as a responsive
monitoring workspace with throughput trends, bounded Granite hardware history,
attribution breakdowns, and sanitized request inspection.

## Chat API

The student-facing endpoint is `POST /v1/responses` on port `5003` locally. It accepts `Authorization: Bearer sk_kent_...`, public model name `rocky`, and a JSON `input` string or text-message array. The configured Ollama model stays an internal server detail.

The documented Python client uses `requests`; Rocky has no runtime dependency on an external AI-provider SDK.

## Seed data

Backend-owned fixtures live in:

- `rocky-backend/seed-data/account/users.json`
- `rocky-backend/seed-data/courses/courses.json`
- `rocky-backend/seed-data/analytics/kpis.json`
- `rocky-backend/seed-data/analytics/activity.json`
- `rocky-backend/seed-data/widgets/widgets.json`
- `rocky-backend/seed-data/help/faq.json`

Seed the backend database with:

```powershell
python rocky-backend\seed_from_backend.py
```

## Tests

Backend unit tests:

```powershell
python -m unittest discover -s run-test/backend -p "test_*.py" -v
```

Frontend browser tests depend on a running browser and Chromium/WebDriver setup:

```powershell
python -m unittest discover -s run-test/frontend -p "test_*.py" -v
```
## Credits

This project is based on the original Rocky repository developed in Kent State University's Software Engineering course.

Original repository:
https://github.com/Spring-2026-Software-Engineering/Rocky

This repository preserves the original commit history and contributors while continuing development for the Kent State Rocky AI platform.
