# Rocky Chat API

This Flask service exposes Rocky's student-facing `POST /v1/responses` endpoint and proxies valid requests to the internal model bridge.

## Local configuration

Copy `.env.example` to `.env`, or set the values in the repository-root `.env`. Both the backend and this service must use the same `ROCKY_DB_BACKEND`, `ROCKY_DB_NAME`, and `ROCKY_MONGITA_PATH` so generated and revoked keys take effect immediately.

Start the complete local stack from the repository root:

```sh
python run-dev.py --mode both
```

Use `--seed` only when you intentionally want to load the fixture data.

## Request

```sh
curl http://127.0.0.1:5003/v1/responses \
  -H "Authorization: Bearer $ROCKY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"rocky","input":"Hello!","store":false}'
```

The plaintext API key is never stored by this service; it is SHA-256 hashed for lookup. The public `rocky` model alias maps to `OLLAMA_MODEL`, and the internal model name is not accepted from clients.

## Permanent request records

When telemetry is enabled, every `POST /v1/responses` attempt receives an
`X-Rocky-Request-Id` and is written to `telemetry_interactions`. Schema-v2
records include the complete sanitized request and public response, credential
ownership, trustworthy user attribution when available, course/group context,
outcome, token counts, and model timing. Authorization headers, plaintext API
keys, key hashes, cookies, and service secrets are not recorded.
Malformed JSON bodies are represented by their byte length and digest rather
than stored verbatim because unparseable content cannot be safely redacted.

Production defaults to `ROCKY_REQUIRE_REQUEST_LOGGING=true`. If the initial
audit insert or any required pre-inference request, identity, or model-input
update fails, Rocky returns `503` without invoking the model. Set the variable
explicitly to `false` only when unlogged inference is acceptable.

Before deploying schema-v2 logging to a database containing the original
seven-day telemetry records, inspect and apply the migration:

```sh
python api-rocky/migrate_telemetry_v2.py --dry-run
python api-rocky/migrate_telemetry_v2.py
```

The migration removes `expires_at`, drops the old TTL index, labels existing
records as schema version 1 with unavailable content, and creates the new
permanent-record indexes. Back up MongoDB before running the non-dry command.
