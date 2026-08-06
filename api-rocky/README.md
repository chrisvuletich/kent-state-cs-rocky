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
