# Rocky

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- Ollama, with the model named by `OLLAMA_MODEL` installed locally when you want
  to run inference on the development machine

## First-time setup

### 1. Create a Python virtual environment

From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
```

If you need a different Python executable, use the full path with `&`.

On macOS or Linux:

```sh
python3 -m venv .venv
```

### 2. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

On macOS or Linux:

```sh
source .venv/bin/activate
```

### 3. Install backend dependencies

```powershell
pip install -r rocky-backend\requirements.txt -r granite-llm-server\requirements.txt -r run-test\requirements-compat.txt
```

On macOS or Linux, use `/` instead of `\` in those paths.

The compatibility requirements are used only by the test and coverage tools;
Rocky's runtime does not depend on an external AI-provider SDK or coverage
collector.

### 4. Install frontend dependencies

```powershell
Push-Location rocky-interface
npm install
Pop-Location
```

### 5. Create the environment file

For the complete local stack, copy the root [.env.example](.env.example) to `.env` and replace its example secret values. The service-level examples contain the same shared names and placeholder values when a service needs to be configured independently. Shared secrets must have identical values in every service that uses them.

For production, set `ROCKY_DB_BACKEND=mongodb` and provide `ROCKY_MONGODB_URI`.

### Minimum required variables

Development minimum:

- Root `.env`: keep the development bind, Mongita, Ollama, model, and shared-path values from [.env.example](.env.example), then replace the four example values for `ROCKY_HIDDEN_API_KEY_SECRET`, `ROCKY_SESSION_SECRET`, `ROCKY_INTERNAL_PROXY_SECRET`, and `ROCKY_GRANITE_TOKEN` with independent random secrets.

For development Microsoft OAuth, set:

- `rocky-interface/.env`: start from [rocky-interface/.env.example](rocky-interface/.env.example), then set `PUBLIC_ENABLE_MICROSOFT_OAUTH=true`, `PUBLIC_MICROSOFT_CLIENT_ID`, the specific `PUBLIC_MICROSOFT_TENANT_ID`, `ROCKY_SESSION_SECRET`, and `ROCKY_INTERNAL_PROXY_SECRET`
- `rocky-backend/.env`: start from [rocky-backend/.env.example](rocky-backend/.env.example), then set `ROCKY_ENABLE_MICROSOFT_OAUTH=true` and the same `ROCKY_INTERNAL_PROXY_SECRET`

Production-preview minimum:

- `rocky-backend/.env`: start from [rocky-backend/.env.example](rocky-backend/.env.example), then set `ROCKY_APP_ENV=production`, `ROCKY_DB_BACKEND=mongodb`, `ROCKY_MONGODB_URI`, `ROCKY_HIDDEN_API_KEY_SECRET`, `ROCKY_INTERNAL_PROXY_SECRET`, `ROCKY_ENABLE_DB_INSPECTOR=false`, `ROCKY_API_HOST`, and `ROCKY_API_PORT`
- `rocky-interface/.env`: start from [rocky-interface/.env.example](rocky-interface/.env.example), then set `PUBLIC_APP_ENV=production`, `PUBLIC_API_BASE_URL`, `PUBLIC_MICROSOFT_CLIENT_ID`, the specific `PUBLIC_MICROSOFT_TENANT_ID`, the same `ROCKY_HIDDEN_API_KEY_SECRET`, `ROCKY_SESSION_SECRET`, the same `ROCKY_INTERNAL_PROXY_SECRET`, `ROCKY_WEB_HOST`, `ROCKY_WEB_PORT`, and `ROCKY_ALLOWED_HOSTS`

That preview runs only the management backend and built frontend. A real Rocky
deployment also requires the Chat API, Granite bridge, Ollama, Nginx, and their
shared production settings. Follow the authoritative
[Ubuntu deployment guide](deploy/README.md) instead of treating the preview
settings as a complete deployment recipe.

Auth mode behavior:

- Development: preview auth by default; Microsoft OAuth enabled only when override env variables are true.
- Testing: preview auth only.
- Production: Microsoft OAuth only.

The development launcher loads `.env` and `.env.local` from the repository root and all four service directories. The production-preview launcher loads them from the repository root, backend, and frontend directories. Root values load first; service-level `.env.local` files are the intended place for service-specific overrides.

Configuration is validated when each service starts. Boolean values must be
exactly `true` or `false`; ports, limits, and timeouts must be within their
documented ranges; and service URLs must be absolute HTTP(S) URLs without
embedded credentials, query strings, or fragments. Omitted optional settings
use the defaults shown in the example files. Run
`python manage.py doctor --skip-network` to validate the combined configuration
without contacting any services.

## Running locally

### Development

Run both backend and frontend together:

```powershell
python run-dev.py --mode both
```

This launches the local Granite bridge, Chat API, management backend, and
frontend. Ollama must already be running with the configured model for chat
generation to succeed. `python manage.py doctor` performs the deeper readiness
checks when you need to verify inference, not only process startup.

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
attribution breakdowns, and complete recorded prompt and response inspection.

## Chat API

The student-facing endpoints are `POST /v1/responses` and `GET /v1/models` on
port `5003` locally. They accept `Authorization: Bearer sk_kent_...`. The
advertised model is configured with `ROCKY_PUBLIC_MODEL` and should match the
installed `OLLAMA_MODEL`. Clients should discover it through `GET /v1/models`.

The documented Python client uses `requests`; Rocky has no runtime dependency on an external AI-provider SDK.

Streaming and base64 image input are disabled-by-default capabilities. When
enabled consistently across the relevant services, Rocky provides OpenAI-style
Responses SSE, bounded JPEG/PNG/static-WebP analysis, incremental built-in chat
rendering with buffered fallback, and durable image-aware conversation history.
Student examples, SDK compatibility coverage, deployment smoke checks, and the
release checklist verify every capability the selected model advertises. The
precise public and internal contracts are in
[`api-rocky/STREAMING_AND_IMAGE_CONTRACT.md`](api-rocky/STREAMING_AND_IMAGE_CONTRACT.md).

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

Run the complete local release gate from an activated project environment:

```sh
python run-test/test_all.py
```

This covers backend, Granite, frontend unit/type/format/build checks, and the
browser suite. Use `--skip-browser` only for an intermediate run on a machine
without a usable browser. The individual commands remain useful while
developing a focused change.

Measure Python and frontend source coverage separately from the browser release
gate:

```sh
python run-test/coverage_all.py
```

This command enforces the conservative baseline thresholds stored in
`.coveragerc` and `rocky-interface/vite.config.ts`. See
[`run-test/README.md`](run-test/README.md) for what is included in each metric.

Backend unit tests:

macOS/Linux:

```sh
PYTHONPATH=rocky-backend python -m unittest discover -s run-test/backend -p "test_*.py" -v
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "rocky-backend"
python -m unittest discover -s run-test/backend -p "test_*.py" -v
```

Frontend browser tests depend on a running browser and Chromium/WebDriver setup:

macOS/Linux:

```sh
PYTHONPATH=run-test:rocky-backend python -m unittest discover -s run-test/frontend -p "test_*.py" -v
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "run-test;rocky-backend"
python -m unittest discover -s run-test/frontend -p "test_*.py" -v
```

## Credits

This project is based on the original Rocky repository developed in Kent State University's Software Engineering course.

Original repository:
https://github.com/Spring-2026-Software-Engineering/Rocky

This repository preserves the original commit history and contributors while continuing development for the Kent State Rocky AI platform.
