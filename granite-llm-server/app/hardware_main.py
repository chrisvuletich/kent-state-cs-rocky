from __future__ import annotations

import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env", override=False)
load_dotenv(REPOSITORY_ROOT / ".env.local", override=True)
load_dotenv(SERVICE_ROOT / ".env", override=False)
load_dotenv(SERVICE_ROOT / ".env.local", override=True)

from app.hardware_metrics import collect_hardware_snapshot
from app.config import app_env, env_int, env_text, require_production_secret


app = Flask(__name__)
APP_ENV = app_env()
METRICS_TOKEN = env_text("ROCKY_HARDWARE_METRICS_TOKEN")
HARDWARE_HOST = env_text("ROCKY_HARDWARE_HOST", "127.0.0.1")
HARDWARE_PORT = env_int("ROCKY_HARDWARE_PORT", 5010, minimum=1, maximum=65535)

if APP_ENV == "production":
    require_production_secret("ROCKY_HARDWARE_METRICS_TOKEN", METRICS_TOKEN)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "granite-hardware-metrics"}), 200


@app.route("/hardware", methods=["GET"])
def hardware():
    provided = request.headers.get("X-Rocky-Metrics-Token", "")
    if METRICS_TOKEN:
        if not secrets.compare_digest(provided, METRICS_TOKEN):
            return jsonify({"error": "Hardware metrics authentication failed."}), 401
    elif APP_ENV == "production":
        return jsonify({"error": "Hardware metrics are not configured."}), 503
    elif request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify({"error": "Hardware metrics are available locally only."}), 403
    return jsonify(collect_hardware_snapshot(include_runtime=False)), 200


if __name__ == "__main__":
    app.run(
        host=HARDWARE_HOST or "127.0.0.1",
        port=HARDWARE_PORT,
        debug=APP_ENV == "development",
        use_reloader=False,
    )
