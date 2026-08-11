# Errors and Troubleshooting

Rocky returns a consistent JSON error object for public API failures. Check the
HTTP status first, then use `error.code` for program logic and `error.message`
for a readable explanation.

## Error format

```json
{
  "error": {
    "message": "model is required.",
    "type": "invalid_request_error",
    "param": "model",
    "code": "missing_required_parameter"
  }
}
```

- `message` explains what went wrong.
- `type` identifies the broad category, such as `authentication_error` or
  `invalid_request_error`.
- `param` identifies the request field involved, when applicable.
- `code` is the most useful stable value for application error handling.

Every API response also includes an `x-request-id` header. Include that value
when asking an administrator for help so the request can be located in the
audit records without guessing.

## Status codes and what to do

| Status | Common codes | What it means | Recommended action |
| --- | --- | --- | --- |
| `400` | `invalid_json`, `missing_required_parameter`, `invalid_type`, `invalid_value`, `invalid_parameter_combination`, `invalid_model_request`, `model_not_found`, `unsupported_parameter`, `unsupported_role`, `unsupported_content_type`, `input_too_large`, `metadata_too_large` | The request cannot be processed as written. | Correct the request before retrying. Use `error.param` to find the affected field. |
| `401` | `invalid_api_key` | The Bearer key is missing, invalid, inactive, revoked, or expired. | Check the header and generate or reactivate a key. Do not automatically retry the same key. |
| `404` | `response_not_found` | A `previous_response_id` was not found or does not belong to this credential. | Start a new request or use a response ID created by the same key. |
| `413` | `request_too_large` | The complete HTTP request body exceeds the server limit. | Send a smaller request. |
| `429` | `rate_limit_exceeded`, `ingress_rate_limit_exceeded` | The API key exhausted its minute limit, or unusually heavy traffic arrived from the same network address. | Wait at least the number of seconds in `Retry-After`, then retry with a small random delay. |
| `500` | `internal_error` | An unexpected Rocky error occurred. | Record the request ID and retry once after a short delay. Report repeated failures. |
| `502` | `model_service_unavailable`, `invalid_model_response`, `model_error` | Granite or Ollama could not be reached or returned an unusable response. | Retry once after a short delay. Report repeated failures with the request ID. |
| `503` | `model_busy`, `request_logging_unavailable`, `rate_limit_unavailable` | The model is busy or a required internal service is unavailable. | For `model_busy`, honor the `Retry-After` header. Otherwise wait for the service to recover. |
| `504` | `model_timeout` | Model generation exceeded the configured time limit. | Retry once, preferably with shorter input or a smaller `max_output_tokens`. |

After Rocky authenticates and counts a request, the response includes
`x-ratelimit-limit-requests`, `x-ratelimit-remaining-requests`, and
`x-ratelimit-reset-requests`. The reset value is a duration such as `17s`.
Rocky enforces request limits only, so token-limit headers are not present.
`Retry-After` is returned in whole seconds when a temporary `429` limit is hit.

## Handle errors with Python requests

```python
import os
import time
import requests

response = requests.post(
    "https://rocky.cs.kent.edu/v1/responses",
    headers={"Authorization": f"Bearer {os.environ['ROCKY_API_KEY']}"},
    json={
        "model": os.environ["ROCKY_MODEL"],
        "input": "Explain recursion in two sentences.",
        "store": False,
    },
    timeout=60,
)

if response.ok:
    print(response.json()["output_text"])
else:
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error", {})
    request_id = response.headers.get("x-request-id", "not provided")
    print(f"{response.status_code} {error.get('code')}: {error.get('message')}")
    print(f"Request ID: {request_id}")

    if error.get("code") in {"model_busy", "rate_limit_exceeded"}:
        time.sleep(int(response.headers.get("Retry-After", "2")))
```

Never print or log the API key while diagnosing an error.

## Quick checks

### Invalid API key

The header must use the Bearer scheme exactly once:

```sh
curl https://rocky.cs.kent.edu/v1/models \
  -H "Authorization: Bearer $ROCKY_API_KEY"
```

Make sure the shell variable exists with `test -n "$ROCKY_API_KEY"`. Do not use
`echo` to display a real key in a shared terminal or screenshot.

### Model not found

Do not guess the model name. Read the current identifier first:

```sh
curl https://rocky.cs.kent.edu/v1/models \
  -H "Authorization: Bearer $ROCKY_API_KEY"
```

Copy `data[0].id` into the `model` field of the response request.

### Service or timeout errors

Check `https://rocky.cs.kent.edu/server-health`. If the problem repeats, give
the administrator the time of the request, its `x-request-id`, HTTP status, and
error code. Do not send the API key.

The response shape and major HTTP categories intentionally follow familiar API
conventions. Rocky-specific codes in this guide are the source of truth for
this service.
