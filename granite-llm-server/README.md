# Rocky Model Bridge

This is an authenticated internal Flask bridge between the Rocky chat API and
Ollama. It is not a public student API and should bind to loopback or an
interface restricted to Rocky.

Copy `.env.example` to `.env`, ensure Ollama is running with the configured `OLLAMA_MODEL`, and start it from this directory:

```sh
python -m app.main
```

The bridge validates environment names, service URLs, ports, limits, and
timeouts at startup. Invalid values fail immediately with the setting name;
omitted optional values use the defaults in `.env.example`.

`ROCKY_ENABLE_STREAMING` is a disabled-by-default rollout gate for Granite's
internal text stream. When enabled, `POST /generate` accepts `"stream": true`,
requests Ollama's chat stream, and returns provider-neutral NDJSON. The regular
JSON response remains the default. `ROCKY_ENABLE_IMAGE_INPUT` gates Rocky's
strictly normalized private image blocks and maps them to
Ollama's per-message `images` array. Both JSON and streaming generation support
them. The complete contract is documented in
[`../api-rocky/STREAMING_AND_IMAGE_CONTRACT.md`](../api-rocky/STREAMING_AND_IMAGE_CONTRACT.md)
and enforced by `app/stream_contract.py` tests.

```sh
curl -N http://127.0.0.1:5002/generate \
  -H "Content-Type: application/json" \
  -H "X-Rocky-Granite-Token: $ROCKY_GRANITE_TOKEN" \
  -d '{
    "model": "gemma4:latest",
    "input": [{
      "role": "user",
      "content": [{"type": "input_text", "text": "Hello"}]
    }],
    "stream": true
  }'
```

The bridge bounds individual provider lines to 1 MiB and each provider stream
to 16 MiB. A downstream disconnect closes the Ollama response and releases the
inference slot immediately.

Rocky consumes this private stream and translates it into public Responses SSE.
Granite performs defense-in-depth image verification before contacting Ollama.
Public rollout for either feature requires its matching flag in both services,
and Granite readiness verifies the installed Ollama model advertises `vision`
before image input can be ready.

Set the same `ROCKY_GRANITE_TOKEN` here and on the Rocky chat API. The public
model identifier is configured with `ROCKY_PUBLIC_MODEL`; the bridge sends the
server-controlled `OLLAMA_MODEL` to Ollama. `/ready` verifies that Ollama is
reachable and that the configured model is installed. When the bridge token is
configured, both `/generate` and `/ready` require it in
`X-Rocky-Granite-Token`.

```sh
curl http://127.0.0.1:5002/ready \
  -H "X-Rocky-Granite-Token: $ROCKY_GRANITE_TOKEN"
```

## Private hardware snapshot

`GET /hardware` returns a bounded snapshot of local CPU/RAM, NVIDIA GPU/VRAM,
loaded Ollama models, and active bridge inference requests. Production requires
`ROCKY_HARDWARE_METRICS_TOKEN`; callers send the same value in
`X-Rocky-Metrics-Token`. Missing `nvidia-smi` or Ollama data is marked partial.

The snapshot describes the host running this process. To measure Granite rather
than Rocky, run the metrics-only app on Granite:

```sh
python -m app.hardware_main
```

The metrics-only app exposes `/health` and `/hardware`, but no generation route.
Bind it to a private address, restrict its port to Rocky at the firewall, and
use the tracked `granite-hardware-metrics.service.example` for systemd.
