import os
import sys
from pathlib import Path

import requests
from pymongo import MongoClient


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
if str(API_ROCKY_DIR) not in sys.path:
    sys.path.insert(0, str(API_ROCKY_DIR))

OPT_IN = "ROCKY_RUN_LIVE_TELEMETRY_SMOKE"
REQUIRED = (
    "ROCKY_LIVE_API_URL", "ROCKY_LIVE_API_KEY",
    "ROCKY_LIVE_MONGODB_URI", "ROCKY_LIVE_DB_NAME",
)
PROMPT = "Reply with only the word Rocky. Unicode check: café ☕"


class SmokeFailure(Exception):
    pass


def integer(document, field, default=None):
    value = document.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SmokeFailure("METRIC_INVALID")
    return value


def run_live_smoke():
    values = {name: os.getenv(name, "").strip() for name in REQUIRED}
    if any(not value for value in values.values()):
        raise SmokeFailure("CONFIG_MISSING")
    timeout = float(os.getenv("ROCKY_LIVE_TIMEOUT_SECONDS", "210"))
    if timeout <= 0:
        raise SmokeFailure("CONFIG_INVALID")

    from telemetry_projection import refresh_current

    client = MongoClient(values["ROCKY_LIVE_MONGODB_URI"],
                         serverSelectionTimeoutMS=5000, tz_aware=True)
    try:
        client.admin.command("ping")
        database = client[values["ROCKY_LIVE_DB_NAME"]]
        interactions = database["telemetry_interactions"]
        current = database["telemetry_current"]
        users = database["users"]
        before = refresh_current(interactions, current, users)

        endpoint = values["ROCKY_LIVE_API_URL"].rstrip("/")
        if not endpoint.endswith("/v1/responses"):
            endpoint += "/v1/responses"
        response = requests.post(endpoint, json={
            "model": os.getenv("ROCKY_PUBLIC_MODEL", "gemma4:latest").strip(),
            "input": PROMPT,
            "store": False,
        }, headers={
            "Authorization": f"Bearer {values['ROCKY_LIVE_API_KEY']}"
        }, timeout=timeout)
        if not response.ok:
            raise SmokeFailure("API_RESPONSE_FAILED")
        payload = response.json()
        if (not isinstance(payload, dict)
                or not isinstance(payload.get("output_text"), str)
                or not payload["output_text"].strip()):
            raise SmokeFailure("API_REPLY_EMPTY")

        interaction = interactions.find_one(
            {"_id": response.headers.get("X-Rocky-Request-Id", "")})
        if (not isinstance(interaction, dict)
                or interaction.get("state") != "terminal"
                or interaction.get("outcome") != "completed"):
            raise SmokeFailure("CORRELATED_INTERACTION_MISSING")
        if (interaction.get("schema_version") != 2
                or interaction.get("content_available") is not True
                or interaction.get("expires_at") is not None):
            raise SmokeFailure("PERMANENT_RECORD_MISSING")
        stored_request = interaction.get("request")
        stored_response = interaction.get("response")
        if (not isinstance(stored_request, dict)
                or stored_request.get("input_text") != PROMPT
                or not isinstance(stored_response, dict)
                or stored_response.get("output_text") != payload["output_text"]):
            raise SmokeFailure("REQUEST_CONTENT_MISSING")
        if values["ROCKY_LIVE_API_KEY"] in repr(interaction):
            raise SmokeFailure("PLAINTEXT_KEY_STORED")

        after = refresh_current(interactions, current, users)

        requirements = {
            "interactions_accepted_total": 1,
            "interactions_completed_total": 1,
            "request_latency_samples_total": 1,
        }
        for field in ("model_input_bytes", "model_output_bytes",
                      "request_latency_ms"):
            requirements[f"{field}_total"] = integer(interaction, field)
        deltas = {}
        for field, expected in requirements.items():
            change = integer(after, field) - integer(before, field)
            if change != expected:
                raise SmokeFailure("METRIC_DELTA_MISSING")
            deltas[field] = change

        for source, total in (("prompt_eval_count", "prompt_tokens_total"),
                              ("eval_count", "output_tokens_total")):
            if source not in interaction:
                continue
            change = integer(after, total) - integer(before, total, 0)
            if change != integer(interaction, source):
                raise SmokeFailure("TOKEN_DELTA_MISSING")
            deltas[total] = change
        return deltas
    finally:
        client.close()


def main():
    if os.getenv(OPT_IN, "").strip() != "1":
        print("SKIP_LIVE_TELEMETRY_SMOKE")
        return 0
    try:
        deltas = run_live_smoke()
    except SmokeFailure as error:
        print(f"FAIL_{error}", file=sys.stderr)
        return 1
    except Exception:
        print("FAIL_UNEXPECTED", file=sys.stderr)
        return 1
    for field in sorted(deltas):
        print(f"{field}_delta={deltas[field]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
