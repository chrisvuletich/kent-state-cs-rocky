# API Reference

Rocky exposes one text-generation endpoint. It uses ordinary HTTP and JSON, so no provider-specific client library is required.

## Endpoint and authentication

| Method | Endpoint | Authentication |
| --- | --- | --- |
| POST | `https://rocky.cs.kent.edu/v1/responses` | `Authorization: Bearer sk_kent_...` |

The request body must be valid JSON. API keys placed in the JSON body or URL are not accepted.

## Request fields

| Field | Type | Required | Description | Default |
| --- | --- | --- | --- | --- |
| `model` | string | No | Public model alias. The only supported value is `rocky`. | `rocky` |
| `input` | string or array | Yes | A prompt string or an array of text message objects. | None |
| `instructions` | string | No | System-level instructions applied before the input. | None |
| `temperature` | number | No | Sampling temperature from 0 through 2. | Model default |
| `top_p` | number | No | Nucleus sampling value from 0 through 1. | Model default |
| `max_output_tokens` | integer | No | Maximum generated tokens from 1 through 2048. | Model default |
| `store` | boolean | No | Store the exchange and use conversation history. | `true` |
| `conversation_id` | string | No | Continue a stored conversation owned by the key's user. | New conversation |

The simplest request uses a string:

```json
{
  "model": "rocky",
  "input": "Explain recursion in one paragraph.",
  "store": false
}
```

For multiple messages, `content` can be a string or a list of text blocks:

```json
{
  "model": "rocky",
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

Rocky currently accepts text only. Streaming, tools, file input, and image input are not part of this first contract.

## Successful response

```json
{
  "id": "resp_123...",
  "object": "response",
  "created_at": 1786032000,
  "status": "completed",
  "model": "rocky",
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

Use `output_text` when you only need the generated text. The structured `output` array is available for students practicing a familiar response-envelope pattern. A stored request also returns `conversation_id`.

## Status codes

| Status | Meaning |
| --- | --- |
| 200 | Generation completed. |
| 400 | The JSON, model, input, or generation settings are invalid. |
| 401 | The Bearer key is missing, invalid, inactive, revoked, or expired. |
| 502 | Rocky could not reach the model service or received an unusable response. |
| 504 | Model generation timed out. |
