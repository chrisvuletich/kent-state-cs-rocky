# Rocky Model Bridge

This is an internal Flask bridge between the Rocky chat API and Ollama. It is not a public student API and should bind to loopback or another private network interface.

Copy `.env.example` to `.env`, ensure Ollama is running with the configured `OLLAMA_MODEL`, and start it from this directory:

```sh
python -m app.main
```

The public chat service maps model `rocky` to the configured Ollama model before calling this bridge.

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
