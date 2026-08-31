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

The example below discovers the active model and sends a request from Node.js
using the built-in `fetch()` function. A browser application must send requests
through its own server so the API key is never shipped to or exposed in browser
code.

```javascript
const apiKey = process.env.ROCKY_API_KEY;

if (!apiKey) {
	throw new Error("Set ROCKY_API_KEY before running this script.");
}

const modelsResponse = await fetch("https://rocky.cs.kent.edu/v1/models", {
	headers: { "Authorization": `Bearer ${apiKey}` }
});
if (!modelsResponse.ok) throw new Error(await modelsResponse.text());

const model = (await modelsResponse.json()).data?.[0]?.id;
if (!model) throw new Error("Rocky did not return an available model.");

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

The model-list request prevents the example from depending on a model name that
may change between semesters.

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
