# JavaScript Example

Learn how to make your first request to the Rocky API using modern JavaScript.

## Requirements

- Node.js 18 or newer
- Your Rocky API Key
- Basic knowledge of JavaScript

## Authentication

Every request to the Rocky API requires an API key. Send it as a Bearer token in the `Authorization` header.

Keep your API key private. Anyone with access to your key can make requests on your behalf.

## Example Request

The example below sends a simple chat request from Node.js using the built-in `fetch()` function. A browser application must send requests through its own server so the API key is never shipped to or exposed in browser code.

```javascript
const apiKey = process.env.ROCKY_API_KEY;
const model = process.env.ROCKY_MODEL;

if (!apiKey || !model) {
	throw new Error("Set ROCKY_API_KEY and ROCKY_MODEL before running this script.");
}

const response = await fetch(
    "https://rocky.cs.kent.edu/v1/responses",
    {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${apiKey}`,
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            model,
            input: "Hello Rocky!",
            store: false
        })
    }
);

if (!response.ok) {
    throw new Error(await response.text());
}

const data = await response.json();

console.log(data.output_text);
```

Run `GET /v1/models` and set `ROCKY_MODEL` to the identifier it returns.

## Example Response

If the request succeeds, Rocky returns a JSON response similar to the example below.

```json
{
  "object": "response",
  "status": "completed",
  "model": "model-id-from-v1-models",
  "output_text": "Hello! How can I help you today?"
}
```

## Next Steps

- Review the [API Reference](/?frame=help&doc=reference).
- Read the [Best Practices](/?frame=help&doc=best-practices) guide.
- Learn correct SSE parsing in the
  [Streaming Example](/?frame=help&doc=streaming).
- Send a local image with the
  [Image Input Example](/?frame=help&doc=image-input).
- Build your first Rocky application.
