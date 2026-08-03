# JavaScript Example

Learn how to make your first request to the Rocky API using modern JavaScript.

## Requirements

- A modern browser or Node.js
- Your Rocky API Key
- Basic knowledge of JavaScript

## Authentication

Every request to the Rocky API requires an API key. Include it as the `api-key` field in the JSON request body, not as an `Authorization` header.

Keep your API key private. Anyone with access to your key can make requests on your behalf.

## Example Request

The example below sends a simple chat request to the Rocky API using the built-in `fetch()` function.

```javascript
const response = await fetch(
    "https://rocky.cs.kent.edu/v1/responses",
    {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            "api-key": process.env.ROCKY_API_KEY,
            message: "Hello Rocky!",
            store: false
        })
    }
);

if (!response.ok) {
    throw new Error(await response.text());
}

const data = await response.json();

console.log(data);
```

## Example Response

If the request succeeds, Rocky returns a JSON response similar to the example below.

```json
{
  "reply": "Hello! How can I help you today?"
}
```

## Next Steps

- Review the API Reference.
- Read the Best Practices guide.
- Build your first Rocky application.
