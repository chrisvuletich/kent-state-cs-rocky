import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, jsonify


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env", override=False)
load_dotenv(REPOSITORY_ROOT / ".env.local", override=True)
load_dotenv(SERVICE_ROOT / ".env", override=False)
load_dotenv(SERVICE_ROOT / ".env.local", override=True)

from app.ollama_client import OllamaCallError, call_ollama_chat
from app.hardware_metrics import collect_hardware_snapshot
from app.runtime_state import begin_inference, end_inference
from app.request_parser import extract_model, extract_messages, extract_reasoning, extract_generation_options


app = Flask(__name__)
GRANITE_HOST = os.getenv("ROCKY_GRANITE_HOST", "127.0.0.1")
GRANITE_PORT = int(os.getenv("ROCKY_GRANITE_PORT", "5002"))
APP_ENV = os.getenv("ROCKY_APP_ENV", "development").strip().lower()
HARDWARE_METRICS_TOKEN = os.getenv("ROCKY_HARDWARE_METRICS_TOKEN", "").strip()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "granite-llm-server"}), 200


@app.route("/hardware", methods=["GET"])
def hardware():
    provided_token = request.headers.get("X-Rocky-Metrics-Token", "")
    if HARDWARE_METRICS_TOKEN:
        if not secrets.compare_digest(provided_token, HARDWARE_METRICS_TOKEN):
            return jsonify({"error": "Hardware metrics authentication failed."}), 401
    elif APP_ENV == "production":
        return jsonify({"error": "Hardware metrics are not configured."}), 503
    elif request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify({"error": "Hardware metrics are available locally only."}), 403
    return jsonify(collect_hardware_snapshot()), 200


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
        reasoning = extract_reasoning(payload)
    except ValueError as error:
        return jsonify({
            "error": {
                "type": "bad_request",
                "message": str(error)
            }
        }), 400

    think = reasoning["effort"] if reasoning is not None else None

    begin_inference()
    try:
        ollama_result = call_ollama_chat(model, messages, options, think)
    except OllamaCallError as error:
        is_timeout = error.kind == "timeout"
        return jsonify({
            "error": {
                "type": "model_timeout" if is_timeout else "model_error",
                "message": (
                    "Model request timed out."
                    if is_timeout
                    else "Model service request failed."
                ),
            },
            "telemetry": error.telemetry,
        }), 504 if is_timeout else 502
    except Exception:
        app.logger.error("Unexpected Ollama client failure.")
        return jsonify({
            "error": {
                "type": "model_error",
                "message": "Model service request failed.",
            }
        }), 502
    finally:
        end_inference()
    
    if reasoning is not None and not ollama_result["thinking_present"]:
        return jsonify({
            "error": {
                "type": "model_error",
                "message": (
                    "Reasoning was requested, but the model "
                    "returned no reasoning output."
                )
            },
            "telemetry": ollama_result["telemetry"],
        }), 502
    
    metadata = {
        "source": "ollama",
        "reasoning_requested": reasoning is not None,
        "reasoning_applied": (
            reasoning is not None
            and ollama_result["thinking_present"]
        )
    }

    if reasoning is not None:
        metadata["reasoning_effort"] = reasoning["effort"]
        metadata["reasoning_summary_requested"] = reasoning["summary"]

    
    return jsonify({
        "model": model,
        "output_text": ollama_result["content"],
        "metadata": metadata,
        "telemetry": ollama_result["telemetry"],
    }), 200

    
    


if __name__ == "__main__":
    app.run(
        host=GRANITE_HOST,
        port=GRANITE_PORT,
        debug=APP_ENV == "development",
        use_reloader=False,
    )
