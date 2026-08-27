# Python Example

Learn how to make your first request to the Rocky API using Python.

## Requirements

- Python 3.10 or newer
- The `requests` library
- Your Rocky API Key

## Install Dependencies

Rocky's Python examples use the `requests` library to communicate with the API. If you don't already have it installed, run:

```bash
pip install requests
```

## Authentication

Every request to the Rocky API requires an API key. Send it as a Bearer token in the `Authorization` header.

Keep your API key private. Anyone with access to your key can make requests on your behalf.

## Example Request

The example below sends a simple chat request to the Rocky API. Store your key in the `ROCKY_API_KEY` environment variable before running the script.

```python
import os
import requests

url = "https://rocky.cs.kent.edu/v1/responses"
model = os.environ["ROCKY_MODEL"]

headers = {
    "Authorization": f"Bearer {os.environ['ROCKY_API_KEY']}"
}
payload = {
    "model": model,
    "input": "Hello Rocky!",
    "max_output_tokens": 300,
    "store": False,
}

response = requests.post(url, headers=headers, json=payload, timeout=390)
response.raise_for_status()

print(response.json()["output_text"])
```

Run `GET /v1/models` and set `ROCKY_MODEL` to the identifier it returns.

## Example Response

If the request succeeds, Rocky returns a JSON response similar to the example below.

```json
{
  "id": "resp_123...",
  "object": "response",
  "status": "completed",
  "model": "model-id-from-v1-models",
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [
        { "type": "output_text", "text": "Hello! How can I help you today?" }
      ]
    }
  ],
  "output_text": "Hello! How can I help you today?"
}
```

Rocky's documented Python interface uses `requests` and does not require an AI-provider SDK.

## Optional compatible client

If an assignment benefits from a higher-level client, the OpenAI Python library can be pointed at Rocky's base URL. This library is optional client-side convenience; the Rocky server does not import or depend on it.

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["ROCKY_API_KEY"],
    base_url="https://rocky.cs.kent.edu/v1",
)

model = os.environ["ROCKY_MODEL"]

response = client.responses.create(
    model=model,
    input="Hello Rocky!",
    store=False,
)

print(response.output_text)
```

## Next Steps

- [Generate your API key](/?frame=help&doc=apikey).
- Read the [API Reference](/?frame=help&doc=reference).
- Learn authentication [best practices](/?frame=help&doc=best-practices).
- Try the [JavaScript example](/?frame=help&doc=javascript).
- Stream text incrementally with the
  [Streaming Example](/?frame=help&doc=streaming).
- Analyze a local image with the
  [Image Input Example](/?frame=help&doc=image-input).
