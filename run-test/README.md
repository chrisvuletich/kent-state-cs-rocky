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
  - checks the real backend seed data has one admin, two instructors, four users, and six courses;
  - verifies widgets are embedded per user.
- test_backend_validation.py:
  - verifies accepted data is inserted;
  - verifies invalid data is rejected;
  - verifies API endpoints return 400 for malformed payloads.
- test_audit_events.py:
  - verifies successful administrative mutations create trusted audit events;
  - verifies rejected mutations do not create events and sensitive fields are removed;
  - verifies account deactivation suspends owned API keys.
- test_user_settings.py:
  - verifies per-user settings are readable and writable;
  - verifies widgets stay isolated per user.
- test_course_api_history.py:
  - verifies API history records grouped and ungrouped usage;
  - verifies analytics and widgets endpoints remain reachable.
- test_authorization_matrix.py:
  - keeps student, instructor, administrator, inactive-account, closed-course,
    and trusted-proxy expectations in one data-driven role matrix;
  - verifies students can create only their own course key.
- test_database_counts.py:
  - verifies the backup/restore count baseline is deterministic and read-only.

Install the backend and compatibility-test dependencies with:

- `pip install -r rocky-backend/requirements.txt -r run-test/requirements-compat.txt`

`openai` is only a test dependency. The compatibility test verifies that the
official Python client can consume Rocky's OpenAI-compatible HTTP responses;
students may continue to use `requests`, `curl`, or any other HTTP client.

## Frontend tests

Path: run-test/frontend

- test_preview_login_chromedriver.py:
  - opens login preview;
  - signs into a mock admin session;
  - confirms the dashboard loads.
- test_view_titles_chromedriver.py:
  - opens login preview (auth gate aware);
  - signs into mock session;
  - clicks each sidebar view;
  - asserts each view renders the correct page title.
- test_admin_management_chromedriver.py:
  - creates a role-aware external whitelist account;
  - verifies the resulting mutation appears in the Admin audit preview.
- test_priority_reliability_chromedriver.py:
  - verifies course cards use button semantics;
  - verifies existing keys warn before regeneration;
  - checks independent Admin Dashboard sections, shareable analytics state, and
    desktop/mobile chat layout.
- test_role_journeys_chromedriver.py:
  - verifies student key generation, copy-once disclosure, and dismissal;
  - verifies instructor student/group key controls and unrelated-course hiding;
  - verifies logout clears account-specific browser state and protects `/`.

## Local run commands

From the repository root on macOS/Linux:

- All backend and browser tests: `PYTHONPATH=run-test:rocky-backend python run-test/test_all.py`
- Backend only: `PYTHONPATH=rocky-backend python -m unittest discover -s run-test/backend -p "test_*.py"`
- Frontend only: `PYTHONPATH=run-test:rocky-backend python -m unittest discover -s run-test/frontend -p "test_*.py"`
- Granite bridge only: `cd granite-llm-server && python -m unittest discover -s tests -p "test_*.py"`

From the repository root in Windows PowerShell, set the Python import path first:

```powershell
$env:PYTHONPATH = "run-test;rocky-backend"
```

Then use the same commands without their leading `PYTHONPATH=...` assignment.

Browser tests use port `4173` by default. If another local project already uses
that port, set a different one, such as `ROCKY_WEB_PORT=4273`, before running
the frontend suite.

The frontend also has Node-based checks. From `rocky-interface`, run
`npm run lint`, `npm run check`, `npm run test:unit`, and `npm run build`.

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
export ROCKY_API_KEY='sk_kent_replace_with_test_key'
python run-test/integration/deployment_smoke.py
```

The default checks do not generate model output or modify application content.
They are not invisible: the authenticated model-discovery request is retained
in institutional audit telemetry and consumes one model-discovery quota unit.
Add `--include-generation` to send one short request with `store: false` and
verify the generation rate-limit headers too. The generation is also retained
in institutional audit telemetry, like every other inference request.

Use a dedicated instructor or deployment-test key and avoid running the command
in a tight loop. The smoke test intentionally does not exhaust the key to prove
the `429` path; that behavior is covered by the automated API contract tests.
