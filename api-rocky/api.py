from __future__ import annotations

from flask import Flask, request

app = Flask(__name__)


@app.route("/rocky-api", methods=["POST"])
def rocky_api():

    # parse incoming JSON into `apirequest` with keys: `apikey`, `requestbody`
    apirequest = parse_api_request()
    if not apirequest:
        return "Bad request: expected JSON payload", 400, {"Content-Type": "text/plain; charset=utf-8"}

    #verify and request AI
    response = ""
    if check_key(apirequest.get("apikey")):
        response = request_ai(apirequest.get("requestbody"))
    else:
        response = "Invalid API key"

    return response, 200, {"Content-Type": "text/plain; charset=utf-8"}


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

def request_ai(request):
    #inlpiment AI req
    return "ai response returned!\n"


if __name__ == "__main__":
	# default local dev run
	app.run(host="127.0.0.1", port=5001, debug=True)
