# Streaming Example

Streaming lets an application display text as Rocky generates it. Rocky uses
Server-Sent Events (SSE) and the Responses API lifecycle. Check
`data[0].metadata.supports_streaming` from `GET /v1/models` before exposing a
streaming option.

## Python with requests

`requests.iter_lines()` preserves SSE line boundaries even when network chunks
split a JSON event. The example prints text deltas immediately and accepts only
`response.completed` as success.

```python
import json
import os
import requests

url = "https://rocky.cs.kent.edu/v1/responses"
headers = {
    "Authorization": f"Bearer {os.environ['ROCKY_API_KEY']}",
    "Accept": "text/event-stream",
}
payload = {
    "model": os.environ["ROCKY_MODEL"],
    "input": "Explain recursion in one paragraph.",
    "stream": True,
    "store": False,
}

completed = False
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
            completed = True
            print()

if not completed:
    raise RuntimeError(f"Rocky stream ended before completion (request {request_id})")
```

## JavaScript with fetch

Network chunks do not necessarily align with SSE frames or UTF-8 characters.
Use a streaming `TextDecoder`, keep the unfinished tail, and split only on a
blank SSE line.

```javascript
const apiKey = process.env.ROCKY_API_KEY;
const model = process.env.ROCKY_MODEL;

const response = await fetch("https://rocky.cs.kent.edu/v1/responses", {
	method: "POST",
	headers: {
		"Authorization": `Bearer ${apiKey}`,
		"Content-Type": "application/json",
		"Accept": "text/event-stream"
	},
	body: JSON.stringify({
		model,
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
let completed = false;

function processFrame(frame) {
	let eventName;
	const dataLines = [];
	for (const line of frame.split(/\r?\n/)) {
		if (line.startsWith(":")) continue;
		if (line.startsWith("event:")) eventName = line.slice(6).trim();
		else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
		else throw new Error("Malformed Rocky SSE field");
	}
	if (!eventName || dataLines.length === 0) throw new Error("Incomplete Rocky SSE frame");

	const event = JSON.parse(dataLines.join("\n"));
	if (event.type !== eventName) throw new Error("SSE event name and data.type did not match");
	if (eventName === "response.output_text.delta") process.stdout.write(event.delta);
	else if (eventName === "error") {
		throw new Error(`${event.code}: ${event.message} (request ${requestId})`);
	} else if (eventName === "response.completed") {
		completed = true;
		process.stdout.write("\n");
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
if (!completed) throw new Error(`Rocky stream ended before completion (request ${requestId})`);
```

## Important behavior

- Concatenate only `response.output_text.delta` values for live text.
- Require increasing `sequence_number` values in applications that need strict
  contract validation.
- Do not wait for `[DONE]`; Rocky does not send that sentinel.
- An `error` event is terminal even though the HTTP status is already 200.
- A closed connection without `response.completed` or `error` is incomplete.
- Keep `x-request-id` for troubleshooting, but never log the API key.
