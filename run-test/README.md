# Test Strategy and Automation

This folder centralizes isolated automated tests for both backend and frontend.

## Test Design (best-practice checklist)

- Keep tests isolated from production data by using an in-memory backend database.
- Use deterministic fixture data with both valid and invalid records.
- Validate API behavior for both success and failure paths.
- Use end-to-end browser tests for critical user-path smoke coverage.
- Run everything in CI on pushes and pull requests for fast feedback.

## Backend tests

Path: run-test/backend

- seed_data.json: mixed valid and invalid records for validation coverage.
- test_seed_data_shape.py:
  - checks the real backend seed data has one admin, two instructors, four students, and six courses.
- test_backend_validation.py:
  - verifies accepted data is inserted;
  - verifies invalid data is rejected;
  - verifies API endpoints return 400 for malformed payloads.
- test_audit_events.py:
  - verifies successful administrative mutations create trusted audit events;
  - verifies rejected mutations do not create events and sensitive fields are removed;
  - verifies account deactivation suspends owned API keys.
- test_user_settings.py:
  - verifies per-user settings are readable and writable.
- test_course_api_history.py:
  - verifies API history records grouped and ungrouped usage.
- test_authorization_matrix.py:
  - keeps student, instructor, administrator, inactive-account, closed-course,
    and trusted-proxy expectations in one data-driven role matrix;
  - verifies students can create only their own course key.
- test_database_counts.py:
  - verifies the backup/restore count baseline is deterministic and read-only.

Install the backend and compatibility-test dependencies with:

- `pip install -r rocky-backend/requirements.txt -r run-test/requirements-compat.txt`

`openai` and `coverage` are test-only dependencies. The compatibility test
verifies that the official Python client can consume Rocky's OpenAI-compatible
HTTP responses; students may continue to use `requests`, `curl`, or any other
HTTP client.

## Frontend tests

Path: run-test/frontend

The compact viewport, state, and UI acceptance matrix is documented
in [UI_UX_ACCEPTANCE.md](UI_UX_ACCEPTANCE.md). Keep new UI regression coverage
inside the existing Selenium harness unless a future requirement cannot be
tested there.

- test_preview_login_chromedriver.py:
  - opens login preview;
  - signs into a mock admin session;
  - confirms the dashboard loads without document overflow at all five
    reference viewports.
- test_dialog_accessibility_chromedriver.py:
  - verifies modal dialogs move and contain keyboard focus;
  - verifies Escape closes the topmost surface and restores its opener;
  - verifies modal backgrounds become inert;
  - verifies mobile navigation and chat drawers expose their expanded state;
  - verifies Dashboard, course, and Account disclosures manage focus predictably.
- test_responsive_layout_chromedriver.py:
  - verifies short-laptop and landscape navigation remains locally scrollable;
  - verifies wide user, audit, API-key, and analytics tables contain their overflow;
  - verifies analytics summaries wrap at landscape and narrow-phone widths.
- test_form_semantics_chromedriver.py:
  - verifies field errors are exposed through `aria-invalid` and `aria-describedby`;
  - verifies user, course, and analytics tabs support roving keyboard focus;
  - verifies sortable table headers are keyboard-operable and announce their direction;
  - verifies each route exposes one current sidebar destination.
- test_chat_resilience_chromedriver.py:
  - verifies confirmed chat outages disable sending without locking or clearing the draft;
  - verifies the institutional logging notice remains visible, readable, and associated with the composer;
  - verifies failed history refreshes keep cached conversations visible and recover through Retry.
- test_theme_and_inactive_chromedriver.py:
  - verifies light and dark account preferences survive reload;
  - checks the primary dark-theme text tokens against the 4.5:1 contrast target;
  - verifies inactive users receive a truthful sign-out path and signed-out users cannot reopen it.
- test_css_motion_chromedriver.py:
  - emulates the operating system's reduced-motion preference;
  - verifies Credits remain stationary, readable, and scrollable inside their
    live region;
  - verifies the explicit system font and zero-duration component transitions.
- test_view_titles_chromedriver.py:
  - opens login preview (auth gate aware);
  - signs into mock session;
  - clicks each sidebar view;
  - asserts each view renders the correct page title;
  - verifies course deep links across reload and browser history;
  - verifies remembered-view fallback and safe invalid/unauthorized links;
  - verifies secondary Account, Help, and Admin links use canonical URLs.
- test_admin_management_chromedriver.py:
  - creates a role-aware external whitelist account;
  - verifies the resulting mutation appears in the Admin audit preview.
- test_priority_reliability_chromedriver.py:
  - verifies course cards use addressable link semantics;
  - verifies completed streamed conversations become addressable in the URL;
  - verifies existing keys warn before regeneration;
  - checks independent Admin Dashboard sections, shareable analytics state, and
    desktop/mobile chat layout.
- test_role_journeys_chromedriver.py:
  - verifies student key generation, copy-once disclosure, and dismissal;
  - verifies instructor student/group key controls and unrelated-course hiding;
  - verifies logout clears account-specific browser state and protects `/`.

## Local run commands

From the repository root on macOS/Linux:

- Complete local release gate: `python run-test/test_all.py`
- Release gate without Selenium: `python run-test/test_all.py --skip-browser`
- Python and frontend code coverage: `python run-test/coverage_all.py`
- Backend only: `PYTHONPATH=rocky-backend python -m unittest discover -s run-test/backend -p "test_*.py"`
- Frontend only: `PYTHONPATH=run-test:rocky-backend python -m unittest discover -s run-test/frontend -p "test_*.py"`
- Granite bridge only: `cd granite-llm-server && python -m unittest discover -s tests -p "test_*.py"`

The required concurrency, cancellation, bounded-memory, timeout, and streaming
regressions for Granite's admission queue are listed in
[`../granite-llm-server/INFERENCE_QUEUE_CONTRACT.md`](../granite-llm-server/INFERENCE_QUEUE_CONTRACT.md).
The isolated queue plus buffered, queued-stream, active-heartbeat, and
deployment-thread contract integrations have deterministic coverage. Queue
telemetry sanitization, persistence, private streaming transport, and readiness
snapshots are also covered. A route-level acceptance test verifies six validated
requests complete FIFO with only one active model call. The opt-in deployment
smoke `--include-queue-burst` repeats a six-client burst against the public API
after the timeout rollout. Live rollout validation remains required before the
longer wait is enabled on Rocky.

Run the release gate from an activated project virtual environment after
installing the backend, compatibility-test, Granite, and frontend dependencies.
It runs backend tests, Granite tests, frontend unit tests, Svelte type checks,
formatting checks, a production frontend build using safe testing-mode values
(including the buffered `ROCKY_ENABLE_STREAMING=false` baseline),
and browser tests. It continues after a failed step so one run reports every
failing surface, then exits nonzero if any step failed. `--skip-browser` is for
machines without Chrome/Edge or WebDriver; do not use it for the final release
candidate.

The coverage runner measures branch and line coverage for the management
backend, Chat API, and Granite services, then measures statements, branches,
functions, and lines for all frontend TypeScript and Svelte source files. It
prints reports to the terminal and writes an ignored frontend JSON summary to
`rocky-interface/coverage/coverage-summary.json`. Selenium remains part of the
release gate but is intentionally separate from source-code coverage because it
exercises the running application from another process.

The thresholds in `.coveragerc` and `rocky-interface/vite.config.ts` are
conservative regression floors based on the measured all-source baseline. Raise
them as coverage improves; do not lower them simply to make a failing change
pass.

From the repository root in Windows PowerShell, set the Python import path first:

```powershell
$env:PYTHONPATH = "run-test;rocky-backend"
```

Then use the same commands without their leading `PYTHONPATH=...` assignment.

Browser tests use port `4173` by default. If another local project already uses
that port, set a different one, such as `ROCKY_WEB_PORT=4273`, before running
the frontend suite.

The frontend also has Node-based checks. From `rocky-interface`, run
`npm run lint`, `npm run check`, `npm run test:unit`, `npm run test:coverage`,
and `npm run build`.
Those direct commands expect the frontend `.env` described in
`rocky-interface/README.md`; the full test runner supplies its own testing
environment.

## Backup and restore count baseline

`manage.py database-counts` performs read-only `count_documents({})` calls for
the account, course, key, telemetry, and audit collections used in recovery
verification:

```sh
python manage.py database-counts --env-file /etc/rocky/backend.env
python manage.py database-counts \
  --env-file /etc/rocky/backend.env \
  --database rocky_restore_check
```

The second form is intended for a temporary restored database. Full archive,
permission, checksum, temporary-restore, and production-recovery instructions
are in `deploy/README.md`.

## Deployment smoke test

`integration/deployment_smoke.py` checks a deployed instance through its public
URLs. It requires `ROCKY_BASE_URL` and `ROCKY_API_KEY`; the optional
`ROCKY_EXPECTED_MODEL` value verifies the advertised model identifier. The
authenticated model-discovery request also verifies Rocky's three request
rate-limit headers and their value ranges.

```sh
export ROCKY_BASE_URL='https://rocky.cs.kent.edu'
printf 'Rocky deployment test API key: '
IFS= read -r -s ROCKY_API_KEY
printf '\n'
export ROCKY_API_KEY
python run-test/integration/deployment_smoke.py
```

The default checks do not generate model output or modify application content.
They are not invisible: the authenticated model-discovery request is retained
in institutional audit telemetry and consumes one model-discovery quota unit.
Add `--include-generation`, `--include-streaming`, or `--include-image` to
verify the corresponding public inference path and its rate-limit headers. The
streaming and image checks first require the selected model to advertise the
matching capability. For a final deployment, test buffered generation and every
advertised optional path with:

```sh
python run-test/integration/deployment_smoke.py \
  --timeout 390 \
  --include-advertised
```

All three explicit checks may also be combined:

```sh
python run-test/integration/deployment_smoke.py \
  --include-generation \
  --include-streaming \
  --include-image
```

Each generation is retained in institutional audit telemetry, including the
embedded one-pixel image used by the image smoke check.

After deploying the tracked timeout ladder, repeat the six-client classroom
burst with:

```sh
python run-test/integration/deployment_smoke.py \
  --timeout 390 \
  --include-queue-burst
```

The burst requires six available Responses requests in the key's current
rate-limit window. It starts them together, requires six distinct request IDs
and successful responses, validates every rate-limit header set, and prints the
IDs for queue-telemetry review. Unset the key after all smoke checks:

```sh
unset ROCKY_API_KEY
```

Use a dedicated instructor or deployment-test key and avoid running the command
in a tight loop. The smoke test intentionally does not exhaust the key to prove
the `429` path; that behavior is covered by the automated API contract tests.

## Live queue-telemetry verification

After the public queue burst passes, run
`integration/live_telemetry_smoke.py` once from the deployed revision with a
dedicated test key and direct access to the production database. This submits
one additional audited request and verifies that its exact permanent record has
the completed response, aggregate counter deltas, and the bounded queue object.
The queue check rejects missing fields, invalid positions, unsuccessful queue
states, booleans in numeric fields, and unexpected fields that could contain
request content.

Set `ROCKY_RUN_LIVE_TELEMETRY_SMOKE=1`, `ROCKY_LIVE_API_URL`,
`ROCKY_LIVE_API_KEY`, `ROCKY_LIVE_MONGODB_URI`, and `ROCKY_LIVE_DB_NAME` in the
operator shell, then run:

```sh
ROCKY_LIVE_TIMEOUT_SECONDS=390 \
  python run-test/integration/live_telemetry_smoke.py
```

The script prints only counter deltas or a stable failure code. It does not
print the API key, database URI, prompt, response, or stored queue record. Unset
the sensitive environment values immediately afterward.
