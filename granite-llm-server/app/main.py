import os
import secrets
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env", override=False)
load_dotenv(REPOSITORY_ROOT / ".env.local", override=True)
load_dotenv(SERVICE_ROOT / ".env", override=False)
load_dotenv(SERVICE_ROOT / ".env.local", override=True)

from app.ollama_client import (
    OllamaCallError,
    call_ollama_chat,
    call_ollama_chat_stream,
    check_ollama_readiness,
)
from app.config import (
    app_env,
    env_bool,
    env_float,
    env_int,
    env_text,
    require_production_secret,
)
from app.hardware_metrics import collect_hardware_snapshot
from app.runtime_state import begin_inference, end_inference
from app.request_parser import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_TOTAL_BYTES,
    MAX_IMAGE_TOTAL_PIXELS,
    MAX_IMAGES_PER_REQUEST,
    extract_generation_options,
    extract_messages,
    extract_model,
    extract_reasoning,
    extract_stream,
)
from app.stream_contract import (
    STREAM_CONTENT_TYPE,
    encode_stream_event,
)


app = Flask(__name__)
GRANITE_HOST = env_text("ROCKY_GRANITE_HOST", "127.0.0.1") or "127.0.0.1"
GRANITE_PORT = env_int("ROCKY_GRANITE_PORT", 5002, minimum=1, maximum=65535)
APP_ENV = app_env()
ENABLE_STREAMING = env_bool("ROCKY_ENABLE_STREAMING", False)
ENABLE_IMAGE_INPUT = env_bool("ROCKY_ENABLE_IMAGE_INPUT", False)
HARDWARE_METRICS_TOKEN = env_text("ROCKY_HARDWARE_METRICS_TOKEN")
GRANITE_AUTH_TOKEN = env_text("ROCKY_GRANITE_TOKEN")
MAX_CONCURRENT_INFERENCES = env_int(
    "ROCKY_GRANITE_MAX_CONCURRENT", 1, minimum=1
)
MAX_REQUEST_BYTES = env_int(
    "ROCKY_GRANITE_MAX_REQUEST_BYTES", 10 * 1024 * 1024, minimum=1
)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
MINIMUM_IMAGE_REQUEST_BYTES = (
    4 * ((MAX_IMAGE_TOTAL_BYTES + 2) // 3)
    + 128 * 1024
)
if ENABLE_IMAGE_INPUT and MAX_REQUEST_BYTES < MINIMUM_IMAGE_REQUEST_BYTES:
    raise RuntimeError(
        "ROCKY_GRANITE_MAX_REQUEST_BYTES is too small for the configured "
        "image-input budget; set it to at least "
        f"{MINIMUM_IMAGE_REQUEST_BYTES}."
    )
QUEUE_WAIT_SECONDS = env_float(
    "ROCKY_GRANITE_QUEUE_WAIT_SECONDS", 1, minimum=0
)
INFERENCE_GATE = threading.BoundedSemaphore(MAX_CONCURRENT_INFERENCES)

if APP_ENV == "production":
    require_production_secret("ROCKY_GRANITE_TOKEN", GRANITE_AUTH_TOKEN)


def granite_request_is_authorized():
    if GRANITE_AUTH_TOKEN:
        provided_token = request.headers.get("X-Rocky-Granite-Token", "")
        return bool(provided_token) and secrets.compare_digest(
            provided_token,
            GRANITE_AUTH_TOKEN,
        )
    return APP_ENV != "production"


def granite_authentication_error():
    if GRANITE_AUTH_TOKEN:
        return jsonify({
            "error": {
                "type": "authentication_error",
                "message": "Granite authentication failed.",
            }
        }), 401
    return jsonify({
        "error": {
            "type": "service_unavailable",
            "message": "Granite authentication is not configured.",
        }
    }), 503


def generation_metadata(reasoning, thinking_present):
    metadata = {
        "source": "ollama",
        "reasoning_requested": reasoning is not None,
        "reasoning_applied": reasoning is not None and thinking_present,
    }
    if reasoning is not None:
        metadata["reasoning_effort"] = reasoning["effort"]
        metadata["reasoning_summary_requested"] = reasoning["summary"]
    return metadata


def model_error_details(kind):
    is_timeout = kind == "timeout"
    return {
        "type": "model_timeout" if is_timeout else "model_error",
        "message": (
            "Model request timed out."
            if is_timeout
            else "Model service request failed."
        ),
    }


class GraniteStreamBody:
    """Own one upstream stream and its inference-capacity reservation."""

    def __init__(self, model, upstream, reasoning, gate):
        self.model = model
        self.upstream = upstream
        self.reasoning = reasoning
        self.gate = gate
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.upstream.close()
        finally:
            end_inference()
            self.gate.release()

    def __iter__(self):
        try:
            yield encode_stream_event({
                "type": "started",
                "model": self.model,
            })
            try:
                for text in self.upstream:
                    yield encode_stream_event({
                        "type": "delta",
                        "text": text,
                    })
            except OllamaCallError as error:
                yield encode_stream_event({
                    "type": "error",
                    "error": model_error_details(error.kind),
                })
                return
            except Exception:
                app.logger.error("Unexpected Ollama streaming client failure.")
                yield encode_stream_event({
                    "type": "error",
                    "error": model_error_details("model_error"),
                })
                return

            if self.reasoning is not None and not self.upstream.thinking_present:
                yield encode_stream_event({
                    "type": "error",
                    "error": {
                        "type": "model_error",
                        "message": (
                            "Reasoning was requested, but the model returned "
                            "no reasoning output."
                        ),
                    },
                })
                return

            yield encode_stream_event({
                "type": "completed",
                "telemetry": self.upstream.telemetry,
                "metadata": generation_metadata(
                    self.reasoning,
                    self.upstream.thinking_present,
                ),
            })
        finally:
            self.close()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "granite-llm-server"}), 200


@app.route("/ready", methods=["GET"])
def ready():
    if not granite_request_is_authorized():
        return granite_authentication_error()

    model = os.getenv("OLLAMA_MODEL", "gemma4:latest").strip() or "gemma4:latest"
    ready_now = check_ollama_readiness(
        model,
        require_vision=ENABLE_IMAGE_INPUT,
    )
    return jsonify({
        "ok": ready_now,
        "service": "granite-llm-server",
        "model": model,
        "capabilities": {
            "supports_streaming": ENABLE_STREAMING,
            "supports_image_input": ENABLE_IMAGE_INPUT,
            "image_limits": {
                "max_images": MAX_IMAGES_PER_REQUEST,
                "max_image_bytes": MAX_IMAGE_BYTES,
                "max_total_bytes": MAX_IMAGE_TOTAL_BYTES,
                "max_pixels": MAX_IMAGE_PIXELS,
                "max_total_pixels": MAX_IMAGE_TOTAL_PIXELS,
            },
        },
        "dependencies": {"ollama": ready_now, "model_available": ready_now},
    }), 200 if ready_now else 503


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
    if not granite_request_is_authorized():
        return granite_authentication_error()

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
        messages = extract_messages(payload, allow_images=ENABLE_IMAGE_INPUT)
        options = extract_generation_options(payload)
        reasoning = extract_reasoning(payload)
        stream = extract_stream(payload)
    except ValueError as error:
        return jsonify({
            "error": {
                "type": "bad_request",
                "message": str(error)
            }
        }), 400

    if stream and not ENABLE_STREAMING:
        return jsonify({
            "error": {
                "type": "bad_request",
                "message": "Streaming is not enabled.",
            }
        }), 400

    think = reasoning["effort"] if reasoning is not None else None

    acquired = INFERENCE_GATE.acquire(timeout=QUEUE_WAIT_SECONDS)
    if not acquired:
        return jsonify({
            "error": {
                "type": "model_busy",
                "message": "The model is busy. Try again shortly.",
            }
        }), 503, {"Retry-After": "2"}

    begin_inference()
    if stream:
        try:
            ollama_stream = call_ollama_chat_stream(
                model,
                messages,
                options,
                think,
            )
        except OllamaCallError as error:
            end_inference()
            INFERENCE_GATE.release()
            details = model_error_details(error.kind)
            return jsonify({
                "error": details,
                "telemetry": error.telemetry,
            }), 504 if error.kind == "timeout" else 502
        except Exception:
            end_inference()
            INFERENCE_GATE.release()
            app.logger.error("Unexpected Ollama streaming client failure.")
            return jsonify({
                "error": model_error_details("model_error"),
            }), 502

        stream_body = GraniteStreamBody(
            model,
            ollama_stream,
            reasoning,
            INFERENCE_GATE,
        )
        return Response(
            stream_body,
            status=200,
            content_type=STREAM_CONTENT_TYPE,
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        ollama_result = call_ollama_chat(model, messages, options, think)
    except OllamaCallError as error:
        details = model_error_details(error.kind)
        return jsonify({
            "error": details,
            "telemetry": error.telemetry,
        }), 504 if error.kind == "timeout" else 502
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
        INFERENCE_GATE.release()
    
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
    
    metadata = generation_metadata(reasoning, ollama_result["thinking_present"])

    return jsonify({
        "model": model,
        "output_text": ollama_result["content"],
        "metadata": metadata,
        "telemetry": ollama_result["telemetry"],
    }), 200


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({
        "error": {
            "type": "bad_request",
            "message": "Request body is too large.",
        }
    }), 413

    
    


if __name__ == "__main__":
    app.run(
        host=GRANITE_HOST,
        port=GRANITE_PORT,
        debug=APP_ENV == "development",
        use_reloader=False,
    )
