# API Reference

Rocky exposes a text-generation endpoint and a model-list endpoint. It uses
ordinary HTTP and JSON, so no provider-specific client library is required.

## Endpoint and authentication

| Method | Endpoint | Authentication |
| --- | --- | --- |
| POST | `https://rocky.cs.kent.edu/v1/responses` | `Authorization: Bearer sk_kent_...` |
| GET | `https://rocky.cs.kent.edu/v1/models` | `Authorization: Bearer sk_kent_...` |

The request body must be valid JSON. API keys placed in the JSON body or URL are not accepted.

## Available models

Call `GET /v1/models` before sending a response request and use the identifier from its `data` array. The installed model can change between semesters, so examples intentionally use a placeholder instead of assuming a model name.

Rocky keeps the standard model fields and adds a Rocky-specific `metadata`
object describing the currently configured capabilities:

```json
{
  "object": "list",
  "data": [
    {
      "id": "model-id-from-v1-models",
      "object": "model",
      "created": 0,
      "owned_by": "kent-state",
      "metadata": {
        "max_output_tokens": 2048,
        "max_context_characters": 60000,
        "supports_streaming": false,
        "supports_previous_response_id": true,
        "supports_instructions": true,
        "model_dependent_parameters": [
          "frequency_penalty",
          "presence_penalty"
        ]
      }
    }
  ]
}
```

The limit values come from the server's active configuration and may differ
from this example. Clients may use this metadata to configure their interface
or ignore it. The additional object does not change the required model-list
fields.

## Request fields

| Field | Type | Required | Description | Default |
| --- | --- | --- | --- | --- |
| `model` | string | Yes | Model identifier returned by `GET /v1/models`. | None |
| `input` | string or array | Yes | A prompt string or an array of text message objects. | None |
| `instructions` | string | No | System-level instructions applied before the input. | None |
| `temperature` | number | No | Sampling temperature from 0 through 2. | Model default |
| `top_p` | number | No | Nucleus sampling value from 0 through 1. | Model default |
| `max_output_tokens` | integer | No | Maximum generated tokens from 1 through 2048. | Model default |
| `frequency_penalty` | number | No | Frequency penalty from -2 through 2; its effect depends on the deployed model and Ollama runtime. | Model default |
| `presence_penalty` | number | No | Presence penalty from -2 through 2; its effect depends on the deployed model and Ollama runtime. | Model default |
| `metadata` | object | No | Application metadata returned with the response. | `{}` |
| `store` | boolean | No | Allow the response to be used for later continuation. Institutional audit logging is independent of this field. | `true` |
| `previous_response_id` | string | No | Continue from a previously stored response created by the same credential. | None |
| `stream` | boolean | No | Streaming is not currently supported; `true` returns a clear 400 error. | `false` |

Rocky validates and forwards both penalty fields for OpenAI-compatible clients,
but some Ollama models may ignore one or both. Clients should not depend on a
specific penalty behavior unless it has been verified with the model currently
returned by `GET /v1/models`. The model metadata identifies these fields under
`model_dependent_parameters`.

The simplest request uses a string:

```json
{
  "model": "model-id-from-v1-models",
  "input": "Explain recursion in one paragraph.",
  "store": false
}
```

For multiple messages, `content` can be a string or a list of text blocks:

```json
{
  "model": "model-id-from-v1-models",
  "input": [
    { "role": "user", "content": "My name is Flash." },
    { "role": "assistant", "content": "Nice to meet you." },
    {
      "role": "user",
      "content": [{ "type": "input_text", "text": "What is my name?" }]
    }
  ],
  "store": false
}
```

Rocky currently accepts text only. Tools, files, images, structured output, and
streaming are not part of this contract. Unsupported parameters and content
types return a 400 error instead of being silently ignored.

To continue a stored response, send its response ID:

```json
{
  "model": "model-id-from-v1-models",
  "input": "Give me another example.",
  "previous_response_id": "resp_123..."
}
```

## Successful response

```json
{
  "id": "resp_123...",
  "object": "response",
  "created_at": 1786032000,
  "status": "completed",
  "model": "model-id-from-v1-models",
  "output": [
    {
      "id": "msg_123...",
      "type": "message",
      "status": "completed",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "Recursion is ...",
          "annotations": []
        }
      ]
    }
  ],
  "output_text": "Recursion is ...",
  "usage": {
    "input_tokens": 8,
    "output_tokens": 24,
    "total_tokens": 32
  }
}
```

Use `output_text` when you only need the generated text. The structured
`output` array is available for students practicing a familiar response-envelope
pattern. The built-in website uses a private conversation extension that is not
part of the public student contract.

## Error response

```json
{
  "error": {
    "message": "temperature must be between 0 and 2.",
    "type": "invalid_request_error",
    "param": "temperature",
    "code": "invalid_value"
  }
}
```

Every API response includes an `x-request-id` header that can be used to find
the matching audit record when troubleshooting. Authenticated requests that
reach rate-limit enforcement also include `x-ratelimit-limit-requests`,
`x-ratelimit-remaining-requests`, and `x-ratelimit-reset-requests`. The reset
value is a duration such as `17s`.

The **Errors and Troubleshooting** guide lists the current error codes, explains
when a retry is appropriate, and includes a Python `requests` example.

## Status codes

| Status | Meaning |
| --- | --- |
| 200 | Generation completed. |
| 400 | The JSON, model, input, or generation settings are invalid. |
| 401 | The Bearer key is missing, invalid, inactive, revoked, or expired. |
| 404 | The requested previous response does not exist or is not owned by this credential. |
| 413 | The request body is too large. |
| 429 | The API key has exhausted its request limit for the current minute. |
| 502 | Rocky could not reach the model service or received an unusable response. |
| 503 | The model is busy or a required internal service is unavailable. |
| 504 | Model generation timed out. |
