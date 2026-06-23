from __future__ import annotations

from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)


@app.route("/rocky-api", methods=["POST"])
def rocky_api():

    # parse incoming JSON into `apirequest` with keys: `apikey`, `requestbody`
    apirequest = parse_api_request()
    if not apirequest:
        return jsonify({"error": "Bad request: expected JSON payload"}), 400

    #verify and request AI
    if check_key(apirequest.get("apikey")):
        response = request_ai(apirequest.get("requestbody"))
        return jsonify(response), 200
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
    #impliment mongo interaction
    if key == "SOME_API_KEY":
        return True
    else:
        return False

def request_ai(request_body):
    """Send `request_body` to the AI endpoint at granite.cs.kent.edu and return the response body.

    - If `request_body` is a dict, it will be sent as JSON.
    - If it's a string, the function will try to parse it as JSON, otherwise send it as the value of an `input` field.
    - On network or HTTP errors, returns an error string.
    """
    try:
        if request_body is None:
            payload = {}
        elif isinstance(request_body, str):
            try:
                payload = json.loads(request_body)
            except Exception:
                payload = {"input": request_body}
        else:
            payload = request_body

        resp = requests.post("https://granite.cs.kent.edu", json=payload, timeout=15)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return {"result": resp.text}
    except requests.RequestException as exc:
        return {"error": f"Error contacting AI: {exc}"}


if __name__ == "__main__":
	# default local dev run
	app.run(host="127.0.0.1", port=5001, debug=True)
