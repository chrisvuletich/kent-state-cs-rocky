# Rocky Ubuntu Deployment

This deployment runs Rocky from `/var/www/rocky/current` with nginx as the public reverse proxy.

Services:

- `rocky-frontend.service`: SvelteKit Node server on `127.0.0.1:8000`.
- `rocky-backend.service`: Flask/Gunicorn API on `127.0.0.1:5001`.
- `rocky-granite.service`: Granite/Ollama bridge on `127.0.0.1:5002`.
- `rocky-chat-api.service`: Chat API on `127.0.0.1:5003`.

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

Set the same long random `ROCKY_HIDDEN_API_KEY_SECRET` in both `/etc/rocky/backend.env` and `/etc/rocky/frontend.env` so the built-in web chat can use each user's hidden key.
