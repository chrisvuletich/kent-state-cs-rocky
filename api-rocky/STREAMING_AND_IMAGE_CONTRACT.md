# Streaming and image-input contract

This document defines Rocky's current public and internal streaming and image
contracts. The student-facing Responses stream is translated from Granite's
private Ollama stream. Bounded base64 image input works with buffered or
streamed text output, and the built-in SvelteKit chat consumes both capabilities
with durable owned-history rendering. Student examples, capability-aware
deployment checks, the local release gate, configuration-doctor comparisons,
and official SDK tests cover the advertised paths. Each feature remains
independently disabled by default: streaming must be enabled in Granite, Rocky,
and the web frontend, while image input must be enabled in Granite and Rocky.

The public shape follows the OpenAI Responses API's documented SSE and
`input_image` conventions:

- <https://developers.openai.com/api/docs/guides/streaming-responses>
- <https://developers.openai.com/api/docs/guides/images-vision>

## Public successful text stream

`POST /v1/responses` with `stream: true` returns
`Content-Type: text/event-stream`. Each frame has matching `event` and payload
`type` values:

```text
event: response.output_text.delta
data: {"type":"response.output_text.delta",...}

```

Rocky's text-only success sequence is:

1. `response.created`
2. `response.in_progress`
3. `response.output_item.added`
4. `response.content_part.added`
5. One or more `response.output_text.delta` events
6. `response.output_text.done`
7. `response.content_part.done`
8. `response.output_item.done`
9. `response.completed`

Contract invariants:

- `sequence_number` begins at zero and increases by one for every event.
- One response ID is used by every lifecycle event.
- One message/item ID is used by every content event.
- The initial response and message are `in_progress`; final copies are
  `completed`.
- Rocky's first subset has one output item and one text content part, both at
  index zero.
- Concatenating the deltas exactly equals every final text representation.
- Rocky declares `logprobs: []`; log probabilities are outside this subset.
- The stream contains no `[DONE]` sentinel. `response.completed` is terminal.

The required HTTP headers are:

```text
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

The normal Rocky request ID and request-rate-limit headers remain present.
Trusted built-in web-chat streams also receive `X-Rocky-Conversation-Id` and
`X-Rocky-Message-Stored`. These Rocky-specific headers let the web client
reconcile durable history if a student stops or loses the stream; ordinary API
requests do not receive them.

The golden public stream is
[`run-test/fixtures/responses_text_stream.sse`](../run-test/fixtures/responses_text_stream.sse).
Tests validate it against Rocky's contract helpers and the current official
OpenAI Python SDK event models.

Pre-stream failures remain ordinary JSON errors with their real HTTP status.
After the first SSE byte, failures use the official SDK-compatible `error`
event because the HTTP status can no longer change:

```text
event: error
data: {"type":"error","sequence_number":5,"code":"model_timeout","message":"Model request timed out.","param":null}

```

Rocky validates Granite's status, media type, first event, and configured model
before sending the public SSE prefix. Midstream provider details are sanitized.
A downstream disconnect closes Granite, which closes Ollama. If generation is
still underway, Rocky records a failed interaction with
`error_type=client_disconnected`, including any partial generated text. If the
model already completed while Rocky was emitting its final SSE frames, the
model outcome remains completed and the separate delivery status records
`client_disconnected` instead of falsely claiming that the client received
`response.completed`.

On success, response/context storage and required audit persistence complete
before Rocky emits `response.completed`. If required terminal logging fails,
Rocky deletes any newly saved continuation context and emits `error` instead of
claiming completion. Delivery is marked completed only after the terminal frame
has actually been yielded.

Buffered responses use the same fail-closed finalization rule. If required
terminal logging fails after a continuation context or built-in chat messages
were written, Rocky deletes the continuation context and retains the chat
messages with `failed` status rather than leaving an unaudited success behind.

## Built-in web chat stream

The built-in web chat keeps the SvelteKit proxy streaming end to end. It requests SSE only
when `ROCKY_ENABLE_STREAMING=true`, returns the upstream `ReadableStream`
without buffering it, and sends `X-Accel-Buffering: no` so the outer Nginx
proxy forwards deltas immediately. When the flag is false, the established
buffered JSON chat remains available for a safe staged rollout.

The browser decoder accepts only the ordered text-event subset above, requires
contiguous sequence numbers, handles split UTF-8 and CRLF framing, and fails
closed on malformed, incomplete, or mismatched terminal data. The UI creates
one assistant message, updates it for each delta, marks it sent only after
`response.completed`, and preserves partial output as incomplete when a
terminal stream error occurs. Stopping aborts the fetch and refreshes the owned
conversation using the Rocky-specific response headers. The retained failed
prompt and partial response remain visible for institutional review, while the
immediate stop reconciliation does not offer a duplicate retry action.

## Internal Granite stream

Granite exposes a private `application/x-ndjson` stream when its rollout flag is
enabled and the internal request contains `"stream": true`. This is not a
student-facing contract and deliberately does not expose Ollama's provider
event format. Requests without `"stream": true` retain the existing JSON
response. Ollama's upstream framing follows its documented
[NDJSON streaming format](https://docs.ollama.com/api/streaming).

The event shapes are:

```json
{"type":"started","model":"gemma4:latest"}
{"type":"delta","text":"Hello"}
{"type":"completed","telemetry":{},"metadata":{}}
{"type":"error","error":{"type":"model_timeout","message":"Timed out."}}
{"type":"cancelled"}
```

Every stream:

- Begins with exactly one `started` event.
- Contains only `delta` events between start and termination.
- Ends with exactly one of `completed`, `error`, or `cancelled`.
- Requires at least one non-empty delta before `completed`.
- Rejects unknown event fields so provider details cannot leak accidentally.

Ollama's newline-delimited stream is decoded incrementally with a 1 MiB line
limit and 16 MiB total limit. UTF-8 and JSON are strict, raw reasoning text is
discarded, and only allowlisted final telemetry is retained. Upstream failures
before Granite starts its response remain JSON errors with their real status;
failures after `started` become a terminal sanitized `error` event.

If the downstream connection closes, Granite closes the Ollama response and
releases its inference slot. No `cancelled` event can be delivered over a
connection that is already gone; that event is reserved for a future explicit
in-band cancellation mechanism.

The golden internal stream is
[`run-test/fixtures/granite_text_stream.ndjson`](../run-test/fixtures/granite_text_stream.ndjson).

## Public image-input subset

The initial public image contract uses an OpenAI-style content block:

```json
{
  "type": "input_image",
  "image_url": "data:image/png;base64,...",
  "detail": "auto"
}
```

Image-input rules:

- Accept base64 data URLs only.
- Accept JPEG, PNG, and static WebP only after server-side container and pixel
  verification.
- Accept `detail` omitted or set to `auto`.
- Allow images only in user messages.
- Reject remote URLs, `file_id`, SVG, animation, audio, and video.
- Produce text output only, with or without streaming.
- Recheck normalized images at Granite before sending them through Ollama's
  per-message `images` array.
- Preserve the submitted order of text and image content blocks. When text
  follows an image, Granite represents the interleaving as consecutive ordered
  Ollama message fragments because Ollama separates message text from its image
  array.
- Persist the original public request for institutional auditing and retain
  normalized image blocks in stored continuation context.

Rocky enforces the configured image count, per-image decoded-byte,
request-wide decoded-byte, per-image pixel, and request-wide pixel limits
before inference. It rejects
remote URLs, malformed base64, declared/actual format mismatches, corrupt or
truncated pixel data, unexpected image fields, images on non-user messages,
and animated files. Granite independently checks the normalized field set,
hash, decoded length, dimensions, format, animation state, and budgets.

The permanent audit request retains the submitted `image_url`, consistent with
Rocky's institutional logging policy. The separately normalized `model_input`
record replaces its duplicate base64 field with an omission marker and records
safe image metadata including SHA-256, dimensions, media type, and byte length.

The canonical request fixture is
[`run-test/fixtures/responses_image_input.json`](../run-test/fixtures/responses_image_input.json).
It is accepted only when `ROCKY_ENABLE_IMAGE_INPUT=true` in both services.

## Built-in web chat image input

The built-in web chat discovers image support through an authenticated SvelteKit capability
route backed by Rocky's `/ready` response. The attachment control is enabled
only when `/ready` is healthy, Rocky and Granite both report image input, and
their configured limits match. No additional browser-visible rollout setting is
required.

The composer accepts local JPEG, PNG, and WebP files through its file picker,
paste, or drag and drop. It checks count, decoded file bytes, and browser-decoded
pixel dimensions before creating previews, while Rocky and Granite remain the
authoritative validators. A student may remove previews or send an image-only
message. The browser sends Base64 data URLs to its SvelteKit route; that route
strictly reconstructs one user message containing `input_text` and
`input_image` blocks and rejects remote URLs or extra image fields.

Optimistic messages retain their preview data through JSON or streamed output,
failure, retry, and cancellation. Owned conversation history converts private
normalized image records back to the same safe public data-URL subset, so
reopened conversations show their images without exposing Granite's internal
image-block shape. Markdown exports record the number of attached images but do
not embed multi-megabyte data URLs.

## Rollout configuration

```dotenv
ROCKY_ENABLE_STREAMING=false
ROCKY_ENABLE_IMAGE_INPUT=false
ROCKY_MAX_IMAGES_PER_REQUEST=4
ROCKY_MAX_IMAGE_BYTES=4194304
ROCKY_MAX_IMAGE_TOTAL_BYTES=6291456
ROCKY_MAX_IMAGE_PIXELS=20000000
ROCKY_MAX_IMAGE_TOTAL_PIXELS=40000000
```

Both flags default to false and accept only the literal values `true` or
`false`. Streaming and image input each require their matching flag in both the
Rocky chat API and Granite service environments. This permits independent
rollback at either layer. Image limits must be positive, at most 16 images may be
configured, and the total decoded-byte limit cannot be lower than the per-image
limit. The total pixel limit cannot be lower than the per-image pixel limit.

`ROCKY_MAX_REQUEST_BYTES` remains 262144 while image input is disabled. Set it
to 9437184 with the example image budgets before enabling image input. Granite uses
`ROCKY_GRANITE_MAX_REQUEST_BYTES=10485760`. Startup and `manage.py doctor`
reject either limit when it cannot carry the configured decoded image budget.
The tracked Nginx route retains a hard 10 MiB outer ceiling.
