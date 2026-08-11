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
