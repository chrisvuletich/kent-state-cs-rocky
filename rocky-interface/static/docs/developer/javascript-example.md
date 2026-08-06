# JavaScript Example

Learn how to make your first request to the Rocky API using modern JavaScript.

## Requirements

- A modern browser or Node.js
- Your Rocky API Key
- Basic knowledge of JavaScript

## Authentication

Every request to the Rocky API requires an API key. Send it as a Bearer token in the `Authorization` header.

Keep your API key private. Anyone with access to your key can make requests on your behalf.

## Example Request

The example below sends a simple chat request to the Rocky API using the built-in `fetch()` function.

```javascript
const response = await fetch(
    "https://rocky.cs.kent.edu/v1/responses",
    {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${process.env.ROCKY_API_KEY}`,
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            model: "rocky",
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

## Example Response

If the request succeeds, Rocky returns a JSON response similar to the example below.

```json
{
  "object": "response",
  "status": "completed",
  "model": "rocky",
  "output_text": "Hello! How can I help you today?"
}
```

## Next Steps

- Review the API Reference.
- Read the Best Practices guide.
- Build your first Rocky application.
