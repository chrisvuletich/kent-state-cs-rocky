# Rocky Chat API

This Flask service exposes Rocky's student-facing `POST /v1/responses` and
`GET /v1/models` endpoints and proxies valid generation requests to the
internal model bridge.

## Local configuration

Copy `.env.example` to `.env`, or set the values in the repository-root `.env`. Both the backend and this service must use the same `ROCKY_DB_BACKEND`, `ROCKY_DB_NAME`, and `ROCKY_MONGITA_PATH` so generated and revoked keys take effect immediately.

The service validates environment names, booleans, URLs, ports, limits, and
timeouts at startup. Invalid values fail immediately with the setting name;
omitted optional values use the defaults in `.env.example`.

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
  -d "{\"model\":\"$ROCKY_MODEL\",\"input\":\"Hello!\",\"store\":false}"
```

The plaintext API key is never stored by this service; it is SHA-256 hashed for
lookup. `ROCKY_PUBLIC_MODEL` defines the one model identifier students may
request and defaults to `OLLAMA_MODEL`.
Set `ROCKY_MODEL` to the identifier returned by an authenticated `GET /v1/models` request.
Each listed model also includes a Rocky-specific `metadata` object populated
from the active server configuration. It reports the context and output limits
plus support for streaming, instructions, and `previous_response_id`. Clients
that only need the standard model fields can ignore this additional object.

## Streaming and image input

Rocky supports opt-in OpenAI-style Responses SSE and bounded base64
JPEG/PNG/static-WebP input for buffered or streamed text responses. The built-in
web chat consumes the same stream, provides local image previews, and renders
owned conversation history without changing the public API contract.
Capability-aware deployment smoke checks, student examples, the local release
gate, and SDK compatibility tests cover each advertised inference path. See
[`STREAMING_AND_IMAGE_CONTRACT.md`](STREAMING_AND_IMAGE_CONTRACT.md). Both Rocky
and Granite must enable the corresponding rollout flag. Both features remain
disabled by default.

## Request rate limits

Rocky applies separate per-key, fixed-minute request limits to
`POST /v1/responses` and `GET /v1/models`. Configure them with
`ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE` and
`ROCKY_MODELS_RATE_LIMIT_PER_MINUTE`; the example defaults are 10 and 120.

Once a request is authenticated and its limit is consumed, the response
includes:

- `x-ratelimit-limit-requests`: the configured requests-per-minute limit
- `x-ratelimit-remaining-requests`: requests remaining in the current window
- `x-ratelimit-reset-requests`: time until the window resets, such as `17s`

An exhausted key receives HTTP `429`, error code `rate_limit_exceeded`, the
same three request-limit headers, and `Retry-After` in whole seconds. Invalid
credentials, malformed JSON, and health/readiness checks do not consume these
limits. Authenticated validation failures do consume a request. Rocky does not
enforce token-per-minute limits, so it does not emit token-limit headers.

## Permanent request records

When telemetry is enabled, every `POST /v1/responses` attempt receives an
`x-request-id` (also available as `X-Rocky-Request-Id`) and is written to
`telemetry_interactions`. Records include the complete parsed request and public response, credential
ownership, trustworthy user attribution when available, course/group context,
outcome, token counts, and model timing. Authorization headers, plaintext API
keys, key hashes, cookies, and service secrets are not recorded.
Valid prompt, instruction, and response text is recorded verbatim. Malformed
JSON bodies are represented by their byte length and digest because the service
cannot reliably distinguish content from accidentally included credentials in
an unparseable body.

Production defaults to `ROCKY_REQUIRE_REQUEST_LOGGING=true`. If the initial
audit insert or any required pre-inference request, identity, or model-input
update fails, Rocky returns `503` without invoking the model. Set the variable
explicitly to `false` only when unlogged inference is acceptable.
