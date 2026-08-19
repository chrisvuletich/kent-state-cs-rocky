# Rocky release checklist

Use this checklist for a candidate that has already been reviewed and is ready
for the Rocky and Granite hosts. It keeps the normal path short while preserving
the checks needed for a safe streaming or image-input rollout.

## 1. Verify the candidate locally

From an activated project environment at the candidate revision:

```sh
python run-test/test_all.py
```

Do not use `--skip-browser` for the final candidate. Record the revision being
deployed and keep the successful test output with the release notes.

## 2. Check configuration before changing services

- Keep `ROCKY_ENABLE_STREAMING` and `ROCKY_ENABLE_IMAGE_INPUT` set to `false`
  while initially copying a new release.
- Keep the public model identifier aligned across Rocky, Granite, and the web
  frontend.
- Before enabling image input, configure the same image count, byte, and pixel
  limits in Rocky and Granite and use the documented larger request ceilings.
- Back up MongoDB before any release that includes a data migration.

Run the non-network configuration checks on the Rocky host:

```sh
python manage.py doctor \
  --skip-network \
  --env-file /etc/rocky/backend.env \
  --env-file /etc/rocky/frontend.env
```

## 3. Restart in dependency order

1. Restart Granite and wait for its authenticated `/ready` check to pass.
2. Restart the Rocky chat API and verify `/ready`.
3. Restart the backend and web frontend.
4. Run the full doctor without `--skip-network`.

For streaming, enable Granite first, then Rocky, then the frontend. For image
input, enable Granite first and Rocky second. Run the full doctor after the
flags are aligned; it fails when rollout state or image limits differ.

## 4. Verify the deployed public surface

Use a dedicated instructor or deployment-test key. The command tests buffered
generation plus every optional inference path advertised by the selected
model:

```sh
export ROCKY_BASE_URL=https://rocky.cs.kent.edu
export ROCKY_EXPECTED_MODEL=gemma4:latest
export ROCKY_API_KEY=...
python run-test/integration/deployment_smoke.py --include-advertised
unset ROCKY_API_KEY
```

Every inference request, including the embedded one-pixel image, is retained in
institutional audit telemetry. Run this once per deployment rather than as a
frequent health poll.

Finally, verify the built-in chat in a student account:

- Text appears incrementally when streaming is advertised.
- Stop leaves the conversation recoverable from durable history.
- A local JPEG, PNG, or WebP can be attached and remains visible after reopening
  the conversation.
- Buffered text chat remains usable when streaming is disabled.

## 5. Roll back safely

If the public verification fails, stop enabling features and retain the doctor
and smoke output for diagnosis. Disable streaming in the frontend first, then
Rocky, then Granite. Disable image input in Rocky first and Granite second.
After image rollback, restore Rocky's smaller request-body ceiling. Restart the
affected services and rerun the doctor plus the default non-generating smoke
test.

Record the deployed revision, whether each optional feature remained enabled,
and the smoke-test request IDs. Never copy the API key into release notes or
logs.
