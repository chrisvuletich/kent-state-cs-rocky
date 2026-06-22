from flask import Flask, request, jsonify

from ollama_client import call_ollama_chat
from request_parser import extract_model
from request_parser import extract_messages
from request_parser import extract_generation_options


app = Flask(__name__)
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
    app.run(host="127.0.0.1", port=5002, debug=True)


