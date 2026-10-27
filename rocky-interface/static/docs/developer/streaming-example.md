# Streaming Example

Streaming lets an application display text as Rocky generates it. Rocky uses
Server-Sent Events (SSE) and the Responses API lifecycle. Check
`data[0].metadata.supports_streaming` from `GET /v1/models` before exposing a
streaming option.

## Python with requests

`requests.iter_lines()` preserves SSE line boundaries even when network chunks
split a JSON event. The example prints text deltas immediately and accepts only
`response.completed` as success. It reports `response.incomplete` separately
when the output allowance is exhausted, preserving any partial text.

```python
import json
import os
import requests

url = "https://rocky.cs.kent.edu/v1/responses"
headers = {
    "Authorization": f"Bearer {os.environ['ROCKY_API_KEY']}",
    "Accept": "text/event-stream",
}

models_response = requests.get(
    "https://rocky.cs.kent.edu/v1/models",
    headers={"Authorization": headers["Authorization"]},
    timeout=30,
)
models_response.raise_for_status()
model = models_response.json()["data"][0]
if model.get("metadata", {}).get("supports_streaming") is not True:
    raise RuntimeError("The active Rocky model does not support streaming.")

payload = {
    "model": model["id"],
    "input": "Explain recursion in one paragraph.",
    "stream": True,
    "store": False,
}

finished = False
event_name = None
with requests.post(
    url,
    headers=headers,
    json=payload,
    stream=True,
    timeout=390,
) as response:
    request_id = response.headers.get("x-request-id", "not provided")
    response.raise_for_status()

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            event_name = None
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
            continue
        if not line.startswith("data:") or event_name is None:
            raise RuntimeError("Malformed Rocky SSE frame")

        event = json.loads(line.removeprefix("data:").strip())
        if event.get("type") != event_name:
            raise RuntimeError("SSE event name and data.type did not match")
        if event_name == "response.output_text.delta":
            print(event["delta"], end="", flush=True)
        elif event_name == "error":
            raise RuntimeError(
                f"{event.get('code')}: {event.get('message')} "
                f"(request {request_id})"
            )
        elif event_name == "response.completed":
            finished = True
            print()
        elif event_name == "response.incomplete":
            finished = True
            reason = event["response"]["incomplete_details"]["reason"]
            print(f"\nAnswer unfinished: {reason} (request {request_id})")

if not finished:
    raise RuntimeError(f"Rocky stream ended without a terminal event (request {request_id})")
```

## JavaScript with fetch

Network chunks do not necessarily align with SSE frames or UTF-8 characters.
Use a streaming `TextDecoder`, keep the unfinished tail, and split only on a
blank SSE line.

```javascript
const apiKey = process.env.ROCKY_API_KEY;
if (!apiKey) throw new Error("Set ROCKY_API_KEY before running this script.");

const modelsResponse = await fetch("https://rocky.cs.kent.edu/v1/models", {
	headers: { "Authorization": `Bearer ${apiKey}` }
});
if (!modelsResponse.ok) throw new Error(await modelsResponse.text());

const model = (await modelsResponse.json()).data?.[0];
if (!model) throw new Error("Rocky did not return an available model.");
if (model.metadata?.supports_streaming !== true) {
	throw new Error("The active Rocky model does not support streaming.");
}

const response = await fetch("https://rocky.cs.kent.edu/v1/responses", {
	method: "POST",
	headers: {
		"Authorization": `Bearer ${apiKey}`,
		"Content-Type": "application/json",
		"Accept": "text/event-stream"
	},
	body: JSON.stringify({
		model: model.id,
		input: "Explain recursion in one paragraph.",
		stream: true,
		store: false
	})
});

if (!response.ok || !response.body) {
	throw new Error(await response.text());
}

const requestId = response.headers.get("x-request-id") ?? "not provided";
const reader = response.body.getReader();
const decoder = new TextDecoder("utf-8", { fatal: true });
let buffer = "";
let finished = false;

function processFrame(frame) {
	let eventName;
	const dataLines = [];
	for (const line of frame.split(/\r?\n/)) {
		if (line.startsWith(":")) continue;
		if (line.startsWith("event:")) eventName = line.slice(6).trim();
		else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
		else throw new Error("Malformed Rocky SSE field");
	}
	if (!eventName && dataLines.length === 0) return; // Queue/thinking keepalive comment.
	if (!eventName || dataLines.length === 0) throw new Error("Incomplete Rocky SSE frame");

	const event = JSON.parse(dataLines.join("\n"));
	if (event.type !== eventName) throw new Error("SSE event name and data.type did not match");
	if (eventName === "response.output_text.delta") process.stdout.write(event.delta);
	else if (eventName === "error") {
		throw new Error(`${event.code}: ${event.message} (request ${requestId})`);
	} else if (eventName === "response.completed") {
		finished = true;
		process.stdout.write("\n");
	} else if (eventName === "response.incomplete") {
		finished = true;
		process.stdout.write("\n");
		console.warn(`Answer unfinished: ${event.response.incomplete_details.reason} (request ${requestId})`);
	}
}

while (true) {
	const { value, done } = await reader.read();
	buffer += decoder.decode(value, { stream: !done });

	let boundary = buffer.match(/\r?\n\r?\n/);
	while (boundary?.index !== undefined) {
		processFrame(buffer.slice(0, boundary.index));
		buffer = buffer.slice(boundary.index + boundary[0].length);
		boundary = buffer.match(/\r?\n\r?\n/);
	}
	if (done) break;
}

if (buffer.trim()) processFrame(buffer);
if (!finished) throw new Error(`Rocky stream ended without a terminal event (request ${requestId})`);
```

## Important behavior

- Concatenate only `response.output_text.delta` values for live text.
- Require increasing `sequence_number` values in applications that need strict
  contract validation.
- Do not wait for `[DONE]`; Rocky does not send that sentinel.
- An `error` event is terminal even though the HTTP status is already 200.
- `response.incomplete` is a normal terminal event for token-limit exhaustion,
  not a network error. Its response has `status: "incomplete"` and
  `incomplete_details.reason: "max_output_tokens"`; output can be partial or empty.
- A closed connection without `response.completed`, `response.incomplete`, or
  `error` is an interrupted stream. Do not mistake it for a reported token limit.
- These examples omit `max_output_tokens` to use the server default. Thinking
  shares this allowance with the visible answer. An explicit smaller limit is
  honored without a hidden retry or automatic increase.
- Keep `x-request-id` for troubleshooting, but never log the API key.
