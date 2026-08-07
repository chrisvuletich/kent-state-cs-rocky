# Rocky Ubuntu Deployment

This deployment runs Rocky from `/var/www/rocky/current` with nginx as the public reverse proxy.

Services:

- `rocky-frontend.service`: SvelteKit Node server on `127.0.0.1:8000`.
- `rocky-backend.service`: Flask/Gunicorn API on `127.0.0.1:5001`.
- `rocky-granite.service`: Granite/Ollama bridge on `127.0.0.1:5002`.
- `rocky-chat-api.service`: Chat API on `127.0.0.1:5003`.
- `rocky-hardware-sampler.service`: bounded Granite hardware history collector.

The tracked service files are examples:

- Replace `{{ROCKY_USER}}` with the Linux user that should run the app.
- Replace `{{ROCKY_GROUP}}` with that user's primary group or another readable app group.
- Replace `{{ROCKY_APP_DIR}}` with the absolute app path, for example `/var/www/rocky/current`.

Copy the edited files to `/etc/systemd/system/*.service`, then run:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now rocky-backend rocky-granite rocky-chat-api rocky-frontend
```

Environment files stay outside the repo:

- `/etc/rocky/frontend.env`
- `/etc/rocky/backend.env`

For a true production database, add these to `/etc/rocky/backend.env` and restart `rocky-backend.service`:

```sh
ROCKY_APP_ENV=production
ROCKY_DB_BACKEND=mongodb
ROCKY_MONGODB_URI=...
```

The chat API reads API keys from the same database, so `ROCKY_DB_NAME` and the MongoDB settings must be identical for `rocky-backend` and `rocky-chat-api`. Keep the Granite bridge and Ollama private; nginx exposes only the frontend and `POST /v1/responses`.

Set the same long random `ROCKY_HIDDEN_API_KEY_SECRET` in both `/etc/rocky/backend.env` and `/etc/rocky/frontend.env` so the built-in web chat can use each user's hidden key. Also set the same independent `ROCKY_INTERNAL_PROXY_SECRET` in both files; Flask rejects forwarded user and administrator headers without it. Set a third independent `ROCKY_SESSION_SECRET` in `/etc/rocky/frontend.env` for signed web sessions. Both new secrets must contain at least 32 characters in production.

Microsoft login additionally requires the specific Kent tenant and application client IDs in `/etc/rocky/frontend.env`:

```sh
PUBLIC_MICROSOFT_CLIENT_ID=...
PUBLIC_MICROSOFT_TENANT_ID=...
ROCKY_SESSION_SECRET=...
ROCKY_INTERNAL_PROXY_SECRET=...
```

## Telemetry schema-v2 migration

Before restarting the chat API with permanent request logging for the first
time, back up MongoDB and run the telemetry migration from the release checkout:

```sh
set -a
. /etc/rocky/backend.env
set +a
.venv/bin/python api-rocky/migrate_telemetry_v2.py --dry-run
.venv/bin/python api-rocky/migrate_telemetry_v2.py
```

Production defaults to `ROCKY_REQUIRE_REQUEST_LOGGING=true`; set it explicitly
in `/etc/rocky/backend.env` to document that unlogged inference is prohibited.

The backend reads Phase 2 analytics from the same `telemetry_interactions` and
`telemetry_current` collections. No additional service, scheduler, or database
is required. After deploying, restart both `rocky-chat-api` and `rocky-backend`
so the writer and analytics API use the same schema and indexes.

## Granite hardware history

Hardware measurements must be collected on Granite itself. Install the
metrics-only app and `granite-hardware-metrics.service.example` on Granite,
bind it to a private address, and allow its port only from Rocky. Use the same
long random token in Granite's `/etc/rocky/hardware.env` and Rocky's
`/etc/rocky/backend.env`:

```sh
ROCKY_APP_ENV=production
ROCKY_HARDWARE_METRICS_TOKEN=...
```

Rocky's backend environment additionally needs:

```sh
ROCKY_HARDWARE_TELEMETRY_ENABLED=true
ROCKY_HARDWARE_METRICS_URL=http://granite.cs.kent.edu:5010/hardware
ROCKY_HARDWARE_SAMPLE_INTERVAL_SECONDS=30
ROCKY_HARDWARE_RETENTION_DAYS=90
```

Install and start `rocky-hardware-sampler.service` on Rocky after confirming
the private Granite `/health` endpoint is reachable. The sampler stores only
numeric hardware/model state and host/model names; it does not receive prompts,
responses, API keys, or Microsoft credentials.
