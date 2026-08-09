# API Best Practices

Following these best practices will help keep your Rocky applications secure, reliable, and easy to maintain.

## Keep Your API Key Secure

Your API key identifies your application when communicating with Rocky. Never share your API key publicly or include it in source control.

```javascript
// ❌ Don't do this
const apiKey = "abc123xyz";

// ✅ Better
const apiKey = process.env.ROCKY_API_KEY;
```

The environment-variable example above is for server-side Node.js. Never put a Rocky API key in JavaScript that is delivered to a web browser; have the browser call your own server instead.

## Validate API Responses

Always check that a request completed successfully before using the data returned by the API.

```javascript
if (response.ok) {
    const data = await response.json();
    console.log(data);
} else {
    console.error("Request failed.");
}
```

## Handle Errors Gracefully

Network issues and server errors can happen. Make sure your application handles these situations without crashing.

- Check HTTP status codes.
- Display helpful error messages.
- Retry requests only when appropriate.

## Protect Sensitive Information

Only request the information your application needs, and avoid storing sensitive data unless absolutely necessary.

- Never expose API keys in client-side code.
- Use HTTPS for all API requests.
- Rotate API keys if they become compromised.

## Next Steps

You're now ready to explore the Rocky API in more detail.

- Browse the API Reference.
- Experiment with the Python and JavaScript examples.
- Start building your own Rocky integrations.
