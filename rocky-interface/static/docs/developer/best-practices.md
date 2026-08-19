# API Best Practices

Following these best practices will help keep your Rocky applications secure, reliable, and easy to maintain.

## Keep Your API Key Secure

Your API key identifies your application when communicating with Rocky. Never share your API key publicly or include it in source control.

```javascript
// ❌ Don't do this
const apiKey = "abc123xyz";
```

```javascript
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

For streams, an HTTP 200 means only that SSE started. Treat
`response.completed` as success, handle a terminal `error` event, and treat a
connection that closes without either event as incomplete.

## Discover Optional Capabilities

Read the selected model's `metadata` from `GET /v1/models` before enabling
streaming or image input. These features can be disabled during rollout or when
the installed course model does not support them. Read image count, byte, and
pixel limits from the same metadata instead of copying example values.

## Protect Sensitive Information

Only request the information your application needs, and avoid storing sensitive data unless absolutely necessary.

- Never expose API keys in client-side code.
- Use HTTPS for all API requests.
- Rotate API keys if they become compromised.

Rocky records prompts, submitted images, outputs, and request metadata for
university safety and academic-resource oversight. Use the service only for
course-appropriate work and do not submit personal, confidential, regulated,
or otherwise sensitive material. Avoid writing Base64 image data or complete
responses to additional application logs unless the assignment requires it.

## Next Steps

You're now ready to explore the Rocky API in more detail.

- Browse the [API Reference](/?frame=help&doc=reference).
- Experiment with the [Python](/?frame=help&doc=python) and
  [JavaScript](/?frame=help&doc=javascript) examples.
- Try the [Streaming](/?frame=help&doc=streaming) and
  [Image Input](/?frame=help&doc=image-input) examples.
- Start building your own Rocky integrations.
