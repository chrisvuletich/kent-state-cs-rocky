# Root Dev Runner

Run from the repository root with Python. Normal startup preserves the current
local database.

```sh
python run-dev.py --mode both
```

Use `--seed` only when you intentionally want to load the fixtures:

```sh
python run-dev.py --mode both --seed
```

Other modes:

- `python run-dev.py --mode backend`
- `python run-dev.py --mode frontend`

If your system uses `python3`, substitute it for `python`.

## What Mode both does

1. Starts the Granite model bridge when the configured Granite URL is local.
2. Starts the student-facing Chat API.
3. Starts the management backend using `ROCKY_API_HOST` and `ROCKY_API_PORT`.
4. Starts the optional hardware sampler when hardware telemetry is enabled.
5. Starts the frontend using `ROCKY_WEB_HOST`, `ROCKY_WEB_PORT`, and
   `ROCKY_ALLOWED_HOSTS`, pointed at the local backend and Chat API.

Ollama and the configured model must already be available for inference. See
the root [README](README.md) for setup and configuration details.
