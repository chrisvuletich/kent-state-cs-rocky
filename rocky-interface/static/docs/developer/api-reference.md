# API Reference

Reference for Rocky’s current Chat API request and response contract.

## Endpoint and authentication

| Method | Endpoint | Authentication |
| --- | --- | --- |
| POST | `https://rocky.cs.kent.edu/v1/responses` | JSON `api-key` field |

Use Rocky’s public Chat API endpoint for requests.

## Simple request parameters

Use this form for a single message. History is stored unless `store` is set to `false`.

| Parameter | Data type | Required | Description | Default |
| --- | --- | --- | --- | --- |
| `api-key` | string | Yes | Active course API key. | None |
| `message` | string | Yes* | The user message sent to Rocky. | None |
| `store` | boolean | No | Store the exchange and use conversation history. | `true` |
| `conversation_id` | string | No | Continue a stored conversation owned by the key’s user. | New conversation |
| `model` | string | No | Model name forwarded to the generation service. | Configured server model |
| `temperature` | number | No | Sampling temperature; accepted range is 0–2. | Generation-service default |
| `top_p` | number | No | Nucleus sampling value; accepted range is 0–1. | Generation-service default |
| `max_output_tokens` | integer | No | Maximum generated tokens; accepted range is 1–3500. | Generation-service default |

**\*** Required when history is stored. A request with `store: false` may use the advanced `input` form below instead.

## Advanced input parameters

For a prebuilt message list, set `store` to `false` and send `input` instead of `message`.

| Parameter | Data type | Required | Description | Default |
| --- | --- | --- | --- | --- |
| `input` | array | Yes | Array of message objects passed to the generation service. | None |
| `input[].role` | string | No | Message role. | `user` |
| `input[].content` | array | No | Content blocks for the message. | Empty array |
| `input[].content[].type` | string | Yes for usable text | Use `input_text` for text content. | None |
| `input[].content[].text` | string | Yes for usable text | Text sent in an `input_text` block. | None |

## Successful response fields

| Field | Data type | Description |
| --- | --- | --- |
| `reply` | string | Rocky’s generated response text. |
| `model` | string | Model reported by the generation service. |
| `metadata` | object | Generation-service metadata. |
| `conversation_id` | string | Stored conversation ID; returned only when history is stored. |

## Error responses and status codes

| Status | Returned fields | When it occurs |
| --- | --- | --- |
| 200 | `reply`, `model`, `metadata`, optional `conversation_id` | Request completed. |
| 400 | `error` (string) | Invalid JSON, missing message, missing chat context, or an invalid request handled as a bad request. |
| 401 | `error` (string) | Missing, invalid, inactive, revoked, or expired API key. |
| 502 | `error` (string) | Rocky could not contact the generation service or the service returned an unusable response. |
