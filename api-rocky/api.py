from __future__ import annotations

import os

from flask import Flask, request, jsonify
import requests
import logging
from mongita import MongitaClientDisk

# Try PyMongo first (default to localhost). If unavailable, fall back to Mongita.
try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except Exception:  # pragma: no cover - optional dependency
    MongoClient = None
    PyMongoError = Exception


app = Flask(__name__)

CHAT_API_KEY = os.getenv("ROCKY_CHAT_API_KEY", "SOME_API_KEY")
GRANITE_URL = os.getenv("ROCKY_GRANITE_URL", "http://127.0.0.1:5002/generate")
DEFAULT_MODEL = os.getenv("ROCKY_CHAT_MODEL", os.getenv("OLLAMA_MODEL", "gemma4:latest"))
CHAT_API_HOST = os.getenv("ROCKY_CHAT_API_HOST", "127.0.0.1")
CHAT_API_PORT = int(os.getenv("ROCKY_CHAT_API_PORT", "5003"))
GRANITE_TIMEOUT_SECONDS = int(os.getenv("ROCKY_GRANITE_TIMEOUT_SECONDS", "180"))


col = None

# Determine MongoDB URI (defaults to local MongoDB)
mongodb_uri = os.getenv("ROCKY_MONGODB_URI", "mongodb://127.0.0.1:27017").strip()

if MongoClient and mongodb_uri:
    try:
        mclient = MongoClient(mongodb_uri, serverSelectionTimeoutMS=2000)
        mclient.admin.command("ping")
        mdb = mclient["rocky_db"]
        col = mdb["apikeys"]
        logging.info("Using MongoDB at %s for apikeys", mongodb_uri)
    except PyMongoError as exc:
        logging.warning("Could not connect to MongoDB (%s), falling back to Mongita: %s", mongodb_uri, exc)

if col is None:
    # Fallback: use Mongita on disk
    client = MongitaClientDisk("mongitaDB")
    db = client["rocky_db"]
    col = db["apikeys"]




@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "api-rocky"}), 200


@app.route("/rocky-api", methods=["POST"])
def rocky_api():

    # parse incoming JSON into `apirequest` with keys: `apikey`, `requestbody`
    apirequest = parse_api_request()
    if not apirequest:
        return jsonify({"error": "Bad request: expected JSON payload"}), 400

    #verify and request AI
    if check_key(apirequest.get("apikey")):
        response = request_ai(apirequest.get("requestbody"))
        if response.get("error"):
            status = 400 if response.get("error_type") == "bad_request" else 502
            return jsonify({"error": response["error"]}), status
        return jsonify(
            {
                "reply": response.get("output_text", ""),
                "model": response.get("model"),
                "metadata": response.get("metadata", {}),
            }
        ), 200
    else:
        return jsonify({"error": "Invalid API key"}), 401


def parse_api_request():
    # Parse JSON payload from request into a dict with keys apikey & requestbody
    # Returns the dict or None if the payload is invalid.
    # Unsure if needed. More efficent to just use API key param, but then have to pass it to Rocky. Insecure?
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None

    key = payload.get("api-key")

    # build request body as everything except the api-key field
    requestbody = {k: v for k, v in payload.items() if k != "api-key"}

    return {"apikey": key, "requestbody": requestbody}


def check_key(key):
    api_key = col.find_one({"api-key": key})
    return api_key is not None



def _build_granite_payload(request_body):
    if request_body is None:
        return None

    if isinstance(request_body, str):
        message_text = request_body.strip()
        if not message_text:
            return None
        return {
            "model": DEFAULT_MODEL,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": message_text}],
                }
            ],
        }

    if not isinstance(request_body, dict):
        return None

    if isinstance(request_body.get("input"), list):
        return request_body

    message_text = str(request_body.get("message", "")).strip()
    if not message_text:
        return None

    payload = {
        "model": str(request_body.get("model") or DEFAULT_MODEL),
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": message_text}],
            }
        ],
    }

    if "temperature" in request_body:
        payload["temperature"] = request_body["temperature"]
    if "top_p" in request_body:
        payload["top_p"] = request_body["top_p"]
    if "max_output_tokens" in request_body:
        payload["max_output_tokens"] = request_body["max_output_tokens"]

    return payload


def request_ai(request_body):
    # Send a chat request to Granite and return the parsed response body.
    try:
        payload = _build_granite_payload(request_body)
        if payload is None:
            return {"error": "Missing message.", "error_type": "bad_request"}

        resp = requests.post(GRANITE_URL, json=payload, timeout=GRANITE_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        if not str(data.get("output_text", "")).strip():
            return {"error": "Granite returned no output.", "error_type": "bad_response"}
        return data
    except requests.RequestException as exc:
        return {"error": f"Error contacting AI: {exc}", "error_type": "network"}


if __name__ == "__main__":
	# default local dev run
	app.run(host=CHAT_API_HOST, port=CHAT_API_PORT, debug=True)
