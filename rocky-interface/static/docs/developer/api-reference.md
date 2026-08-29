# API Reference

Rocky exposes a response-generation endpoint and a model-list endpoint. It
supports text prompts, optional local image input, buffered JSON responses, and
optional Server-Sent Event (SSE) streaming. It uses ordinary HTTP, JSON, and
SSE, so no provider-specific client library is required.

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
        "default_reasoning_effort": "medium",
        "max_output_tokens": 8192,
        "max_image_output_tokens": 12288,
        "max_context_tokens": 65536,
        "max_context_characters": 262144,
        "supports_streaming": true,
        "supports_image_input": true,
        "max_images_per_request": 4,
        "max_image_bytes": 4194304,
        "max_image_total_bytes": 6291456,
        "max_image_pixels": 20000000,
        "max_image_total_pixels": 40000000,
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

The feature flags and limit values come from the server's active configuration
and may differ from this example. Check them at runtime instead of assuming that
streaming or image input is enabled. Clients may use this metadata to configure
their interface or ignore it when they only use buffered text. The additional
object does not change the required model-list fields.

## Request fields

| Field | Type | Required | Description | Default |
| --- | --- | --- | --- | --- |
| `model` | string | Yes | Model identifier returned by `GET /v1/models`. | None |
| `input` | string or array | Yes | A prompt string or an array of message objects containing text and, when advertised, image blocks. | None |
| `instructions` | string | No | System-level instructions applied before the input. | None |
| `temperature` | number | No | Sampling temperature from 0 through 2. | Model default |
| `top_p` | number | No | Nucleus sampling value from 0 through 1. | Model default |
| `max_output_tokens` | integer | No | Maximum generated tokens. The text ceiling is `metadata.max_output_tokens`; requests containing an image may use `metadata.max_image_output_tokens`. | Applicable advertised ceiling |
| `frequency_penalty` | number | No | Frequency penalty from -2 through 2; its effect depends on the deployed model and Ollama runtime. | Model default |
| `presence_penalty` | number | No | Presence penalty from -2 through 2; its effect depends on the deployed model and Ollama runtime. | Model default |
| `metadata` | object | No | Application metadata returned with the response. | `{}` |
| `store` | boolean | No | Allow the response to be used for later continuation. Institutional audit logging is independent of this field. | `true` |
| `previous_response_id` | string | No | Continue from a previously stored response created by the same credential. | None |
| `stream` | boolean | No | Return SSE lifecycle and text-delta events when streaming is advertised. | `false` |

Rocky validates and forwards both penalty fields for OpenAI-compatible clients,
but some Ollama models may ignore one or both. Clients should not depend on a
specific penalty behavior unless it has been verified with the model currently
returned by `GET /v1/models`. The model metadata identifies these fields under
`model_dependent_parameters`.

When the built-in chat does not specify a reasoning level, Rocky uses the
advertised `default_reasoning_effort` (`medium` by default). The Ollama context
window is capped by `max_context_tokens`. `max_context_characters` is a separate
application-level request and conversation-history guard, not a tokenizer
count.

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

Tools, uploaded file IDs, remote image URLs, structured output, audio, and video
are not part of Rocky's current contract. Unsupported parameters and content
types return a 400 error instead of being silently ignored.

To continue a stored response, send its response ID:

```json
{
  "model": "model-id-from-v1-models",
  "input": "Give me another example.",
  "previous_response_id": "resp_123..."
}
```

## Image input

When the selected model advertises `supports_image_input: true`, a user message
may contain `input_text` and `input_image` blocks:

```json
{
  "model": "model-id-from-v1-models",
  "input": [
    {
      "role": "user",
      "content": [
        { "type": "input_text", "text": "What is shown in this image?" },
        {
          "type": "input_image",
          "image_url": "data:image/png;base64,iVBORw0KGgo...",
          "detail": "auto"
        }
      ]
    }
  ],
  "store": false
}
```

Rocky accepts Base64 data URLs for JPEG, PNG, and static WebP files. It rejects
remote URLs, `file_id`, GIF, SVG, animation, images in non-user messages, and
`detail` values other than `auto`. The model metadata reports the current
image-count, decoded-byte, and pixel limits. Rocky verifies the real container,
dimensions, and decoded size; a data URL's declared media type is not trusted by
itself.

See the [Image Input Example](/?frame=help&doc=image-input) for complete Python
and JavaScript examples.

## Streaming response

When the selected model advertises `supports_streaming: true`, add
`"stream": true`. A successful request returns `text/event-stream` instead of
one JSON document. Every frame contains matching `event` and `data.type` values:

```text
event: response.output_text.delta
data: {"type":"response.output_text.delta","sequence_number":4,"delta":"Hello",...}

```

Rocky's text stream starts with `response.created`, sends one or more
`response.output_text.delta` events, and ends successfully with
`response.completed`. Sequence numbers start at zero and increase by one. There
is no `[DONE]` sentinel. Concatenate delta strings for live display, but treat
the request as successful only after validating `response.completed`.

Validation failures that occur before streaming begins remain ordinary JSON
errors with their normal non-200 HTTP status. If generation fails after the SSE
response begins, Rocky sends a terminal `error` event; the already-sent HTTP
status remains 200. See the
[Streaming Example](/?frame=help&doc=streaming) for parsers that handle chunk
boundaries and terminal errors.

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

Responses generated by the Rocky application include an `x-request-id` header
that can be used to find the matching audit record when troubleshooting. An
ingress-level `413` or `429` can be returned by Nginx before the request reaches
Rocky and therefore may not have a Rocky request ID. Authenticated requests that
reach application rate-limit enforcement also include `x-ratelimit-limit-requests`,
`x-ratelimit-remaining-requests`, and `x-ratelimit-reset-requests`. The reset
value is a duration such as `17s`.

The **Errors and Troubleshooting** guide lists the current error codes, explains
when a retry is appropriate, and includes a Python `requests` example.

## Status codes

| Status | Meaning |
| --- | --- |
| 200 | A buffered generation completed, or an SSE response began. Check the terminal SSE event for streamed success. |
| 400 | The JSON, model, input, or generation settings are invalid. |
| 401 | The Bearer key is missing, invalid, inactive, revoked, or expired. |
| 404 | The requested previous response does not exist or is not owned by this credential. |
| 413 | The request body is too large. |
| 429 | The API key exhausted its request limit, or the ingress network-address limit was reached. |
| 502 | Rocky could not reach the model service or received an unusable response. |
| 503 | The model is busy or a required internal service is unavailable. |
| 504 | Model generation timed out. |
