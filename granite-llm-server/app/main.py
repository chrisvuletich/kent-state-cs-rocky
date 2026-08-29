import os
import secrets
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env", override=False)
load_dotenv(REPOSITORY_ROOT / ".env.local", override=True)
load_dotenv(SERVICE_ROOT / ".env", override=False)
load_dotenv(SERVICE_ROOT / ".env.local", override=True)

from app.ollama_client import (
    OLLAMA_TIMEOUT_SECONDS,
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
from app.inference_queue import (
    ADMITTED,
    CANCELLED,
    QUEUE_FULL,
    QUEUE_MEMORY_FULL,
    TIMED_OUT,
    WAITING,
    InferenceQueue,
)
from app.runtime_state import begin_inference, end_inference
from app.request_parser import (
    DEFAULT_REASONING_EFFORT,
    MAX_CONTEXT_TOKENS,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_OUTPUT_TOKENS,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_TOTAL_BYTES,
    MAX_IMAGE_TOTAL_PIXELS,
    MAX_IMAGES_PER_REQUEST,
    MAX_OUTPUT_TOKENS,
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
    "ROCKY_GRANITE_QUEUE_WAIT_SECONDS", 120, minimum=0
)
QUEUE_CAPACITY = env_int(
    "ROCKY_GRANITE_QUEUE_CAPACITY", 12, minimum=0
)
QUEUE_MAX_BYTES = env_int(
    "ROCKY_GRANITE_QUEUE_MAX_BYTES", 64 * 1024 * 1024, minimum=0
)
QUEUE_HEARTBEAT_SECONDS = env_float(
    "ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS",
    10,
    minimum=0.1,
)
INFERENCE_QUEUE = InferenceQueue(
    max_active_requests=MAX_CONCURRENT_INFERENCES,
    max_waiting_requests=QUEUE_CAPACITY,
    max_queued_bytes=QUEUE_MAX_BYTES,
    wait_timeout_seconds=QUEUE_WAIT_SECONDS,
)

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
        "reasoning_applied": thinking_present,
        "reasoning_effort": (
            reasoning["effort"]
            if reasoning is not None
            else DEFAULT_REASONING_EFFORT
        ),
    }
    if reasoning is not None:
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


def model_busy_details():
    return {
        "type": "model_busy",
        "message": "The model is busy. Try again shortly.",
    }


def queue_telemetry(ticket):
    snapshot = ticket.snapshot()
    status = snapshot.status
    if status == ADMITTED:
        status = "not_queued" if snapshot.initial_position == 0 else "admitted"
    telemetry = {
        "status": status,
        "depth_on_arrival": snapshot.depth_on_arrival,
        "wait_ms": snapshot.wait_ms,
        "capacity": snapshot.capacity,
        "queued_bytes_on_arrival": snapshot.queued_bytes_on_arrival,
    }
    if snapshot.initial_position is not None:
        telemetry["initial_position"] = snapshot.initial_position
    return telemetry


def generation_telemetry(ticket, provider_telemetry=None):
    telemetry = (
        dict(provider_telemetry)
        if isinstance(provider_telemetry, dict)
        else {}
    )
    telemetry["queue"] = queue_telemetry(ticket)
    return telemetry


def queue_snapshot_telemetry():
    snapshot = INFERENCE_QUEUE.snapshot()
    return {
        "active_requests": snapshot.active_requests,
        "waiting_requests": snapshot.waiting_requests,
        "queued_bytes": snapshot.queued_bytes,
        "max_active_requests": snapshot.max_active_requests,
        "max_waiting_requests": snapshot.max_waiting_requests,
        "max_queued_bytes": snapshot.max_queued_bytes,
    }


def timeout_snapshot_telemetry():
    return {
        "ollama_request_seconds": OLLAMA_TIMEOUT_SECONDS,
        "queue_wait_seconds": QUEUE_WAIT_SECONDS,
        "heartbeat_seconds": QUEUE_HEARTBEAT_SECONDS,
    }


def queue_busy_response(status, ticket):
    reason = {
        QUEUE_FULL: "queue_full",
        QUEUE_MEMORY_FULL: "queue_memory_full",
        TIMED_OUT: "queue_timeout",
        CANCELLED: "queue_cancelled",
    }.get(status, "queue_unavailable")
    details = model_busy_details()
    details["queue_reason"] = reason
    return jsonify({
        "error": details,
        "telemetry": generation_telemetry(ticket),
    }), 503, {"Retry-After": "2"}


def begin_admitted_inference(ticket):
    try:
        begin_inference()
    except Exception:
        ticket.release()
        raise


def end_admitted_inference(ticket):
    try:
        end_inference()
    finally:
        ticket.release()


def iter_upstream_with_heartbeats(upstream, heartbeat_seconds):
    """Consume a blocking Ollama iterator while keeping Granite's stream alive."""
    pending = Queue(maxsize=1)
    stopped = Event()

    def publish(item):
        while not stopped.is_set():
            try:
                pending.put(item, timeout=min(heartbeat_seconds, 0.1))
                return True
            except Full:
                continue
        return False

    def consume_upstream():
        try:
            for text in upstream:
                if not publish(("delta", text)):
                    return
        except BaseException as error:
            publish(("error", error))
        else:
            publish(("completed", None))

    Thread(
        target=consume_upstream,
        name="granite-ollama-stream-reader",
        daemon=True,
    ).start()

    try:
        while True:
            try:
                item_type, value = pending.get(timeout=heartbeat_seconds)
            except Empty:
                yield None
                continue

            if item_type == "delta":
                yield value
                continue
            if item_type == "error":
                raise value
            return
    finally:
        stopped.set()


def iter_stream_events(model, upstream, reasoning, heartbeat_seconds, ticket):
    yield encode_stream_event({
        "type": "started",
        "model": model,
    })
    try:
        for text in iter_upstream_with_heartbeats(upstream, heartbeat_seconds):
            if text is None:
                yield "\n"
                continue
            yield encode_stream_event({
                "type": "delta",
                "text": text,
            })
    except OllamaCallError as error:
        yield encode_stream_event({
            "type": "error",
            "error": model_error_details(error.kind),
            "telemetry": generation_telemetry(ticket, error.telemetry),
        })
        return
    except Exception:
        app.logger.error("Unexpected Ollama streaming client failure.")
        yield encode_stream_event({
            "type": "error",
            "error": model_error_details("model_error"),
            "telemetry": generation_telemetry(ticket),
        })
        return

    if reasoning is not None and not upstream.thinking_present:
        yield encode_stream_event({
            "type": "error",
            "error": {
                "type": "model_error",
                "message": (
                    "Reasoning was requested, but the model returned "
                    "no reasoning output."
                ),
            },
            "telemetry": generation_telemetry(ticket, upstream.telemetry),
        })
        return

    yield encode_stream_event({
        "type": "completed",
        "telemetry": generation_telemetry(ticket, upstream.telemetry),
        "metadata": generation_metadata(
            reasoning,
            upstream.thinking_present,
        ),
    })


class GraniteStreamBody:
    """Own one upstream stream and its inference-capacity reservation."""

    def __init__(self, model, upstream, reasoning, ticket, heartbeat_seconds):
        self.model = model
        self.upstream = upstream
        self.reasoning = reasoning
        self.ticket = ticket
        self.heartbeat_seconds = heartbeat_seconds
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.upstream.close()
        finally:
            end_admitted_inference(self.ticket)

    def __iter__(self):
        try:
            yield from iter_stream_events(
                self.model,
                self.upstream,
                self.reasoning,
                self.heartbeat_seconds,
                self.ticket,
            )
        finally:
            self.close()


class QueuedGraniteStreamBody:
    """Keep a waiting stream alive and acquire Ollama only after admission."""

    def __init__(
        self,
        model,
        messages,
        options,
        think,
        reasoning,
        ticket,
        heartbeat_seconds,
    ):
        self.model = model
        self.messages = messages
        self.options = options
        self.think = think
        self.reasoning = reasoning
        self.ticket = ticket
        self.heartbeat_seconds = heartbeat_seconds
        self.upstream = None
        self.inference_started = False
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.upstream is not None:
                self.upstream.close()
        finally:
            if self.inference_started:
                end_admitted_inference(self.ticket)
            else:
                # Exactly one succeeds: cancel while waiting, or release if the
                # ticket was admitted between the last heartbeat and closure.
                self.ticket.cancel()
                self.ticket.release()

    def __iter__(self):
        try:
            if self.closed:
                return

            # Commit the private response immediately without adding a new
            # protocol event. Rocky ignores blank NDJSON framing lines.
            yield "\n"
            admission_status = self.ticket.wait(
                poll_seconds=self.heartbeat_seconds
            )
            while admission_status == WAITING:
                yield "\n"
                admission_status = self.ticket.wait(
                    poll_seconds=self.heartbeat_seconds
                )

            if admission_status == CANCELLED:
                yield encode_stream_event({
                    "type": "cancelled",
                    "telemetry": generation_telemetry(self.ticket),
                })
                return
            if admission_status != ADMITTED:
                yield encode_stream_event({
                    "type": "error",
                    "error": model_busy_details(),
                    "telemetry": generation_telemetry(self.ticket),
                })
                return

            try:
                begin_admitted_inference(self.ticket)
                self.inference_started = True
                self.upstream = call_ollama_chat_stream(
                    self.model,
                    self.messages,
                    self.options,
                    self.think,
                )
            except OllamaCallError as error:
                yield encode_stream_event({
                    "type": "error",
                    "error": model_error_details(error.kind),
                    "telemetry": generation_telemetry(
                        self.ticket,
                        error.telemetry,
                    ),
                })
                return
            except Exception:
                app.logger.error("Unexpected Ollama streaming client failure.")
                yield encode_stream_event({
                    "type": "error",
                    "error": model_error_details("model_error"),
                    "telemetry": generation_telemetry(self.ticket),
                })
                return

            yield from iter_stream_events(
                self.model,
                self.upstream,
                self.reasoning,
                self.heartbeat_seconds,
                self.ticket,
            )
        finally:
            self.close()


def granite_stream_response(stream_body):
    return Response(
        stream_body,
        status=200,
        content_type=STREAM_CONTENT_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
            "generation": {
                "default_reasoning_effort": DEFAULT_REASONING_EFFORT,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "max_image_output_tokens": MAX_IMAGE_OUTPUT_TOKENS,
                "max_context_tokens": MAX_CONTEXT_TOKENS,
            },
            "image_limits": {
                "max_images": MAX_IMAGES_PER_REQUEST,
                "max_image_bytes": MAX_IMAGE_BYTES,
                "max_total_bytes": MAX_IMAGE_TOTAL_BYTES,
                "max_pixels": MAX_IMAGE_PIXELS,
                "max_total_pixels": MAX_IMAGE_TOTAL_PIXELS,
            },
        },
        "queue": queue_snapshot_telemetry(),
        "timeouts": timeout_snapshot_telemetry(),
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

    raw_request_body = request.get_data(cache=True)
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
        has_images = any(message.get("images") for message in messages)
        output_token_limit = (
            MAX_IMAGE_OUTPUT_TOKENS if has_images else MAX_OUTPUT_TOKENS
        )
        options = extract_generation_options(
            payload,
            max_output_tokens=output_token_limit,
        )
        options.setdefault("num_predict", output_token_limit)
        options["num_ctx"] = MAX_CONTEXT_TOKENS
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

    think = (
        reasoning["effort"]
        if reasoning is not None
        else DEFAULT_REASONING_EFFORT
    )

    ticket = INFERENCE_QUEUE.request_slot(len(raw_request_body))
    admission_status = ticket.wait(poll_seconds=0) if stream else ticket.wait()
    if admission_status != ADMITTED:
        if stream and admission_status == WAITING:
            return granite_stream_response(QueuedGraniteStreamBody(
                model,
                messages,
                options,
                think,
                reasoning,
                ticket,
                QUEUE_HEARTBEAT_SECONDS,
            ))
        return queue_busy_response(admission_status, ticket)

    begin_admitted_inference(ticket)
    if stream:
        try:
            ollama_stream = call_ollama_chat_stream(
                model,
                messages,
                options,
                think,
            )
        except OllamaCallError as error:
            end_admitted_inference(ticket)
            details = model_error_details(error.kind)
            return jsonify({
                "error": details,
                "telemetry": generation_telemetry(ticket, error.telemetry),
            }), 504 if error.kind == "timeout" else 502
        except Exception:
            end_admitted_inference(ticket)
            app.logger.error("Unexpected Ollama streaming client failure.")
            return jsonify({
                "error": model_error_details("model_error"),
                "telemetry": generation_telemetry(ticket),
            }), 502

        stream_body = GraniteStreamBody(
            model,
            ollama_stream,
            reasoning,
            ticket,
            QUEUE_HEARTBEAT_SECONDS,
        )
        return granite_stream_response(stream_body)

    try:
        ollama_result = call_ollama_chat(model, messages, options, think)
    except OllamaCallError as error:
        details = model_error_details(error.kind)
        return jsonify({
            "error": details,
            "telemetry": generation_telemetry(ticket, error.telemetry),
        }), 504 if error.kind == "timeout" else 502
    except Exception:
        app.logger.error("Unexpected Ollama client failure.")
        return jsonify({
            "error": {
                "type": "model_error",
                "message": "Model service request failed.",
            },
            "telemetry": generation_telemetry(ticket),
        }), 502
    finally:
        end_admitted_inference(ticket)
    
    if reasoning is not None and not ollama_result["thinking_present"]:
        return jsonify({
            "error": {
                "type": "model_error",
                "message": (
                    "Reasoning was requested, but the model "
                    "returned no reasoning output."
                )
            },
            "telemetry": generation_telemetry(
                ticket,
                ollama_result["telemetry"],
            ),
        }), 502
    
    metadata = generation_metadata(reasoning, ollama_result["thinking_present"])

    return jsonify({
        "model": model,
        "output_text": ollama_result["content"],
        "metadata": metadata,
        "telemetry": generation_telemetry(ticket, ollama_result["telemetry"]),
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
