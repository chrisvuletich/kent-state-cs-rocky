# API Keys

Your API key allows your application to securely authenticate with the Rocky API. Treat your API key like a password and never share it publicly.

## What is an API Key?

An API key is a unique credential that identifies its owner and course when an
application communicates with Rocky. Every student API request must include a
valid key.

## Generate an API Key

Generate your API key from an enrolled course.

1. Open the **Courses** view and select an enrolled course.
2. Select **Home**.
3. Click **Generate Key**.
4. Copy and securely store your new API key.

## Using Your API Key

Send your key in the HTTP `Authorization` header using the Bearer scheme:

```text
Authorization: Bearer sk_kent_your_key_here
```

Do not put the key in the JSON request body or in a URL.

## Reset an API Key

Click **Regenerate Key** for the same key slot. Confirm the warning before
continuing; regeneration invalidates the old key immediately.

## Security Best Practices

- Never share your API key.
- Do not commit API keys to Git repositories.
- Regenerate your API key if you believe it has been compromised.
- Store API keys in environment variables whenever possible.

## Next Steps

Once you have generated your API key, you're ready to make your first request to the Rocky API.

- Read the [Python Example](/?frame=help&doc=python).
- Read the [JavaScript Example](/?frame=help&doc=javascript).
- Explore the [API Reference](/?frame=help&doc=reference).
