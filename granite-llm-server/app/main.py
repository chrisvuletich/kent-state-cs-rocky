from flask import Flask, request, jsonify

from app.ollama_client import call_ollama_chat
from app.request_parser import extract_model
from app.request_parser import extract_messages
from app.request_parser import extract_generation_options
import os


app = Flask(__name__)
GRANITE_HOST = os.getenv("ROCKY_GRANITE_HOST", "127.0.0.1")
GRANITE_PORT = int(os.getenv("ROCKY_GRANITE_PORT", "5002"))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "granite-llm-server"}), 200


@app.route("/generate", methods=["POST"])

def generate():
    payload = request.get_json(silent=True)

    if payload is None:
        return jsonify({
            "error": {
                "type": "bad_request",
                "message": "Request body must be valid JSON."
            }
        }), 400
    
    try:
        model = extract_model(payload)
        messages = extract_messages(payload)
        options = extract_generation_options(payload)
    except ValueError as error:
        return jsonify({
            "error": {
                "type": "bad_request",
                "message": str(error)
            }
        }), 400

    try:
        output_text = call_ollama_chat(model, messages, options)
    except Exception as error:
        return jsonify({
            "error": {
                "type": "model_error",
                "message": str(error)
            }
        }), 502

    return jsonify({
        "model": model,
        "output_text": output_text,
        "metadata": {
            "source": "ollama"
        }
    }), 200
    


if __name__ == "__main__":
    app.run(host=GRANITE_HOST, port=GRANITE_PORT, debug=True)

