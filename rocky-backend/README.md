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

Configuration is validated at startup. Boolean values must be exactly `true`
or `false`; ports and hardware limits must be in range; and enabled hardware
telemetry requires an absolute HTTP(S) metrics URL without embedded
credentials. Invalid values fail immediately with the setting name.

Core variables:

- `ROCKY_APP_ENV`: `development` | `testing` | `production`
- `ROCKY_DB_BACKEND`: `mongita` | `mongodb`
- `ROCKY_MONGODB_URI`: required in production
- `ROCKY_DB_NAME`: database name
- `ROCKY_MONGITA_PATH`: local data directory shared with `api-rocky`
- `ROCKY_API_HOST` and `ROCKY_API_PORT`: backend bind settings
- `ROCKY_HIDDEN_API_KEY_SECRET`: private derivation secret used for built-in
  web-chat keys; production requires at least 32 characters
- `ROCKY_INTERNAL_PROXY_SECRET`: private secret shared with the Svelte server;
  production requires at least 32 characters

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
- `ROCKY_HIDDEN_API_KEY_SECRET` set to the same value used by SvelteKit
- `ROCKY_INTERNAL_PROXY_SECRET` set to the same value as the Svelte server

The management API is a server-to-server service for SvelteKit, not a browser
API, so it intentionally does not emit cross-origin CORS headers. Browser code
should use SvelteKit's `/api/backend/...` routes. In development only, a missing
`ROCKY_INTERNAL_PROXY_SECRET` permits identity headers from direct IPv4 or IPv6
loopback peers. Any shared-interface or reverse-proxy setup must configure the
same secret in the backend and SvelteKit environments.

## Run backend

```powershell
python main.py
```

Default URL: `http://127.0.0.1:5001`

The canonical widget catalog lives in `seed-data/widgets/widgets.json` and is exposed through the widget endpoint.

Health check: `GET /health`

## Telemetry analytics

Analytics are calculated from the permanent `telemetry_interactions` records
written by `api-rocky`. The Svelte server proxy supplies the authenticated user
headers together with the private proxy secret, and every analytics endpoint
enforces administrator access in Flask.

Available endpoints:

- `GET /analytics/current`: active requests and lifetime counters.
- `GET /analytics/summary?window=24h`: outcomes, token usage, RPM/TPM,
  latency percentiles, model timing/throughput, and rate-limit incidents.
- `GET /analytics/timeseries?window=24h&bucket=hour`: zero-filled time buckets.
- `GET /analytics/hardware?window=24h&bucket=hour`: bounded Granite hardware
  history aligned with workload, latency, model-load time, and generation speed.
- `GET /analytics/breakdown?window=24h&dimension=user`: grouped metrics for
  `user`, `course`, `key`, `group`, `model`, `source`, or `outcome`.
- `GET /analytics/requests?window=24h&limit=50`: filtered recent-request index.
- `GET /analytics/requests/<request_id>`: the complete stored request record,
  including the recorded prompt and response text.
- `PATCH /analytics/requests/<request_id>/review`: update an administrative
  review and append its change history.
- `GET /analytics/export?format=json&window=24h`: download up to 10,000
  filtered request records, including the stored prompt and response.
- `GET /audit/export?format=csv&date_from=2026-08-01`: download filtered
  administrative audit events.

Analytics summary, time-series, hardware-workload, breakdown, request-list,
and export routes share the `user_id`, `course_id`, `key_id`, `model`,
`operation`, `outcome`, `source`, `error_type`, `flagged`, and `review_status`
filters. Rate-limit enforcement records use `rate_limit_exceeded`; limiter
storage or identity failures remain separate and are reported as unavailable.
Review status is one of `unreviewed`, `in_review`, or `resolved`. A review
update accepts `flagged`, `flag_reasons`, `status`, and `notes`; flagged
requests require at least one reason. Supported reasons are
`academic_integrity`, `harmful_content`, `security_abuse`, `policy_violation`,
`system_quality`, and `other`, and notes are limited to 4,000 characters.

Each update records the administrator and timestamp, appends the previous and
new values to the telemetry record's `review_history`, and writes a metadata-only
`telemetry-review` audit event. The audit event records the review transition
but does not make another copy of the stored prompt or response.

Review updates use a version number. If another administrator saves the same
review first, the stale update receives `409 Conflict` and must be reloaded
instead of silently overwriting the newer review.

The current snapshot derives active and unresolved request counts from open
interaction records. Requests older than four minutes are reported as
unresolved rather than remaining active after an interrupted service process.
Aggregate and request-list queries exclude stored prompt and response content;
full content is retrieved only by the individual request-detail endpoint.
Valid prompt, instruction, and model-response text is retained verbatim. API
keys, authorization headers, cookies, internal service tokens, and stored key
hashes remain excluded because they are authentication material rather than
conversation content.

Supported windows are `15m`, `1h`, `6h`, `24h`, `7d`, and `30d`. Time-series
buckets are `minute`, `hour`, and `day`; combinations producing more than 1,000
rows are rejected. Breakdown results are capped at 100 rows and request indexes
at 200 rows. The older `/analytics/kpis` and `/analytics/activity` endpoints now
return live compatibility views rather than fixture values.

Exports are administrator-only, generated directly in memory, and never left
as files on the server. JSON preserves stored content exactly. CSV protects
spreadsheet programs from formula execution by prefixing cells beginning with
`=`, `+`, `-`, or `@`; this changes only the downloaded CSV representation.
Every successful export appends a metadata-only audit event.

### Hardware sampler

Hardware history uses one small standalone pull sampler rather than a scheduler
inside each Gunicorn worker. Enable it with the `ROCKY_HARDWARE_*` variables in
`.env.example`, then run:

```sh
python sample_hardware.py
```

`run-dev.py --mode both` starts it automatically when enabled. Production uses
`rocky-hardware-sampler.service`. Snapshots expire independently after 90 days
by default; permanent request records are unaffected. The configured metrics
URL must point to the endpoint running on Granite if Granite is the host being
measured. Production requires a shared metrics token.

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

The analytics JSON files remain only as legacy fixture data. They are not used
by the live telemetry endpoints.

## Tests

From repository root:

macOS/Linux:

```sh
PYTHONPATH=rocky-backend python -m unittest discover -s run-test/backend -p "test_*.py" -v
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "rocky-backend"
python -m unittest discover -s run-test/backend -p "test_*.py" -v
```

## Development guardrails

- Keep authorization checks in backend routes, not only frontend.
- Treat frontend-provided role/email headers as session-context data from trusted proxy routes.
- Add validation in `backend/validation.py` for any new mutable endpoint payloads.
- Keep private data access in backend code paths only.
