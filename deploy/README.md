# Rocky Ubuntu Deployment

This deployment runs the web/API services on Rocky and the model bridge beside
Ollama on Granite. Nginx on Rocky is the only public API entry point.

Services:

- `rocky-frontend.service`: SvelteKit Node server on `127.0.0.1:8000`.
- `rocky-backend.service`: Flask/Gunicorn API on `127.0.0.1:5001`.
- `rocky-granite.service`: authenticated Granite/Ollama bridge on Granite port `5002`.
- `granite-hardware-metrics.service`: optional private Granite hardware endpoint on port `5010`.
- `rocky-chat-api.service`: Chat API on `127.0.0.1:5003`.
- `rocky-hardware-sampler.service`: optional bounded Granite hardware history collector on Rocky.

The tracked service files are examples. Replace every placeholder before
installing them:

| Placeholder | Meaning |
| --- | --- |
| `{{ROCKY_USER}}` | Linux user that runs the Rocky services and backups. |
| `{{ROCKY_GROUP}}` | That user's primary group or another readable application group. |
| `{{ROCKY_APP_DIR}}` | Absolute release path on the relevant host. |
| `{{GRANITE_BIND_IP}}` | Private Granite address used by the model bridge. |
| `{{GRANITE_USER}}` | Linux user that runs the Granite metrics-only service. |
| `{{GRANITE_GROUP}}` | That user's primary group or another readable application group. |
| `{{GRANITE_PRIVATE_IP}}` | Private Granite address used by the metrics-only service. |

Copy the edited files to `/etc/systemd/system/*.service`, then run:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now rocky-backend rocky-chat-api rocky-frontend
```

On Granite, install `rocky-granite.service.example` and run:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now rocky-granite
```

After loading `/etc/rocky/granite.env`, verify the installed unit on Granite:

```sh
python manage.py doctor \
  --deployment-files-only \
  --deployment-host granite \
  --env-file /etc/rocky/granite.env
```

If hardware history is enabled, also install and start
`granite-hardware-metrics.service.example` on Granite and
`rocky-hardware-sampler.service.example` on Rocky after configuring the
environment files described below.

Environment files stay outside the repo:

- `/etc/rocky/frontend.env`
- `/etc/rocky/backend.env`
- `/etc/rocky/granite.env` on Granite
- `/etc/rocky/hardware.env` on Granite when hardware history is enabled

For a true production database, add these to `/etc/rocky/backend.env` and restart `rocky-backend.service`:

```sh
ROCKY_APP_ENV=production
ROCKY_DB_BACKEND=mongodb
ROCKY_MONGODB_URI=...
```

The chat API reads API keys from the same database, so `ROCKY_DB_NAME` and the MongoDB settings must be identical for `rocky-backend` and `rocky-chat-api`. Nginx exposes only the frontend, `POST /v1/responses`, and `GET /v1/models`.

The tracked Nginx configuration also applies a coarse 120-request-per-minute
per-client-address limit, with a bounded burst, to both public API routes. This
protects permanent audit storage from unauthenticated floods; application-level
per-key limits remain authoritative for normal API use. Requests rejected at
the Nginx boundary remain visible in the Nginx access log but do not have a
Rocky request ID because they never reach the application.

Set the same long random `ROCKY_HIDDEN_API_KEY_SECRET` in both `/etc/rocky/backend.env` and `/etc/rocky/frontend.env` so the built-in web chat can use each user's hidden key. Also set the same independent `ROCKY_INTERNAL_PROXY_SECRET` in both files; Flask rejects forwarded user and administrator headers without it. Set a third independent `ROCKY_SESSION_SECRET` in `/etc/rocky/frontend.env` for signed web sessions. Both new secrets must contain at least 32 characters in production.

Set one additional long random `ROCKY_GRANITE_TOKEN` in Rocky's
`/etc/rocky/backend.env` and Granite's `/etc/rocky/granite.env`. Configure the
student-facing model and Granite URL in Rocky's `/etc/rocky/backend.env`:

```sh
ROCKY_PUBLIC_MODEL=gemma4:latest
OLLAMA_MODEL=gemma4:latest
ROCKY_GRANITE_URL=http://GRANITE_PRIVATE_ADDRESS:5002/generate
ROCKY_GRANITE_READY_URL=http://GRANITE_PRIVATE_ADDRESS:5002/ready
ROCKY_GRANITE_TOKEN=...
ROCKY_GRANITE_TIMEOUT_SECONDS=315
ROCKY_OLLAMA_TIMEOUT_SECONDS=150
ROCKY_GRANITE_QUEUE_WAIT_SECONDS=120
ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS=10
ROCKY_GRANITE_MAX_CONCURRENT=1
ROCKY_GRANITE_QUEUE_CAPACITY=12
ROCKY_GRANITE_QUEUE_MAX_BYTES=67108864
ROCKY_MAX_CONTEXT_CHARS=60000
ROCKY_MAX_OUTPUT_TOKENS=2048
ROCKY_MAX_REQUEST_BYTES=262144
ROCKY_ENABLE_STREAMING=false
ROCKY_ENABLE_IMAGE_INPUT=false
```

Set the same student-facing model in `/etc/rocky/frontend.env` so the built-in
chat sends the advertised identifier. Set the SvelteKit request ceiling to the
same bounded 10 MiB used by Nginx; its 512 KiB default is too small for Base64
image attachments. Keep the streaming flag aligned with the Rocky chat API
during rollout:

```sh
ROCKY_PUBLIC_MODEL=gemma4:latest
ROCKY_ENABLE_STREAMING=false
BODY_SIZE_LIMIT=10M
```

Granite's `/etc/rocky/granite.env` needs:

```sh
ROCKY_APP_ENV=production
ROCKY_GRANITE_TOKEN=...
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:latest
ROCKY_MAX_OUTPUT_TOKENS=2048
ROCKY_OLLAMA_TIMEOUT_SECONDS=150
ROCKY_GRANITE_MAX_CONCURRENT=1
ROCKY_GRANITE_QUEUE_CAPACITY=12
ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS=10
ROCKY_GRANITE_QUEUE_MAX_BYTES=67108864
ROCKY_GRANITE_QUEUE_WAIT_SECONDS=120
ROCKY_GRANITE_MAX_REQUEST_BYTES=10485760
ROCKY_ENABLE_STREAMING=false
ROCKY_ENABLE_IMAGE_INPUT=false
ROCKY_MAX_IMAGES_PER_REQUEST=4
ROCKY_MAX_IMAGE_BYTES=4194304
ROCKY_MAX_IMAGE_TOTAL_BYTES=6291456
ROCKY_MAX_IMAGE_PIXELS=20000000
ROCKY_MAX_IMAGE_TOTAL_PIXELS=40000000
```

Granite uses a bounded, process-local FIFO queue when its inference slots are
occupied. Buffered generation and queued and active stream heartbeats are
integrated now. The tracked service examples provide 16 total request threads
in each chat-facing service, enough for the default one active request, twelve
waiters, and health-check headroom. If queue capacity or active capacity is
increased, increase total threads to at least active capacity plus queue
capacity plus two; keep Granite at exactly one worker so it retains one global
in-memory queue.
Timeout ordering, final deployment settings, and rollout acceptance criteria
are defined in
[`../granite-llm-server/INFERENCE_QUEUE_CONTRACT.md`](../granite-llm-server/INFERENCE_QUEUE_CONTRACT.md).
The tracked Phase 6 ladder is now 150 seconds for Ollama, 120 seconds for queue
waiting, 300 seconds for Granite Gunicorn, 315 seconds for Rocky's Granite
client, 330 seconds for Rocky chat API Gunicorn, and 360 seconds for Nginx.
Apply the environment, systemd, and Nginx changes together. Authenticated
readiness and `manage.py doctor` reject mismatched Granite timeout settings.
Bounded queue telemetry remains available in permanent interaction records and
the Rocky `/ready` aggregate queue snapshot.

To roll out Responses streaming, first deploy this code with the flag left
`false` in all three environments. Then set `ROCKY_ENABLE_STREAMING=true` in Granite's environment and
restart `rocky-granite`. After its `/ready` check passes, set the same flag in
Rocky's backend environment and restart `rocky-chat-api`. Verify the public
stream, then enable the flag in `/etc/rocky/frontend.env` and restart the web
service. To roll back without disrupting built-in chat, disable the frontend
flag first, then disable Rocky, and finally Granite. The public API location
disables buffering directly; the SvelteKit stream sends `X-Accel-Buffering: no`
through the general frontend location so browser deltas are also forwarded
immediately.

Verify one short streamed request from a shell that keeps the API key outside
tracked files:

```sh
curl -N "$ROCKY_BASE_URL/v1/responses" \
  -H "Authorization: Bearer $ROCKY_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$ROCKY_EXPECTED_MODEL\",\"input\":\"Reply with hello.\",\"stream\":true,\"store\":false}"
```

The stream should begin with `response.created`, end with
`response.completed`, and include no `[DONE]` sentinel.

After enabling the frontend flag, verify that a longer built-in chat response
appears incrementally, its Stop control cancels an in-progress stream, and the
conversation can be reopened from history afterward.

To roll out image input, first confirm the installed Ollama model advertises
the `vision` capability. Leave both image flags `false` while deploying, set
`ROCKY_GRANITE_MAX_REQUEST_BYTES=10485760`, then enable
`ROCKY_ENABLE_IMAGE_INPUT=true` on Granite and restart it. After Granite
readiness passes, configure the same image count, byte, and pixel limits in
Rocky and Granite, set Rocky's `ROCKY_MAX_REQUEST_BYTES=9437184`, enable the
same image flag there, and restart `rocky-chat-api`. Rocky readiness rejects a
limit mismatch. On the next chat load, the web application reads this readiness
contract and exposes its local image picker automatically; there is no separate
frontend image flag. Disable Rocky's flag first
to roll back. The tracked Nginx route has a fixed 10 MiB outer body ceiling;
configure Rocky's application ceiling back to 256 KiB after disabling image
input.

Image input accepts only base64 data URLs containing JPEG, PNG, or static WebP
images with `detail` omitted or `auto`; it intentionally rejects remote URLs,
file IDs, GIF/SVG, animation, audio, and video. Validate one request using the
shape in `run-test/fixtures/responses_image_input.json`, replacing its model
with the identifier returned by `/v1/models`.

Finally, verify the built-in chat with a local JPEG, PNG, or WebP: confirm its
preview can be removed, an image-only turn can be sent, text output can stream,
and the attached image remains visible after reopening the conversation.

For a direct readiness check on Granite, load `/etc/rocky/granite.env` and send
`ROCKY_GRANITE_TOKEN` in the `X-Rocky-Granite-Token` header. Rocky's own
`/ready` endpoint performs this authenticated check automatically.

Allow Granite port `5002` only from Rocky. If the connection is not on an
isolated private network, place it behind an SSH tunnel or TLS rather than
sending prompts and the internal token over plaintext HTTP.

Microsoft login additionally requires the specific Kent tenant and application client IDs in `/etc/rocky/frontend.env`:

```sh
PUBLIC_MICROSOFT_CLIENT_ID=...
PUBLIC_MICROSOFT_TENANT_ID=...
ROCKY_SESSION_SECRET=...
ROCKY_INTERNAL_PROXY_SECRET=...
```

Production defaults to `ROCKY_REQUIRE_REQUEST_LOGGING=true`; set it explicitly
in `/etc/rocky/backend.env` to document that unlogged inference is prohibited.

The backend reads live analytics from the same `telemetry_interactions` and
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

After creating `/etc/rocky/hardware.env`, start the private endpoint on Granite:

```sh
sudo systemctl enable --now granite-hardware-metrics
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

## Verify a deployment

The concise operator sequence is in
[`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md). The sections below provide the
configuration rationale, individual verification commands, and recovery detail.

Before copying a release to either host, run the complete local acceptance gate
from the candidate checkout:

```sh
python run-test/test_all.py
```

The command is non-deploying and uses testing-mode frontend configuration. It
runs the backend, Granite, Node, production-build, and Selenium surfaces and
returns nonzero if any step fails. Unlike the public smoke test below, it does
not submit requests to the deployed model.

Run the configuration doctor from the release checkout on Rocky after loading
both production environment files. It reads configuration, pings MongoDB, and
checks the backend, chat API, Granite, Ollama, and model mapping. It does not
write application data or print secret values.

```sh
cd {{ROCKY_APP_DIR}}
source .venv/bin/activate
python manage.py doctor \
  --deployment-files \
  --deployment-host rocky \
  --env-file /etc/rocky/backend.env \
  --env-file /etc/rocky/frontend.env
```

Use `--skip-network` to inspect configuration without contacting services. A
successful run exits `0`; a failed check exits `1`; invalid command usage exits
`2`.

With `--deployment-files`, the Rocky doctor validates its installed chat
systemd worker/timeout settings and Nginx proxy timeouts. Granite uses the
file-only command shown above because it is a separate host. Use
`--deployment-host all` only for a combined installation. The default paths may
be overridden with `--granite-unit`, `--chat-unit`, and `--nginx-config`.

The doctor also compares the loaded queue limits, `ROCKY_ENABLE_STREAMING`,
`ROCKY_ENABLE_IMAGE_INPUT`, and image-limit settings with the capabilities and
Rocky/Granite rollout state reported by the chat API's `/ready` response. This
catches a frontend environment file, Rocky service, or Granite service left on
different rollout settings before student traffic is enabled.

Then verify the same public routes students use. Read the key without echoing it
or writing it into shell history, keep it only in the current shell environment,
and unset it immediately after the check.

```sh
export ROCKY_BASE_URL='https://rocky.cs.kent.edu'
export ROCKY_EXPECTED_MODEL='gemma4:latest'
printf 'Rocky deployment test API key: '
IFS= read -r -s ROCKY_API_KEY
printf '\n'
export ROCKY_API_KEY
python run-test/integration/deployment_smoke.py
unset ROCKY_API_KEY
```

That command is non-generating: it checks web health, aggregate service health,
authenticated model discovery, and the live model-discovery rate-limit headers.
The authenticated request is still audited and consumes one model-discovery
quota unit. Use a dedicated instructor or deployment-test key rather than a
student's key. After those checks pass, submit one short, audited generation
request and verify its rate-limit headers with:

```sh
python run-test/integration/deployment_smoke.py --include-generation
```

After enabling each optional capability, verify it through the same public
route and advertised model metadata:

```sh
python run-test/integration/deployment_smoke.py --include-streaming
python run-test/integration/deployment_smoke.py --include-image
```

The streaming check validates the SSE media type, contiguous sequence numbers,
lifecycle order, delta/final-text consistency, terminal completion, request ID,
and rate-limit headers. The image check sends one embedded 1-by-1 PNG through
the documented public content-block shape and validates the buffered response.
If the selected model does not advertise the requested capability, the command
fails clearly without submitting that generation request.

All three inference checks are independent and opt-in. They may be combined in
one invocation after a full rollout:

```sh
python run-test/integration/deployment_smoke.py \
  --include-generation \
  --include-streaming \
  --include-image
```

For the normal final verification, the equivalent capability-aware shortcut is:

```sh
python run-test/integration/deployment_smoke.py \
  --timeout 390 \
  --include-advertised
```

It always checks buffered generation and automatically checks streaming and
image input when the selected model advertises them. Explicit feature flags
remain useful when a feature is required but unexpectedly absent: they fail
instead of silently omitting that path.

After the timeout ladder and longer queue wait are deployed, run the explicit
classroom-burst check once with a fresh deployment-test key:

```sh
export ROCKY_LIVE_DB_NAME='rocky_db'
printf 'Production MongoDB URI: '
IFS= read -r -s ROCKY_LIVE_MONGODB_URI
printf '\n'
export ROCKY_LIVE_MONGODB_URI ROCKY_LIVE_DB_NAME
python run-test/integration/deployment_smoke.py \
  --timeout 390 \
  --include-queue-burst
```

This starts six small buffered requests together, requires all six to complete
without `model_busy`, validates every request ID and rate-limit header set, and
correlates the IDs with permanent telemetry. It passes only when at least five
requests were actually queued, proving the installed one-active-request policy
rather than merely proving six requests completed. It does not assume client
numbering is server arrival order. Queue status and wait time are also visible
in each Analytics request detail for optional inspection. The deployment-test
key must have at least six Responses requests left in its current rate-limit
window.

When both optional capabilities are advertised, either combined form submits
three short, permanently audited generation requests in addition to model
discovery. Queue-burst mode submits six more. Use these modes once per
deployment rather than as frequent polls.

Unset the key when finished:

```sh
unset ROCKY_API_KEY ROCKY_LIVE_API_KEY ROCKY_LIVE_MONGODB_URI ROCKY_LIVE_DB_NAME
```

### Rate-limit rollout verification

A successful default smoke run includes `PASS  model rate limit`; each optional
inference run includes its own rate-limit result. These checks verify that all
three request-limit headers are present, the limit and remaining count are
internally consistent, and the reset is within Rocky's fixed one-minute window.

The deployment smoke test deliberately does not exhaust a key or create an
intentional `429`. After rollout, use the admin Analytics view to confirm that
`Limiter unavailable` remains zero and to review any `Rate-limit rejections` in
their course and user context. A rejection can be expected when a client really
exceeds its quota; any limiter-unavailable event indicates a database or
rate-limit storage problem that should be investigated. Avoid repeatedly or
concurrently running the smoke command because each authenticated API call is
audited and consumes quota.

## Request retention

Request telemetry is permanent unless Kent State establishes a different
policy. Document that default in `/etc/rocky/backend.env` with:

```sh
ROCKY_REQUEST_RETENTION_DAYS=0
```

The setting is documentation only; Rocky never schedules automatic deletion.
Administrators can inspect an explicit cutoff with the dry-run command:

```sh
python manage.py purge-requests \
  --env-file /etc/rocky/backend.env \
  --before 2025-08-01
```

The command reports the matching count and oldest/newest timestamps without
changing data. After taking and verifying a database backup, deletion requires
the additional `--apply` flag. Future cutoff dates and missing cutoffs are
rejected. An applied purge records its cutoff and deleted count in
`api_history` as a `telemetry-purge` audit event.

## MongoDB backup and recovery

Rocky does not implement its own backup service. Use the standard MongoDB
Database Tools on Rocky, keep backup files outside the release directory, and
follow Kent State's storage and retention requirements. The examples below use
`/var/backups/rocky`; an administrator must create that directory and grant the
Rocky service account access before the first backup.

Install a MongoDB Database Tools version compatible with the MongoDB server.
Confirm that the commands are available before relying on this procedure:

```sh
mongodump --version
mongorestore --version
```

Store the MongoDB URI in a Database Tools configuration file so credentials do
not appear in process arguments. The account that runs backups should own the
file, and no other account should be able to read it:

```sh
MONGODB_TOOLS_CONFIG=/etc/rocky/mongodb-tools.yml
sudo touch "$MONGODB_TOOLS_CONFIG"
sudo chown {{ROCKY_USER}}:{{ROCKY_GROUP}} "$MONGODB_TOOLS_CONFIG"
sudo chmod 600 "$MONGODB_TOOLS_CONFIG"
sudoedit "$MONGODB_TOOLS_CONFIG"
```

The file contains one YAML field. Substitute the production URI while editing;
do not commit the file or paste its value into a shell command:

```yaml
uri: mongodb://username:password@mongodb-host:27017/?authSource=admin
```

If backups run as a different account, use that account as the owner instead.
MongoDB Database Tools 100.3.0 or newer support the `--config` option used below.

### Create and verify an archive

Take a backup at least nightly while classes are active, and immediately before
a deployment, migration, retention purge, or other planned database change.
Run the following from the release checkout on Rocky:

```sh
cd {{ROCKY_APP_DIR}}
source .venv/bin/activate
set -a
. /etc/rocky/backend.env
set +a

BACKUP_DIR=/var/backups/rocky
BACKUP_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_PATH="$BACKUP_DIR/rocky-$BACKUP_STAMP.archive.gz"
MONGODB_TOOLS_CONFIG=/etc/rocky/mongodb-tools.yml

umask 077
python manage.py database-counts \
  --env-file /etc/rocky/backend.env \
  > "$BACKUP_PATH.counts.txt"
mongodump \
  --config="$MONGODB_TOOLS_CONFIG" \
  --db="$ROCKY_DB_NAME" \
  --archive="$BACKUP_PATH" \
  --gzip
sha256sum "$BACKUP_PATH" > "$BACKUP_PATH.sha256"
chmod 600 "$BACKUP_PATH" "$BACKUP_PATH.counts.txt" "$BACKUP_PATH.sha256"
```

Do not store database archives in Git, under `current`, or in a web-accessible
directory. The archive contains users, API-key hashes, prompts, responses, and
audit records. Give it the same access restrictions as the production database.
Copy it to Kent State-managed backup storage rather than relying on the Rocky
server as the only copy.

Verify the file checksum and ask `mongorestore` to inspect the archive without
writing data:

```sh
sha256sum --check "$BACKUP_PATH.sha256"
mongorestore \
  --config="$MONGODB_TOOLS_CONFIG" \
  --archive="$BACKUP_PATH" \
  --gzip \
  --dryRun \
  --nsInclude="$ROCKY_DB_NAME.*"
```

A checksum and dry run detect common file and command problems, but the most
useful recovery test is a temporary restore.

### Test a restore in a temporary database

Choose a new, empty database name. The example deliberately maps every Rocky
collection into `rocky_restore_check`; do not use the production database name.

```sh
RESTORE_CHECK_DB=rocky_restore_check

mongorestore \
  --config="$MONGODB_TOOLS_CONFIG" \
  --archive="$BACKUP_PATH" \
  --gzip \
  --stopOnError \
  --nsFrom="$ROCKY_DB_NAME.*" \
  --nsTo="$RESTORE_CHECK_DB.*"

python manage.py database-counts \
  --env-file /etc/rocky/backend.env \
  --database "$RESTORE_CHECK_DB" \
  > "$BACKUP_PATH.restore-counts.txt"

diff -u "$BACKUP_PATH.counts.txt" "$BACKUP_PATH.restore-counts.txt"
```

The first two header lines identify different database names, so `diff` should
show that expected difference. Every collection count should otherwise match.
Also inspect a small sample of users, courses, API keys, telemetry, and audit
events in the temporary database before declaring the backup usable.

After verification, an administrator may delete only the explicitly named
temporary database:

```sh
python - <<'PY'
import os

from pymongo import MongoClient

database_name = "rocky_restore_check"
if database_name != "rocky_restore_check":
    raise RuntimeError("unexpected database")
MongoClient(os.environ["ROCKY_MONGODB_URI"]).drop_database(database_name)
PY
```

If a different temporary name was used, update both occurrences in the safety
check before running it. Never run `dropDatabase()` against the production
database.

### Restore production

A production restore replaces data and requires a maintenance window. First:

1. Confirm the exact archive path, checksum, source database, and intended
   production database.
2. Complete the temporary-restore procedure above.
3. Take a new emergency backup of the current production database, even when it
   is damaged or incomplete.
4. Notify users that Rocky will be unavailable during the restore.
5. Stop services that read or write MongoDB:

```sh
sudo systemctl stop \
  rocky-frontend.service \
  rocky-chat-api.service \
  rocky-backend.service \
  rocky-hardware-sampler.service
```

Run one final dry run, then restore the archive. `--drop` replaces collections
present in the archive; it is intentionally destructive and belongs only in
this reviewed recovery procedure.

```sh
mongorestore \
  --config="$MONGODB_TOOLS_CONFIG" \
  --archive="$BACKUP_PATH" \
  --gzip \
  --dryRun \
  --nsInclude="$ROCKY_DB_NAME.*"

mongorestore \
  --config="$MONGODB_TOOLS_CONFIG" \
  --archive="$BACKUP_PATH" \
  --gzip \
  --drop \
  --stopOnError \
  --nsInclude="$ROCKY_DB_NAME.*"
```

Restart the services and compare the restored collection counts with the saved
baseline:

```sh
sudo systemctl start \
  rocky-backend.service \
  rocky-chat-api.service \
  rocky-frontend.service \
  rocky-hardware-sampler.service

python manage.py database-counts \
  --env-file /etc/rocky/backend.env
python manage.py doctor \
  --deployment-files \
  --deployment-host rocky \
  --env-file /etc/rocky/backend.env \
  --env-file /etc/rocky/frontend.env
python run-test/integration/deployment_smoke.py
```

Finally verify sign-in, course membership, API-key authentication, analytics,
request detail, and audit logs. Run the optional smoke-test generation only
after the non-generating checks pass.
