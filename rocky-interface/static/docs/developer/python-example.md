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

Every request to the Rocky API requires an API key. Include it as the `api-key` field in the JSON request body, not as an `Authorization` header.

Keep your API key private. Anyone with access to your key can make requests on your behalf.

## Example Request

The example below sends a simple chat request to the Rocky API. Store your key in the `ROCKY_API_KEY` environment variable before running the script.

```python
import os
import requests

url = "https://rocky.cs.kent.edu/v1/responses"

payload = {
    "api-key": os.environ["ROCKY_API_KEY"],
    "message": "Hello Rocky!",
    "store": False
}

response = requests.post(url, json=payload, timeout=30)
response.raise_for_status()

print(response.json()["reply"])
```

## Example Response

If the request succeeds, Rocky returns a JSON response similar to the example below.

```json
{
  "reply": "Hello! How can I help you today?",
  "model": "configured-model-name",
  "metadata": { "source": "ollama" }
}
```

## Next Steps

- Generate your API key.
- Read the API Reference.
- Learn authentication best practices.
- Try the JavaScript example.
