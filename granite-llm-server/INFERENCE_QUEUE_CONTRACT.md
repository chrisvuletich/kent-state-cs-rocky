# Granite inference queue contract

Status: rollout candidate. The isolated queue, shared buffered and streaming
admission, disconnect cleanup, private heartbeats, bounded queue telemetry, and
deployment timeout ladder are implemented and covered by automated tests. A
deterministic route test exercises six validated concurrent requests, and the
deployment smoke tool has an explicit six-client queue-burst mode for live
rollout verification.

This document defines the bounded in-memory admission queue for Granite model
generation. It is intentionally limited to one Granite process and uses Python
standard-library synchronization. It does not introduce Redis, a durable job
store, a second worker service, or a new public endpoint.

Normative terms such as **must**, **must not**, and **should** describe behavior
that the implementation and its tests are required to preserve.

## Goals

- Let short bursts of classroom requests wait for model capacity instead of
  failing after the former one-second semaphore admission wait.
- Preserve arrival order when requests contend for the same model capacity.
- Keep waiting memory, connection count, and wait duration explicitly bounded.
- Support buffered JSON and streamed NDJSON generation through the same queue.
- Release capacity after success, provider failure, timeout, or disconnect.
- Preserve Rocky's existing OpenAI-compatible public response contract.
- Expose enough operational metadata to distinguish waiting from generation.

The queue improves admission reliability but does not create model throughput.
If generation remains slower than classroom demand, concurrency or model
performance must be tuned separately using measured hardware results.

## Non-goals

- Persisting waiting requests across a Granite restart.
- Distributing work across multiple Granite processes or hosts.
- Retrying model generation automatically after Ollama has accepted a request.
- Reordering work by user role, course, prompt size, or estimated generation
  time.
- Adding a general-purpose task system.

## Deployment invariant

Exactly one Gunicorn worker may host the generation application while this
in-memory queue is enabled. That worker may use multiple threads. Multiple
workers would create independent queues and independent concurrency counters,
breaking the global capacity limit.

The metrics-only Granite application is separate and does not participate in
generation admission.

## Terms and limits

- **Active request:** a request that owns one inference slot and may contact
  Ollama.
- **Waiting request:** a validated request with a queue ticket that does not yet
  own an inference slot.
- **Queue capacity:** the maximum number of waiting requests. Active requests do
  not count against this limit.
- **Queued bytes:** the number of encoded HTTP request-body bytes retained by
  waiting requests. Active requests do not count against this limit.
- **Initial position:** `0` when immediately admitted, the one-based position
  when accepted as a waiter, and absent when rejected before enqueueing.
- **Queue wait:** elapsed monotonic time between ticket creation and admission,
  rejection, cancellation, or wait expiration.

The planned settings and initial rollout values are:

| Setting | Initial value | Meaning |
| --- | ---: | --- |
| `ROCKY_GRANITE_MAX_CONCURRENT` | `1` | Maximum active Ollama inferences. |
| `ROCKY_GRANITE_QUEUE_CAPACITY` | `12` | Maximum waiting requests. `0` disables waiting. |
| `ROCKY_GRANITE_QUEUE_MAX_BYTES` | `67108864` | Aggregate body-byte budget for waiting requests. |
| `ROCKY_GRANITE_QUEUE_WAIT_SECONDS` | `120` | Maximum time a ticket may wait. |
| `ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS` | `10` | Maximum interval between private streaming heartbeats while waiting or active; minimum `0.1`. |

The implementation recognizes all five settings. Phase 6 aligns the repository
and deployment examples on the 120-second wait and the timeout ladder below.

## Admission rules

Granite must authenticate, parse, and validate a request before it can consume
queue capacity. Invalid or unauthorized requests must never enter the queue.

Admission is decided under one synchronization lock:

1. If an inference slot is available and no older ticket is waiting, admit the
   request immediately.
2. Otherwise, reject the request if adding it would exceed the waiting-request
   capacity or queued-byte budget.
3. Otherwise, append one ticket to the tail of the FIFO queue.
4. Only tickets at the head of the queue may claim newly available inference
   slots.
5. Remove a ticket when it is admitted, cancelled, rejected, or expires, and
   notify the next eligible waiter.

New arrivals must not bypass older waiting tickets, even if more than one
inference slot is configured. When several slots become available, the oldest
eligible tickets claim them in order.

The request's raw encoded body length is its queued-byte charge. The existing
Flask request ceiling remains the authoritative per-request limit. Queued bytes
are decremented when a ticket leaves the waiting state.

Public per-key rate limiting remains upstream in the Rocky chat API. The
Granite queue provides capacity protection, not a replacement rate limiter.

## Ticket lifecycle

Each ticket has one terminal admission result:

- `admitted`
- `queue_full`
- `queue_memory_full`
- `timed_out`
- `cancelled`

An admitted ticket owns exactly one active slot. Its owner must release that
slot exactly once in a `finally` path. Queue removal and active-slot release
must be idempotent so cleanup cannot inflate capacity.

A provider exception, malformed provider response, model timeout, response
finalization failure, or downstream disconnect must not prevent the next
ticket from being admitted.

Waiting uses a monotonic clock. Wall-clock changes must not lengthen or shorten
the configured wait budget.

## Buffered request behavior

A buffered request waits in its request thread until it is admitted or reaches
a terminal admission result. Once admitted, it uses the existing Ollama JSON
request path.

When the queue cannot accept the request or its wait expires before response
headers are sent, Granite returns an ordinary JSON `503` error with:

- internal error type `model_busy`;
- a safe queue reason of `queue_full`, `queue_memory_full`, or `queue_timeout`;
- a positive whole-second `Retry-After` header; and
- no prompt, credential, provider response, or internal exception details.

Rocky continues mapping this condition to the public `model_busy` error code.

## Streaming request behavior

An accepted streaming request must establish its private response promptly,
even when its ticket is waiting. Granite may emit blank NDJSON lines as private
heartbeats; blank lines are framing keepalives, not stream events, and the Rocky
Granite client must surface them only as its private heartbeat sentinel rather
than decoding them as events.

After admission and a successful provider connection, the existing private
event sequence remains:

1. `started`
2. zero or more `delta` events while output is being produced
3. exactly one `completed` or `error` event

The existing requirement for at least one non-empty delta before successful
completion remains unchanged. Queueing must not expose Ollama events directly.
Once `started` has been emitted, Granite continues sending blank keepalives at
the configured interval whenever the blocking provider iterator has not
produced visible output. These keepalives contain no raw reasoning or provider
data.

If an accepted stream reaches its queue-wait deadline, Granite sends a terminal
private `error` event representing `model_busy`; its HTTP status remains `200`
because streaming headers were already committed. Rocky converts that event to
the existing public SDK-compatible `error` event and must not emit
`response.completed`.

No queue-specific public SSE event is required for the first implementation.
Rocky-specific headers or telemetry may expose an initial position without
changing the OpenAI-compatible event sequence.

## Cancellation and disconnects

- Closing a queued streaming request must cancel and remove its ticket.
- Closing an active stream must close Ollama and release its inference slot.
- Private heartbeats provide periodic opportunities for the server to observe
  a disconnected queued or active streaming client. Rocky relays them as SSE
  comment keepalives so each downstream proxy also gets that opportunity.
- Buffered-client disconnect detection is best effort under synchronous WSGI.
  An undetected ticket remains bounded by the configured wait deadline.
- Cancellation must never be reported as successful completion.

Explicit user cancellation continues to propagate browser to SvelteKit, Rocky,
Granite, and Ollama through connection closure. No separate cancellation
endpoint is introduced.

## Readiness and UI semantics

Queue occupancy is not a service-health failure. `/health` and `/ready` should
remain healthy while requests are active or waiting, provided Ollama and the
configured model remain ready. Readiness may include a bounded queue snapshot,
but a full queue must not make the model appear offline.

The web chat must treat `model_busy` as temporary capacity contention:

- keep the service marked available;
- honor `Retry-After` with a short retry cooldown;
- preserve the failed draft and attachments; and
- avoid disabling the composer until the next periodic health check.

An optional waiting indicator may use Rocky-specific queue metadata. It must
not promise an exact start time because earlier output length is unknown.

## Telemetry contract

Existing permanent request and response retention remains authoritative. The
queue must not create another prompt archive or copy credentials into queue
records.

Each generation interaction records a bounded `queue` object containing:

- `status`: `not_queued`, `admitted`, `queue_full`, `queue_memory_full`,
  `timed_out`, or `cancelled`;
- `initial_position`;
- `depth_on_arrival`;
- `wait_ms`;
- `capacity`; and
- `queued_bytes_on_arrival`.

All present numeric values must be finite, non-negative integers. An initial
position may be absent when a request is rejected before enqueueing.
Operational snapshots may additionally expose current waiting requests, queued
bytes, active inferences, and their configured maxima.

Public compatibility remains `model_busy`. Internal telemetry should preserve
the more specific queue reason so administrators can distinguish saturation,
memory protection, and expired waits. Queue wait must not be combined with
model-generation duration when reporting inference performance.

Granite attaches this object only to its private JSON/NDJSON responses. Rocky
strictly reconstructs the allowed fields before storing it in telemetry schema
version 3; unknown fields and malformed queue objects are discarded. Granite's
authenticated `/ready` response also reports only aggregate active, waiting,
and queued-byte counts plus their configured maxima. Queue occupancy does not
change readiness health.

## Timeout ordering

For buffered requests, every downstream timeout must cover the maximum queue
wait plus the maximum Ollama request time and a small transport margin:

```text
Ollama timeout
  < queue wait + Ollama timeout + margin
  < Granite Gunicorn timeout
  < Rocky-to-Granite client timeout
  < Rocky chat API Gunicorn timeout
  < Nginx proxy timeout
```

The tracked Phase 6 values are:

| Layer | Timeout |
| --- | ---: |
| Ollama request | 150 seconds |
| Granite queue wait | 120 seconds |
| Granite Gunicorn | 300 seconds |
| Rocky-to-Granite client | 315 seconds |
| Rocky chat API Gunicorn | 330 seconds |
| Nginx public response and frontend proxy | 360 seconds |

The 300-second Granite service budget covers the 270-second worst-case queue
plus model interval with 30 seconds of internal transport margin. Each outer
layer then expires later than the layer it supervises. Streaming heartbeats
reduce idle-read risk but do not replace this ordering for buffered requests.
Granite and Rocky expose their safe timeout configuration through authenticated
readiness responses; Rocky refuses readiness when the two services disagree.

Granite and Rocky thread counts must also accommodate the bounded number of
waiting and active connections plus health-check headroom. Increasing Gunicorn
workers is not an acceptable substitute because it would split the queue.

## Acceptance criteria

The implementation is complete only when automated tests demonstrate:

1. Six simultaneous validated requests are admitted in FIFO order with one
   active inference and without immediate `model_busy` failures.
2. Active inference never exceeds the configured maximum.
3. Queue count and byte limits reject excess work deterministically.
4. Buffered and streaming requests share the same admission order.
5. Queued and active silent streams remain connected through private
   heartbeats.
6. Cancelling a queued request removes it and advances the next ticket.
7. Cancelling active generation releases its slot.
8. Success, provider error, malformed output, and timeout all release capacity.
9. Queue timeout produces `model_busy` without a false completion event.
10. Queue saturation does not change readiness to unavailable.
11. Queue metadata contains no prompt, image data, credential, or exception
    details.
12. Existing buffered, streaming, image, retention, rate-limit, and official
    SDK compatibility tests continue to pass.

The final deployment check should repeat the six-client classroom burst with
short controlled prompts, then compare completion count, queue waits, model
latency, and failure reasons against the August 26 incident baseline.

Run that check after the Phase 6 timeout ladder and longer queue wait are
deployed, using `deployment_smoke.py --include-queue-burst`. The command prints
the six correlated request IDs so their permanent queue telemetry can be
reviewed without exposing queue internals through the public API.
