from __future__ import annotations

import os
import hashlib
import hmac
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import time

from flask import Flask, g, request, jsonify, Response
import requests
import logging
from mongita import MongitaClientDisk
from dotenv import load_dotenv
from rate_limit import (
    FixedWindowRateLimiter,
    RATE_LIMIT_WINDOW_SECONDS,
    RateLimitDecision,
    RateLimitStoreUnavailable,
    ensure_rate_limit_ttl_index,
)
from telemetry import TelemetryStore, sanitize_model_metrics

# Try PyMongo first (default to localhost). If unavailable, fall back to Mongita.
try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except Exception:  # pragma: no cover - optional dependency
    MongoClient = None
    PyMongoError = Exception


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = Path(__file__).resolve().parent
load_dotenv(REPOSITORY_ROOT / ".env", override=False)
load_dotenv(REPOSITORY_ROOT / ".env.local", override=True)
load_dotenv(SERVICE_ROOT / ".env", override=False)
load_dotenv(SERVICE_ROOT / ".env.local", override=True)


VALID_APP_ENVS = {"development", "testing", "production", "test"}
VALID_DB_BACKENDS = {"mongita", "mongodb"}
PLACEHOLDER_PREFIXES = ("replace-with", "change-me", "changeme")


def _env_value(name, default=""):
    return os.getenv(name, str(default)).strip()


def _env_choice(name, default, choices):
    value = _env_value(name, default).lower() or default
    if value not in choices:
        expected = ", ".join(sorted(choices))
        raise RuntimeError(f"Invalid {name}: expected one of {expected}.")
    return value


def _env_bool(name, default):
    value = _env_value(name, "true" if default else "false").lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeError(f"Invalid {name}: expected exactly true or false.")


def _env_int(name, default, minimum=None, maximum=None):
    raw_value = _env_value(name, default)
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"Invalid {name}: expected an integer.") from error
    if minimum is not None and value < minimum:
        raise RuntimeError(f"Invalid {name}: must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"Invalid {name}: must be at most {maximum}.")
    return value


def _env_float(name, default, minimum=None, allow_minimum=True):
    raw_value = _env_value(name, default)
    try:
        value = float(raw_value)
    except ValueError as error:
        raise RuntimeError(f"Invalid {name}: expected a number.") from error
    if not math.isfinite(value):
        raise RuntimeError(f"Invalid {name}: expected a finite number.")
    if minimum is not None and (
        value < minimum or (value == minimum and not allow_minimum)
    ):
        comparison = "at least" if allow_minimum else "greater than"
        raise RuntimeError(f"Invalid {name}: must be {comparison} {minimum}.")
    return value


def _env_http_url(name, default):
    value = _env_value(name, default)
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        hostname = None
        parsed = None
    valid = bool(
        parsed
        and parsed.scheme in {"http", "https"}
        and parsed.netloc
        and hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise RuntimeError(
            f"Invalid {name}: expected an absolute http(s) URL without credentials, "
            "a query string, or a fragment."
        )
    return value


def _require_production_secret(name, value):
    is_placeholder = value.lower().startswith(PLACEHOLDER_PREFIXES)
    if len(value) < 32 or is_placeholder:
        raise RuntimeError(
            f"{name} must be a non-placeholder value of at least 32 characters in production."
        )


APP_ENV = _env_choice("ROCKY_APP_ENV", "development", VALID_APP_ENVS)
MAX_REQUEST_BYTES = _env_int(
    "ROCKY_MAX_REQUEST_BYTES", 256 * 1024, minimum=1
)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

CHAT_API_KEY_CONFIGURED = "ROCKY_CHAT_API_KEY" in os.environ and bool(os.getenv("ROCKY_CHAT_API_KEY", "").strip())
CHAT_API_KEY = os.getenv("ROCKY_CHAT_API_KEY", "").strip()
CHAT_SERVICE_OWNER_ID = os.getenv("ROCKY_CHAT_SERVICE_OWNER_ID", "rocky-chat-service@kent.edu").strip() or "rocky-chat-service@kent.edu"
CHAT_SERVICE_KEY_NAME = "rocky-chat-service"
GRANITE_URL = _env_http_url(
    "ROCKY_GRANITE_URL", "http://127.0.0.1:5002/generate"
)
INFERENCE_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma4:latest",
).strip() or "gemma4:latest"
PUBLIC_MODEL = os.getenv("ROCKY_PUBLIC_MODEL", INFERENCE_MODEL).strip() or INFERENCE_MODEL
CHAT_API_HOST = _env_value("ROCKY_CHAT_API_HOST", "127.0.0.1") or "127.0.0.1"
CHAT_API_PORT = _env_int("ROCKY_CHAT_API_PORT", 5003, minimum=1, maximum=65535)
GRANITE_TIMEOUT_SECONDS = _env_float(
    "ROCKY_GRANITE_TIMEOUT_SECONDS", 170, minimum=0, allow_minimum=False
)
GRANITE_READY_URL = _env_http_url(
    "ROCKY_GRANITE_READY_URL",
    GRANITE_URL.rstrip("/").rsplit("/", 1)[0] + "/ready",
)
GRANITE_AUTH_TOKEN = os.getenv("ROCKY_GRANITE_TOKEN", "").strip()
INTERNAL_PROXY_SECRET = os.getenv("ROCKY_INTERNAL_PROXY_SECRET", "").strip()
MAX_OUTPUT_TOKENS = _env_int("ROCKY_MAX_OUTPUT_TOKENS", 2048, minimum=1)
MAX_CONTEXT_CHARS = _env_int("ROCKY_MAX_CONTEXT_CHARS", 60000, minimum=1)
RESPONSES_RATE_LIMIT_PER_MINUTE = _env_int(
    "ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE", 10, minimum=1
)
MODELS_RATE_LIMIT_PER_MINUTE = _env_int(
    "ROCKY_MODELS_RATE_LIMIT_PER_MINUTE", 120, minimum=1
)
READINESS_TIMEOUT_SECONDS = _env_float(
    "ROCKY_READINESS_TIMEOUT_SECONDS", 2, minimum=0, allow_minimum=False
)
REQUIRE_REQUEST_LOGGING = _env_bool(
    "ROCKY_REQUIRE_REQUEST_LOGGING",
    APP_ENV == "production",
)

if APP_ENV == "production":
    _require_production_secret("ROCKY_INTERNAL_PROXY_SECRET", INTERNAL_PROXY_SECRET)
    _require_production_secret("ROCKY_GRANITE_TOKEN", GRANITE_AUTH_TOKEN)
    if not REQUIRE_REQUEST_LOGGING:
        raise RuntimeError(
            "ROCKY_REQUIRE_REQUEST_LOGGING must be true in production."
        )

def resolve_mongita_path(value):
    configured_path = Path(str(value).strip() or ".rocky-data/mongita").expanduser()
    if not configured_path.is_absolute():
        configured_path = REPOSITORY_ROOT / configured_path
    return configured_path.resolve()


MONGITA_PATH = resolve_mongita_path(
    os.getenv("ROCKY_MONGITA_PATH", ".rocky-data/mongita")
)


api_keys_col = None
conversations_col = None
messages_col = None
responses_col = None
telemetry_interactions_col = None
telemetry_current_col = None
telemetry_store = None
rate_limit_windows_col = None
rate_limiter = None
MONGITA_KEY_READ_REFRESH_ENABLED = False

DEVELOPMENT_BYPASS_KEY_ID = "akid_local_development_bypass"


def normalize_api_key_value(key):
    return key.strip() if isinstance(key, str) else ""


def hash_api_key_value(key):
    normalized_key = normalize_api_key_value(key)
    if not normalized_key:
        return ""
    return hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()


def generate_public_key_id():
    return f"akid_{uuid4().hex}"


def ensure_chat_service_api_key():
    if api_keys_col is None or not CHAT_API_KEY_CONFIGURED:
        return

    key_hash = hash_api_key_value(CHAT_API_KEY)
    if not key_hash:
        return

    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = api_keys_col.find_one({"hash": key_hash})
        if existing is None:
            existing = api_keys_col.find_one(
                {
                    "owner_type": "service",
                    "owner_id": CHAT_SERVICE_OWNER_ID,
                    "key_scope": "service",
                    "key_name": CHAT_SERVICE_KEY_NAME,
                }
            )

        key_id = ""
        if isinstance(existing, dict) and isinstance(existing.get("key_id"), str):
            key_id = existing.get("key_id", "").strip()

        service_doc = {
            "key_id": key_id or generate_public_key_id(),
            "owner_type": "service",
            "owner_id": CHAT_SERVICE_OWNER_ID,
            "key_scope": "service",
            "key_name": CHAT_SERVICE_KEY_NAME,
            "slot_index": 0,
            "hash": key_hash,
            "is_active": True,
            "expire": None,
            "created": existing.get("created") if isinstance(existing, dict) and existing.get("created") else now,
            "updated_at": now,
        }

        if isinstance(existing, dict) and existing.get("_id") is not None:
            service_doc["_id"] = existing["_id"]
            api_keys_col.replace_one({"_id": existing["_id"]}, service_doc)
        else:
            api_keys_col.insert_one(service_doc)
    except Exception as exc:
        logging.warning(
            "Could not ensure chat service API key record. error_type=%s",
            type(exc).__name__,
        )


def create_index_safely(collection, keys, **kwargs):
    if collection is None:
        return
    try:
        collection.create_index(keys, **kwargs)
    except Exception as exc:
        logging.warning(
            "Could not create chat API index. error_type=%s",
            type(exc).__name__,
        )


def ensure_chat_indexes():
    create_index_safely(
        api_keys_col,
        [("hash", 1)],
        unique=True,
        partialFilterExpression={"hash": {"$exists": True, "$gt": ""}},
    )
    create_index_safely(
        conversations_col,
        [("conversation_id", 1), ("user_id", 1)],
        unique=True,
    )
    create_index_safely(
        conversations_col,
        [("user_id", 1), ("updated_at", -1)],
    )
    create_index_safely(
        messages_col,
        [("conversation_id", 1), ("user_id", 1), ("created_at", 1)],
    )
    create_index_safely(
        responses_col,
        [("response_id", 1), ("owner_scope", 1)],
        unique=True,
    )


# Database configuration
DEFAULT_DB_BACKEND = (
    "mongodb"
    if APP_ENV == "production"
    else "mongita"
)
DB_BACKEND = _env_choice(
    "ROCKY_DB_BACKEND", DEFAULT_DB_BACKEND, VALID_DB_BACKENDS
)
if APP_ENV == "production" and DB_BACKEND != "mongodb":
    raise RuntimeError("ROCKY_DB_BACKEND must be mongodb in production.")
MONGODB_URI = os.getenv(
    "ROCKY_MONGODB_URI",
    ""
).strip()
DB_NAME = os.getenv("ROCKY_DB_NAME", "rocky_db").strip() or "rocky_db"

MONGODB_CONNECT_ATTEMPTS = _env_int(
    "ROCKY_MONGODB_CONNECT_ATTEMPTS", 10, minimum=1
)
MONGODB_RETRY_SECONDS = _env_float(
    "ROCKY_MONGODB_RETRY_SECONDS", 2, minimum=0
)


def initialize_database():
    global api_keys_col
    global conversations_col
    global messages_col
    global responses_col
    global telemetry_interactions_col
    global telemetry_current_col
    global rate_limit_windows_col
    global MONGITA_KEY_READ_REFRESH_ENABLED

    MONGITA_KEY_READ_REFRESH_ENABLED = False

    if DB_BACKEND == "mongodb":
        if not MONGODB_URI:
            raise RuntimeError(
                "ROCKY_MONGODB_URI is required for the MongoDB backend."
            )
        if MongoClient is None:
            raise RuntimeError(
                "ROCKY_DB_BACKEND is set to mongodb, but PyMongo is unavailable."
            )

        for attempt in range(1, MONGODB_CONNECT_ATTEMPTS + 1):
            try:
                logging.info(
                    "Connecting to MongoDB database=%s "
                    "(attempt %s of %s)",
                    DB_NAME,
                    attempt,
                    MONGODB_CONNECT_ATTEMPTS,
                )

                mongo_client = MongoClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=2000,
                )
                mongo_client.admin.command("ping")

                database = mongo_client[DB_NAME]

                api_keys_col = database["api_keys"]
                conversations_col = database["conversations"]
                messages_col = database["messages"]
                responses_col = database["responses"]
                telemetry_interactions_col = database["telemetry_interactions"]
                telemetry_current_col = database["telemetry_current"]
                rate_limit_windows_col = database["rate_limit_windows"]

                logging.info(
                    "Using MongoDB database=%s",
                    DB_NAME,
                )
                return

            except PyMongoError as exc:
                logging.warning(
                    "MongoDB connection attempt %s of %s failed. error_type=%s",
                    attempt,
                    MONGODB_CONNECT_ATTEMPTS,
                    type(exc).__name__,
                )

                if attempt < MONGODB_CONNECT_ATTEMPTS:
                    time.sleep(MONGODB_RETRY_SECONDS)

        raise RuntimeError(
            "MongoDB was unavailable after "
            f"{MONGODB_CONNECT_ATTEMPTS} attempts. "
            "Refusing to fall back to Mongita while "
            "ROCKY_DB_BACKEND=mongodb."
        )

    if DB_BACKEND == "mongita":
        logging.warning(
            "Using Mongita database at %s. "
            "This backend should only be used for local development.",
            MONGITA_PATH,
        )

        MONGITA_PATH.mkdir(parents=True, exist_ok=True)
        client = MongitaClientDisk(str(MONGITA_PATH))
        database = client[DB_NAME]

        api_keys_col = database["api_keys"]
        conversations_col = database["conversations"]
        messages_col = database["messages"]
        responses_col = database["responses"]
        telemetry_interactions_col = database["telemetry_interactions"]
        telemetry_current_col = database["telemetry_current"]
        rate_limit_windows_col = database["rate_limit_windows"]
        MONGITA_KEY_READ_REFRESH_ENABLED = True
        return

    raise RuntimeError(
        f"Unsupported ROCKY_DB_BACKEND value: {DB_BACKEND!r}. "
        "Expected 'mongodb' or 'mongita'."
    )


telemetry_enabled = _env_bool("ROCKY_TELEMETRY_ENABLED", True)
if APP_ENV == "production" and not telemetry_enabled:
    raise RuntimeError("ROCKY_TELEMETRY_ENABLED must be true in production.")


def should_skip_database_initialization_for_tests():
    skip_requested = os.getenv("ROCKY_TEST_SKIP_DATABASE_INIT","false").strip().lower() == "true"

    if not skip_requested:
        return False

    app_environment = os.getenv("ROCKY_APP_ENV","").strip().lower()

    if app_environment != "test":
        raise RuntimeError("Database initialization can only be skipped when ROCKY_APP_ENV=test")

    return True


def initialize_rate_limiter():
    """Initialize the shared limiter after the configured database is ready."""
    global rate_limiter

    if rate_limit_windows_col is None:
        raise RuntimeError("Rate-limit storage is unavailable.")

    if DB_BACKEND == "mongodb":
        ensure_rate_limit_ttl_index(rate_limit_windows_col)

    rate_limiter = FixedWindowRateLimiter(
        rate_limit_windows_col,
        cleanup_expired=DB_BACKEND == "mongita",
        logger=app.logger,
    )


DATABASE_INITIALIZATION_SKIPPED_FOR_TESTS = (
    should_skip_database_initialization_for_tests()
)

if not DATABASE_INITIALIZATION_SKIPPED_FOR_TESTS:
    initialize_database()
    ensure_chat_indexes()
    ensure_chat_service_api_key()
    initialize_rate_limiter()

    if telemetry_enabled:
        telemetry_store = TelemetryStore(
            telemetry_interactions_col,
            telemetry_current_col,
            logger=app.logger,
        )
        telemetry_store.ensure_indexes()


def has_effective_user_prompt(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("input"), list):
        return False
    for item in payload["input"]:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, list) and any(
            isinstance(block, dict)
            and block.get("type") == "input_text"
            and isinstance(block.get("text"), str)
            and block["text"].strip()
            for block in content
        ):
            return True
    return False


SENSITIVE_FIELD_NAMES = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}


def is_sensitive_field_name(value):
    name = str(value).strip().lower().replace("-", "_")
    compact_name = name.replace("_", "")
    if name in {field.replace("-", "_") for field in SENSITIVE_FIELD_NAMES}:
        return True
    if name in {
        "access_token",
        "bearer_token",
        "client_secret",
        "current_password",
        "id_token",
        "new_password",
        "password_confirmation",
        "private_key",
        "proxy_authorization",
        "refresh_token",
        "set_cookie",
    }:
        return True
    if compact_name in {
        "accesstoken",
        "bearertoken",
        "clientsecret",
        "currentpassword",
        "idtoken",
        "newpassword",
        "passwordconfirmation",
        "privatekey",
        "proxyauthorization",
        "refreshtoken",
        "setcookie",
    }:
        return True
    return (
        name.endswith("_password")
        or name.startswith("password_")
        or name.endswith("_secret")
        or name.startswith("secret_")
        or name.endswith("_api_key")
        or name.endswith("_token")
        or compact_name.endswith("password")
        or compact_name.endswith("secret")
        or compact_name.endswith("apikey")
        or compact_name.endswith("token")
    )


def redact_structured_secrets(value):
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if is_sensitive_field_name(key)
                else redact_structured_secrets(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structured_secrets(item) for item in value]
    return value


def optional_text(value, limit=512):
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def telemetry_client_record():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    # nginx appends the connection address to any client-supplied chain.
    remote_address = forwarded_for.rsplit(",", 1)[-1].strip() or request.remote_addr
    return {
        "remote_address": optional_text(remote_address, 128),
        "user_agent": optional_text(request.headers.get("User-Agent"), 512),
        "content_type": optional_text(request.content_type, 128),
        "content_length": request.content_length,
    }


def telemetry_request_record(payload=None, raw_body=None):
    body = redact_structured_secrets(payload) if isinstance(payload, dict) else None
    malformed_body = None
    if body is None and isinstance(raw_body, str):
        encoded = raw_body.encode("utf-8")
        malformed_body = {
            "omitted": True,
            "byte_length": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
    record = {
        "body": body,
        "raw_body": None,
        "malformed_body": malformed_body,
        "model": optional_text(payload.get("model"), 256) if isinstance(payload, dict) else None,
        "store": payload.get("store") if isinstance(payload, dict) and isinstance(payload.get("store"), bool) else None,
        "conversation_id": optional_text(payload.get("conversation_id"), 256) if isinstance(payload, dict) else None,
        "previous_response_id": optional_text(payload.get("previous_response_id"), 256) if isinstance(payload, dict) else None,
        "instructions_text": payload.get("instructions") if isinstance(payload, dict) and isinstance(payload.get("instructions"), str) else None,
        "input_text": extract_user_message_text(payload) if isinstance(payload, dict) else None,
        "parameters": {
            field: redact_structured_secrets(payload[field])
            for field in (
                "frequency_penalty",
                "max_output_tokens",
                "metadata",
                "presence_penalty",
                "temperature",
                "top_p",
            )
            if isinstance(payload, dict) and field in payload
        },
    }
    return record


def telemetry_identity_record(key_doc):
    owner_type = optional_text(key_doc.get("owner_type"), 64) or "person"
    owner_type = owner_type.lower()
    owner_id = optional_text(
        key_doc.get("owner_id") or key_doc.get("user_id") or key_doc.get("email"),
        512,
    )
    actor = {
        "user_id": None,
        "email": None,
        "name": None,
        "attribution": "group-key-only" if owner_type == "group" else "personal-key-owner",
    }
    source = "public_api"
    if is_trusted_web_key_doc(key_doc) and has_valid_internal_proxy_secret():
        context = get_forwarded_user_context()
        actor.update({
            "user_id": context.get("user_id"),
            "email": context.get("user_email"),
            "name": context.get("user_name"),
            "attribution": "trusted-web-session" if context.get("user_id") else "service-key-only",
        })
        source = "web_chat"
    elif owner_type != "group":
        actor.update({
            "user_id": optional_text(
                key_doc.get("user_id") or key_doc.get("owner_id") or key_doc.get("email"),
                512,
            ),
            "email": optional_text(key_doc.get("email"), 512),
        })

    return {
        "source": source,
        "actor": actor,
        "credential": {
            "key_id": optional_text(key_doc.get("key_id"), 256),
            "owner_type": owner_type,
            "owner_id": owner_id,
            "key_name": optional_text(key_doc.get("key_name"), 128),
        },
        "course": {
            "course_id": key_doc.get("course_id") if isinstance(key_doc.get("course_id"), int) else None,
            "course_code": optional_text(key_doc.get("c_id"), 128),
            "group_id": owner_id if owner_type == "group" else None,
        },
    }


def telemetry_operation():
    if request.path == "/v1/models":
        return "models.list"
    if request.path == "/v1/responses":
        return "responses.create"
    return "unknown"


def begin_telemetry_interaction():
    request_id = f"req_{uuid4().hex}"
    started_monotonic_ns = time.monotonic_ns()
    fallback = {
        "request_id": request_id,
        "started_monotonic_ns": started_monotonic_ns,
        "current_counted": False,
        "persisted": False,
    }
    initial_record = {
        "operation": telemetry_operation(),
        "source": "unknown",
        "client": telemetry_client_record(),
        "content_available": True,
    }
    if telemetry_store is None:
        g.rocky_telemetry_interaction = fallback
        return fallback
    try:
        interaction = telemetry_store.record_received(
            request_id,
            record=initial_record,
            started_monotonic_ns=started_monotonic_ns,
        )
    except Exception as error:
        app.logger.warning(
            "telemetry.receive_unexpected_failure error_type=%s",
            type(error).__name__,
        )
        interaction = fallback
    g.rocky_telemetry_interaction = interaction
    return interaction


def enrich_telemetry_interaction(interaction, fields):
    if telemetry_store is None or not isinstance(interaction, dict):
        return False
    try:
        return telemetry_store.update_interaction(interaction, fields)
    except Exception as error:
        app.logger.warning(
            "telemetry.enrich_unexpected_failure error_type=%s",
            type(error).__name__,
        )
        return False


def finish_telemetry_interaction(
    interaction,
    outcome,
    model_metrics=None,
    *,
    response_payload=None,
    http_status=None,
    error_stage=None,
    error_type=None,
    additional_fields=None,
):
    if telemetry_store is None or not isinstance(interaction, dict):
        return False
    response_record = {
        "body": redact_structured_secrets(response_payload) if isinstance(response_payload, dict) else None,
        "output_text": response_payload.get("output_text") if isinstance(response_payload, dict) and isinstance(response_payload.get("output_text"), str) else None,
        "stop_reason": (model_metrics or {}).get("stop_reason"),
    }
    terminal_record = {
        "http_status": http_status,
        "error_stage": error_stage,
        "error_type": error_type,
        "response": response_record,
    }
    if isinstance(additional_fields, dict):
        terminal_record.update(additional_fields)
    try:
        return telemetry_store.record_terminal(
            interaction,
            outcome,
            model_metrics=model_metrics,
            terminal_record=terminal_record,
        )
    except Exception as error:
        app.logger.warning(
            "telemetry.terminal_unexpected_failure error_type=%s",
            type(error).__name__,
        )
        return False


def model_error_status(error_type):
    return {"bad_request": 400, "busy": 503, "timeout": 504}.get(error_type, 502)


def api_error(message, *, error_type="invalid_request_error", param=None, code=None):
    error = {
        "message": message,
        "type": error_type,
        "param": param,
        "code": code,
    }
    return {"error": error}


def model_capabilities():
    """Return the configured public model features advertised by Rocky."""
    return {
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_context_characters": MAX_CONTEXT_CHARS,
        "supports_streaming": False,
        "supports_previous_response_id": True,
        "supports_instructions": True,
        "model_dependent_parameters": ["frequency_penalty", "presence_penalty"],
    }


def telemetry_json(payload, status, interaction, headers=None):
    response = jsonify(payload)
    if isinstance(interaction, dict) and interaction.get("request_id"):
        request_id = interaction["request_id"]
        response.headers["x-request-id"] = request_id
        response.headers["X-Rocky-Request-Id"] = request_id
    if isinstance(headers, dict):
        for name, value in headers.items():
            response.headers[name] = str(value)
    return response, status


def terminal_telemetry_json(
    interaction,
    payload,
    status,
    outcome,
    *,
    model_metrics=None,
    error_stage=None,
    error_type=None,
    additional_fields=None,
    headers=None,
):
    persisted = finish_telemetry_interaction(
        interaction,
        outcome,
        model_metrics,
        response_payload=payload,
        http_status=status,
        error_stage=error_stage,
        error_type=error_type,
        additional_fields=additional_fields,
    )
    if REQUIRE_REQUEST_LOGGING and not persisted:
        return telemetry_json(
            api_error(
                "Request logging is unavailable.",
                error_type="server_error",
                code="request_logging_unavailable",
            ),
            503,
            interaction,
        )
    return telemetry_json(payload, status, interaction, headers=headers)


def rate_limit_key_doc(key_doc):
    """Return a credential with a stable public key ID, backfilling legacy rows."""
    if not isinstance(key_doc, dict):
        return None

    stored_key_id = key_doc.get("key_id")
    key_id = stored_key_id.strip() if isinstance(stored_key_id, str) else ""
    if key_id:
        return key_doc

    # Database-free route tests intentionally use synthetic key documents. This
    # seam cannot be enabled outside ROCKY_APP_ENV=test.
    if DATABASE_INITIALIZATION_SKIPPED_FOR_TESTS and rate_limiter is None:
        return key_doc

    document_id = key_doc.get("_id")
    collection = current_api_keys_collection()
    if document_id is None or collection is None:
        return None

    candidate_key_id = generate_public_key_id()
    legacy_key_id_query = (
        {"$in": [None, ""]}
        if stored_key_id is None or stored_key_id == ""
        else stored_key_id
    )
    try:
        collection.update_one(
            {
                "_id": document_id,
                "key_id": legacy_key_id_query,
            },
            {"$set": {"key_id": candidate_key_id}},
        )
        refreshed = collection.find_one({"_id": document_id})
    except Exception as error:
        app.logger.warning(
            "rate_limit.key_id_backfill_failed error_type=%s",
            type(error).__name__,
        )
        return None

    if not isinstance(refreshed, dict):
        return None
    return refreshed if optional_text(refreshed.get("key_id"), 256) else None


def rate_limit_response_headers(decision):
    """Return the request-limit headers supported by Rocky's RPM policy."""
    return {
        "x-ratelimit-limit-requests": str(decision.limit),
        "x-ratelimit-remaining-requests": str(decision.remaining_requests),
        "x-ratelimit-reset-requests": f"{decision.retry_after_seconds}s",
    }


@app.after_request
def attach_rate_limit_headers(response):
    decision = getattr(g, "rocky_rate_limit_decision", None)
    if isinstance(decision, RateLimitDecision):
        for name, value in rate_limit_response_headers(decision).items():
            response.headers[name] = value
    return response


def enforce_public_rate_limit(interaction, key_doc, *, operation, limit):
    """Consume one authenticated request and return an error response if blocked."""
    if rate_limiter is None and DATABASE_INITIALIZATION_SKIPPED_FOR_TESTS:
        return None

    try:
        decision: RateLimitDecision = rate_limiter.consume(
            key_id=key_doc.get("key_id"),
            operation=operation,
            limit=limit,
        )
    except (RateLimitStoreUnavailable, AttributeError, TypeError, ValueError) as error:
        app.logger.warning(
            "rate_limit.decision_failed request_id=%s operation=%s error_type=%s",
            interaction.get("request_id") if isinstance(interaction, dict) else None,
            operation,
            type(error).__name__,
        )
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Rate limiting is temporarily unavailable.",
                error_type="server_error",
                code="rate_limit_unavailable",
            ),
            503,
            "failed",
            error_stage="rate_limit",
            error_type="rate_limit_unavailable",
        )

    g.rocky_rate_limit_decision = decision
    if decision.allowed:
        return None

    retry_after = decision.retry_after_seconds
    rate_limit_record = {
        "rate_limit": {
            "scope": "api_key",
            "operation": operation,
            "limit": decision.limit,
            "remaining_requests": decision.remaining_requests,
            "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
            "retry_after_seconds": retry_after,
        }
    }
    return terminal_telemetry_json(
        interaction,
        api_error(
            "Rate limit reached for this API key. Please retry shortly.",
            error_type="rate_limit_error",
            code="rate_limit_exceeded",
        ),
        429,
        "rejected",
        error_stage="rate_limit",
        error_type="rate_limit_exceeded",
        additional_fields=rate_limit_record,
        headers={"Retry-After": str(retry_after)},
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "api-rocky"}), 200


@app.route("/ready", methods=["GET"])
def ready():
    dependencies = {"database": False, "granite": False}
    granite_model = None
    try:
        if api_keys_col is not None:
            api_keys_col.find_one({"_id": "__rocky_readiness__"})
            dependencies["database"] = True
    except Exception:
        app.logger.warning("readiness.database_unavailable")

    try:
        headers = {}
        if GRANITE_AUTH_TOKEN:
            headers["X-Rocky-Granite-Token"] = GRANITE_AUTH_TOKEN
        granite_response = requests.get(
            GRANITE_READY_URL,
            headers=headers,
            timeout=READINESS_TIMEOUT_SECONDS,
        )
        try:
            granite_payload = granite_response.json()
        except (TypeError, ValueError):
            granite_payload = {}
        if isinstance(granite_payload, dict):
            reported_model = granite_payload.get("model")
            if isinstance(reported_model, str) and reported_model.strip():
                granite_model = reported_model.strip()
        dependencies["granite"] = (
            granite_response.status_code == 200
            and granite_model == INFERENCE_MODEL
        )
    except requests.RequestException:
        pass

    ready_now = all(dependencies.values())
    return jsonify({
        "ok": ready_now,
        "service": "api-rocky",
        "dependencies": dependencies,
        "capabilities": model_capabilities(),
        "models": {
            "public": PUBLIC_MODEL,
            "inference": INFERENCE_MODEL,
            "granite": granite_model,
        },
    }), 200 if ready_now else 503


@app.route("/v1/models", methods=["GET"])
def list_models():
    interaction = begin_telemetry_interaction()
    key_doc = get_key_doc(extract_bearer_api_key())
    if not key_doc:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Invalid API key",
                error_type="authentication_error",
                code="invalid_api_key",
            ),
            401,
            "rejected",
            error_stage="authentication",
            error_type="invalid_api_key",
        )

    if is_service_key_doc(key_doc) and not is_trusted_web_request(key_doc):
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Internal proxy authentication failed.",
                error_type="authentication_error",
                code="invalid_proxy_authentication",
            ),
            401,
            "rejected",
            error_stage="authentication",
            error_type="invalid_proxy_authentication",
        )

    key_doc = rate_limit_key_doc(key_doc)
    if not key_doc:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Rate-limit identity is temporarily unavailable.",
                error_type="server_error",
                code="rate_limit_identity_unavailable",
            ),
            503,
            "failed",
            error_stage="rate_limit",
            error_type="rate_limit_identity_unavailable",
        )

    identity_logged = enrich_telemetry_interaction(
        interaction,
        telemetry_identity_record(key_doc),
    )
    if REQUIRE_REQUEST_LOGGING and not identity_logged:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Request logging is unavailable.",
                error_type="server_error",
                code="request_logging_unavailable",
            ),
            503,
            "failed",
            error_stage="telemetry",
            error_type="identity_persistence_failed",
        )

    rate_limit_response = enforce_public_rate_limit(
        interaction,
        key_doc,
        operation="models.list",
        limit=MODELS_RATE_LIMIT_PER_MINUTE,
    )
    if rate_limit_response is not None:
        return rate_limit_response

    return terminal_telemetry_json(
        interaction,
        {
            "object": "list",
            "data": [{
                "id": PUBLIC_MODEL,
                "object": "model",
                "created": 0,
                "owned_by": "kent-state",
                "metadata": model_capabilities(),
            }],
        },
        200,
        "completed",
    )


@app.errorhandler(413)
def request_too_large(_error):
    interaction = getattr(g, "rocky_telemetry_interaction", None)
    if not isinstance(interaction, dict):
        interaction = begin_telemetry_interaction()
    payload = api_error(
        "Request body is too large.",
        error_type="invalid_request_error",
        code="request_too_large",
    )
    return terminal_telemetry_json(
        interaction,
        payload,
        413,
        "rejected",
        error_stage="body",
        error_type="request_too_large",
    )


def telemetry_model_fields(request_body, model_metrics):
    metrics = sanitize_model_metrics(model_metrics)
    input_tokens = metrics.get("prompt_eval_count", 0)
    output_tokens = metrics.get("eval_count", 0)
    performance = {
        "model_total_duration_ns": metrics.get("total_duration"),
        "model_load_duration_ns": metrics.get("load_duration"),
        "prompt_eval_duration_ns": metrics.get("prompt_eval_duration"),
        "generation_duration_ns": metrics.get("eval_duration"),
    }
    return {
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_bytes": metrics.get("model_input_bytes"),
            "output_bytes": metrics.get("model_output_bytes"),
        },
        "performance": performance,
        "model": {
            "public_model": PUBLIC_MODEL,
            "actual_model": metrics.get("actual_model") or INFERENCE_MODEL,
        },
    }


@app.route("/v1/responses", methods=["POST"])
def rocky_api():
    interaction = begin_telemetry_interaction()
    if REQUIRE_REQUEST_LOGGING and not interaction.get("persisted"):
        return telemetry_json(
            api_error(
                "Request logging is unavailable.",
                error_type="server_error",
                code="request_logging_unavailable",
            ),
            503,
            interaction,
        )

    raw_body = request.get_data(cache=True, as_text=True)
    apirequest = parse_api_request()
    if not apirequest:
        malformed_logged = enrich_telemetry_interaction(
            interaction,
            {"request": telemetry_request_record(raw_body=raw_body)},
        )
        if REQUIRE_REQUEST_LOGGING and not malformed_logged:
            return terminal_telemetry_json(
                interaction,
                api_error(
                    "Request logging is unavailable.",
                    error_type="server_error",
                    code="request_logging_unavailable",
                ),
                503,
                "failed",
                error_stage="telemetry",
                error_type="request_persistence_failed",
            )
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Request body must be valid JSON object.",
                param=None,
                code="invalid_json",
            ),
            400,
            "rejected",
            error_stage="body",
            error_type="invalid_json",
        )

    request_body = apirequest.get("requestbody")
    request_record = telemetry_request_record(request_body, raw_body=raw_body)
    request_logged = enrich_telemetry_interaction(
        interaction, {"request": request_record}
    )
    if REQUIRE_REQUEST_LOGGING and not request_logged:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Request logging is unavailable.",
                error_type="server_error",
                code="request_logging_unavailable",
            ),
            503,
            "failed",
            error_stage="telemetry",
            error_type="request_persistence_failed",
        )

    key_doc = get_key_doc(apirequest.get("apikey"))
    if not key_doc:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Invalid API key",
                error_type="authentication_error",
                code="invalid_api_key",
            ),
            401,
            "rejected",
            error_stage="authentication",
            error_type="invalid_api_key",
        )

    if (
        is_trusted_web_key_doc(key_doc)
        and forwarded_identity_headers_present()
        and not has_valid_internal_proxy_secret()
    ):
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Internal proxy authentication failed.",
                error_type="authentication_error",
                code="invalid_proxy_authentication",
            ),
            401,
            "rejected",
            error_stage="authentication",
            error_type="invalid_proxy_authentication",
        )

    if is_service_key_doc(key_doc) and not is_trusted_web_request(key_doc):
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Internal proxy authentication failed.",
                error_type="authentication_error",
                code="invalid_proxy_authentication",
            ),
            401,
            "rejected",
            error_stage="authentication",
            error_type="invalid_proxy_authentication",
        )

    key_doc = rate_limit_key_doc(key_doc)
    if not key_doc:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Rate-limit identity is temporarily unavailable.",
                error_type="server_error",
                code="rate_limit_identity_unavailable",
            ),
            503,
            "failed",
            error_stage="rate_limit",
            error_type="rate_limit_identity_unavailable",
        )

    identity_logged = enrich_telemetry_interaction(
        interaction,
        telemetry_identity_record(key_doc),
    )
    if REQUIRE_REQUEST_LOGGING and not identity_logged:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "Request logging is unavailable.",
                error_type="server_error",
                code="request_logging_unavailable",
            ),
            503,
            "failed",
            error_stage="telemetry",
            error_type="identity_persistence_failed",
        )

    rate_limit_response = enforce_public_rate_limit(
        interaction,
        key_doc,
        operation="responses.create",
        limit=RESPONSES_RATE_LIMIT_PER_MINUTE,
    )
    if rate_limit_response is not None:
        return rate_limit_response

    validation_error = validate_public_request(request_body)
    if validation_error:
        return terminal_telemetry_json(
            interaction,
            api_error(
                validation_error["message"],
                param=validation_error.get("param"),
                code=validation_error.get("code"),
            ),
            400,
            "rejected",
            error_stage="validation",
            error_type="invalid_request",
        )

    trusted_web_request = is_trusted_web_request(key_doc)
    if request_body.get("conversation_id") and not trusted_web_request:
        return terminal_telemetry_json(
            interaction,
            api_error(
                "conversation_id is reserved for the built-in web chat. "
                "Use previous_response_id for API continuation.",
                param="conversation_id",
                code="unsupported_parameter",
            ),
            400,
            "rejected",
            error_stage="validation",
            error_type="invalid_request",
        )

    use_web_history = should_use_web_history(request_body, key_doc)
    store_response = should_store_response(request_body)
    chat_user_context = None
    user_id = None
    user_message = None
    requested_conversation_id = request_body.get("conversation_id")
    previous_response_id = request_body.get("previous_response_id")
    history_messages = []
    owner_scope = response_owner_scope(key_doc)

    if use_web_history:
        chat_user_context = get_chat_user_context(key_doc)
        if not chat_user_context:
            return terminal_telemetry_json(
                interaction,
                api_error(
                    "Missing trusted chat user context.",
                    error_type="authentication_error",
                    code="missing_chat_user_context",
                ),
                400,
                "rejected",
                error_stage="authentication",
                error_type="missing_chat_user_context",
            )

        user_id = chat_user_context["user_id"]
        user_message = extract_user_message_text(request_body)
    elif previous_response_id:
        history_messages = load_response_context(previous_response_id, owner_scope)
        if history_messages is None:
            return terminal_telemetry_json(
                interaction,
                api_error(
                    "Previous response not found.",
                    error_type="invalid_request_error",
                    param="previous_response_id",
                    code="response_not_found",
                ),
                404,
                "rejected",
                error_stage="conversation",
                error_type="response_not_found",
            )

    model_metrics = None
    conversation_id = None
    user_message_id = None
    response_payload = None
    try:
        if use_web_history:
            conversation_id = get_or_create_conversation(
                user_id=user_id,
                conversation_id=requested_conversation_id,
                first_message=user_message,
                user_context=chat_user_context
            )
            if conversation_id is None:
                return terminal_telemetry_json(
                    interaction,
                    api_error(
                        "Conversation not found.",
                        param="conversation_id",
                        code="conversation_not_found",
                    ),
                    404,
                    "rejected",
                    error_stage="conversation",
                    error_type="conversation_not_found",
                )

            recent_messages = load_recent_messages(conversation_id, user_id)
            history_messages = messages_to_granite_input(recent_messages)

        (
            model_request,
            current_messages,
            omitted_history_count,
            retained_history,
        ) = build_granite_payload_with_context(
            request_body,
            history_messages=history_messages,
        )
        if model_request is None or not has_effective_user_prompt(model_request):
            return terminal_telemetry_json(
                interaction,
                api_error(
                    "input must contain at least one user message.",
                    param="input",
                    code="missing_required_parameter",
                ),
                400,
                "rejected",
                error_stage="validation",
                error_type="missing_message",
            )

        request_record["model_input"] = redact_structured_secrets(model_request)
        request_record["history_truncated_messages"] = omitted_history_count
        model_input_logged = enrich_telemetry_interaction(interaction, {
            "request": request_record,
            "inference_dispatched_at": datetime.now(timezone.utc),
        })
        if REQUIRE_REQUEST_LOGGING and not model_input_logged:
            return terminal_telemetry_json(
                interaction,
                api_error(
                    "Request logging is unavailable.",
                    error_type="server_error",
                    code="request_logging_unavailable",
                ),
                503,
                "failed",
                error_stage="telemetry",
                error_type="model_input_persistence_failed",
            )

        if use_web_history:
            user_message_id = save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=user_message,
                user_context=chat_user_context,
                status="pending",
            )

        response = request_ai(model_request)
        model_metrics = response.get("_telemetry")
        if response.get("error"):
            if user_message_id:
                update_message_status(
                    conversation_id,
                    user_id,
                    user_message_id,
                    "failed",
                )
            outcome = (
                "timed_out"
                if response.get("error_type") == "timeout"
                else "failed"
            )
            model_error_type = response.get("error_type") or "model_error"
            status = model_error_status(model_error_type)
            code_by_type = {
                "bad_request": "invalid_model_request",
                "busy": "model_busy",
                "timeout": "model_timeout",
                "network": "model_service_unavailable",
                "bad_response": "invalid_model_response",
            }
            error_payload = api_error(
                response["error"],
                error_type=(
                    "invalid_request_error"
                    if model_error_type == "bad_request"
                    else "server_error"
                ),
                code=code_by_type.get(model_error_type, "model_error"),
            )
            if conversation_id is not None:
                error_payload["conversation_id"] = conversation_id
                error_payload["message_stored"] = bool(user_message_id)
            return terminal_telemetry_json(
                interaction,
                error_payload,
                status,
                outcome,
                model_metrics=model_metrics,
                error_stage=(
                    "ollama"
                    if model_error_type in {"timeout", "network", "bad_response"}
                    else "granite"
                ),
                error_type=model_error_type,
                additional_fields=telemetry_model_fields(
                    request_body,
                    model_metrics,
                ),
                headers={"Retry-After": "2"} if model_error_type == "busy" else None,
            )

        assistant_reply = response["output_text"]
        if use_web_history:
            update_message_status(
                conversation_id,
                user_id,
                user_message_id,
                "sent",
            )
            save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=assistant_reply,
                model=response.get("model"),
                user_context=chat_user_context
            )

        response_payload = build_response_payload(
            assistant_reply,
            request_body,
            response.get("metadata", {}),
            model_metrics,
        )
        if previous_response_id:
            response_payload["previous_response_id"] = previous_response_id
        if conversation_id is not None:
            response_payload["conversation_id"] = conversation_id

        if store_response and not use_web_history:
            assistant_context_message = {
                "role": "assistant",
                "content": [{"type": "output_text", "text": assistant_reply}],
            }
            save_response_context(
                response_payload["id"],
                owner_scope,
                [*retained_history, *current_messages, assistant_context_message],
            )
    except Exception as error:
        if user_message_id:
            try:
                update_message_status(
                    conversation_id,
                    user_id,
                    user_message_id,
                    "failed",
                )
            except Exception:
                app.logger.warning(
                    "chat.message_status_update_failed request_id=%s",
                    interaction.get("request_id"),
                )
        app.logger.error(
            "chat.request_failed request_id=%s error_type=%s",
            interaction.get("request_id"),
            type(error).__name__,
        )
        error_payload = api_error(
            "Internal server error.",
            error_type="server_error",
            code="internal_error",
        )
        if conversation_id is not None:
            error_payload["conversation_id"] = conversation_id
            error_payload["message_stored"] = bool(user_message_id)
        return terminal_telemetry_json(
            interaction,
            error_payload,
            500,
            "failed",
            model_metrics=model_metrics,
            error_stage="internal",
            error_type=type(error).__name__,
            additional_fields=telemetry_model_fields(
                request_body,
                model_metrics,
            ),
        )

    return terminal_telemetry_json(
        interaction,
        response_payload,
        200,
        "completed",
        model_metrics=model_metrics,
        additional_fields=telemetry_model_fields(
            request_body,
            model_metrics,
        ),
    )

@app.route("/conversations/<conversation_id>/export", methods=["POST"])
def export_conversation(conversation_id):
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Bad request: expected JSON payload"}), 400

    key_doc = get_key_doc(extract_bearer_api_key())

    if not key_doc:
        return jsonify({"error": "Invalid API key"}), 401

    chat_user_context = get_chat_user_context(key_doc)
    if not chat_user_context:
        return jsonify({"error": "Missing chat user context."}), 400

    user_id = chat_user_context["user_id"]

    conversation = conversations_col.find_one({
        "conversation_id": conversation_id,
        "user_id": user_id
    })

    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    messages = load_conversation_messages(
        conversation_id=conversation_id,
        user_id=user_id
    )

    export_format = str(payload.get("format", "json")).lower().strip()

    if export_format in {"markdown", "md"}:
        markdown_text = format_conversation_markdown(conversation, messages)

        return Response(
            markdown_text,
            mimetype="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="rocky-conversation-{conversation_id}.md"'
            }
        )

    if export_format == "json":
        clean_messages = [
            clean_message_for_export(message)
            for message in messages
        ]

        return jsonify({
            "conversation_id": conversation.get("conversation_id"),
            "title": conversation.get("title"),
            "user_id": conversation.get("user_id"),
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
            "message_count": len(clean_messages),
            "messages": clean_messages
        }), 200

    return jsonify({
        "error": "Unsupported export format. Use json or markdown."
    }), 400

@app.route("/conversations/<conversation_id>", methods=["POST"])
def get_conversation(conversation_id):
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Bad request: expected JSON payload"}), 400

    key_doc = get_key_doc(extract_bearer_api_key())

    if not key_doc:
        return jsonify({"error": "Invalid API key"}), 401

    chat_user_context = get_chat_user_context(key_doc)
    if not chat_user_context:
        return jsonify({"error": "Missing chat user context."}), 400

    user_id = chat_user_context["user_id"]

    conversation = conversations_col.find_one({
        "conversation_id": conversation_id,
        "user_id": user_id
    })

    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    messages = load_conversation_messages(
        conversation_id=conversation_id,
        user_id=user_id
    )

    return jsonify({
        "conversation": clean_conversation_for_list(conversation),
        "messages": [
            clean_message_for_export(message)
            for message in messages
        ]
    }), 200

@app.route("/conversations/list", methods=["POST"])
def list_conversations():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Bad request: expected JSON payload"}), 400

    key_doc = get_key_doc(extract_bearer_api_key())

    if not key_doc:
        return jsonify({"error": "Invalid API key"}), 401

    chat_user_context = get_chat_user_context(key_doc)
    if not chat_user_context:
        return jsonify({"error": "Missing chat user context."}), 400

    user_id = chat_user_context["user_id"]

    conversations = list(conversations_col.find({
        "user_id": user_id
    }))

    conversations.sort(
        key=lambda item: item.get("updated_at", ""),
        reverse=True
    )

    return jsonify({
        "conversations": [
            clean_conversation_for_list(conversation)
            for conversation in conversations
        ]
    }), 200


def parse_api_request():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None

    return {
        "apikey": extract_bearer_api_key(),
        "requestbody": payload,
    }


def extract_bearer_api_key():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, credentials = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer":
        return ""

    return credentials.strip()


def validate_public_request(request_body):
    def invalid(message, param, code="invalid_value"):
        return {"message": message, "param": param, "code": code}

    supported_fields = {
        "conversation_id",
        "frequency_penalty",
        "input",
        "instructions",
        "max_output_tokens",
        "metadata",
        "model",
        "presence_penalty",
        "previous_response_id",
        "store",
        "stream",
        "temperature",
        "top_p",
    }
    for field in request_body:
        if field not in supported_fields:
            return invalid(
                f"Parameter '{field}' is not supported.",
                field,
                "unsupported_parameter",
            )

    if "model" not in request_body:
        return invalid("model is required.", "model", "missing_required_parameter")
    model = request_body.get("model")
    if not isinstance(model, str) or model != PUBLIC_MODEL:
        return invalid(
            f"Unsupported model. Use '{PUBLIC_MODEL}'.",
            "model",
            "model_not_found",
        )

    input_value = request_body.get("input")
    if isinstance(input_value, str):
        if not input_value.strip():
            return invalid("input must not be empty.", "input")
        input_character_count = len(input_value)
    elif isinstance(input_value, list):
        if not input_value:
            return invalid("input must not be empty.", "input")
        input_character_count = 0
        user_message_present = False
        for message_index, message in enumerate(input_value):
            message_param = f"input[{message_index}]"
            if not isinstance(message, dict):
                return invalid("Each input item must be an object.", message_param)
            role = message.get("role", "user")
            if role not in {"user", "assistant", "system", "developer"}:
                return invalid(
                    f"Unsupported input role '{role}'.",
                    f"{message_param}.role",
                    "unsupported_role",
                )
            user_message_present = user_message_present or role == "user"
            content = message.get("content")
            if isinstance(content, str):
                if not content.strip():
                    return invalid("Message content must not be empty.", f"{message_param}.content")
                input_character_count += len(content)
                continue
            if not isinstance(content, list) or not content:
                return invalid(
                    "Message content must be a non-empty string or text-block array.",
                    f"{message_param}.content",
                )
            for block_index, block in enumerate(content):
                block_param = f"{message_param}.content[{block_index}]"
                if not isinstance(block, dict):
                    return invalid("Each content block must be an object.", block_param)
                block_type = block.get("type")
                if block_type not in {"input_text", "output_text", "text"}:
                    return invalid(
                        f"Content type '{block_type}' is not supported.",
                        f"{block_param}.type",
                        "unsupported_content_type",
                    )
                text = block.get("text")
                if not isinstance(text, str) or not text.strip():
                    return invalid("Text content must not be empty.", f"{block_param}.text")
                input_character_count += len(text)
        if not user_message_present:
            return invalid("input must contain at least one user message.", "input")
    else:
        return invalid(
            "input must be a non-empty string or message array.",
            "input",
            "invalid_type",
        )

    instructions = request_body.get("instructions")
    if instructions is not None and (
        not isinstance(instructions, str) or not instructions.strip()
    ):
        return invalid("instructions must be a non-empty string.", "instructions")
    input_character_count += len(instructions) if isinstance(instructions, str) else 0
    if input_character_count > MAX_CONTEXT_CHARS:
        return invalid(
            f"Current input exceeds the {MAX_CONTEXT_CHARS}-character context limit.",
            "input",
            "input_too_large",
        )

    for field in ("store", "stream"):
        if field in request_body and not isinstance(request_body[field], bool):
            return invalid(f"{field} must be a boolean.", field, "invalid_type")
    if request_body.get("stream") is True:
        return invalid(
            "Streaming is not currently supported.",
            "stream",
            "unsupported_parameter",
        )

    for field in ("conversation_id", "previous_response_id"):
        value = request_body.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            return invalid(f"{field} must be a non-empty string.", field, "invalid_type")
    if request_body.get("conversation_id") and request_body.get("previous_response_id"):
        return invalid(
            "conversation_id and previous_response_id cannot be used together.",
            "previous_response_id",
            "invalid_parameter_combination",
        )
    if request_body.get("conversation_id") and request_body.get("store") is False:
        return invalid(
            "conversation_id requires store to be true.",
            "store",
            "invalid_parameter_combination",
        )

    numeric_ranges = {
        "temperature": (0, 2),
        "top_p": (0, 1),
        "frequency_penalty": (-2, 2),
        "presence_penalty": (-2, 2),
    }
    for field, (minimum, maximum) in numeric_ranges.items():
        if field not in request_body:
            continue
        value = request_body[field]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            return invalid(f"{field} must be a finite number.", field, "invalid_type")
        if not minimum <= value <= maximum:
            return invalid(
                f"{field} must be between {minimum} and {maximum}.",
                field,
            )

    if "max_output_tokens" in request_body:
        value = request_body["max_output_tokens"]
        if not isinstance(value, int) or isinstance(value, bool):
            return invalid(
                "max_output_tokens must be an integer.",
                "max_output_tokens",
                "invalid_type",
            )
        if not 1 <= value <= MAX_OUTPUT_TOKENS:
            return invalid(
                f"max_output_tokens must be between 1 and {MAX_OUTPUT_TOKENS}.",
                "max_output_tokens",
            )

    metadata = request_body.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            return invalid("metadata must be an object.", "metadata", "invalid_type")
        if len(json.dumps(metadata, ensure_ascii=False).encode("utf-8")) > 16 * 1024:
            return invalid("metadata must not exceed 16 KiB.", "metadata", "metadata_too_large")

    return None


def check_key(key):
    return get_key_doc(key) is not None

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def hash_api_key(key):
    return hash_api_key_value(key)

def parse_expiration(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def key_doc_is_active(key_doc):
    if not isinstance(key_doc, dict):
        return False
    if key_doc.get("is_active") is False:
        return False
    if key_doc.get("deleted_at") or key_doc.get("revoked_at"):
        return False

    expiration_value = key_doc.get("expire") or key_doc.get("expires_at")
    expires_at = parse_expiration(expiration_value)
    if expiration_value is not None and expiration_value != "" and expires_at is None:
        return False
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        return False

    return True


def is_service_key_doc(key_doc):
    if not isinstance(key_doc, dict):
        return False
    return (
        str(key_doc.get("owner_type") or "").strip().lower() == "service"
        or str(key_doc.get("key_scope") or "").strip().lower() == "service"
    )


def is_trusted_web_key_doc(key_doc):
    if not isinstance(key_doc, dict):
        return False
    return (
        is_service_key_doc(key_doc)
        or str(key_doc.get("key_scope") or "").strip().lower()
        == "user-default"
    )


def normalize_identity(value):
    return str(value).strip().lower() if value is not None else ""


def has_valid_internal_proxy_secret():
    if not INTERNAL_PROXY_SECRET:
        return False
    provided = request.headers.get("X-Rocky-Internal-Secret", "")
    return bool(provided) and hmac.compare_digest(provided, INTERNAL_PROXY_SECRET)


def forwarded_identity_headers_present():
    return any(
        request.headers.get(name)
        for name in (
            "X-Rocky-User-Id",
            "X-Rocky-User-Email",
            "X-Rocky-User-Name",
            "X-Rocky-User-Is-Admin",
        )
    )


def get_forwarded_user_context():
    if not has_valid_internal_proxy_secret():
        return {
            "user_id": None,
            "user_email": None,
            "user_name": None,
        }
    user_id = normalize_identity(request.headers.get("X-Rocky-User-Id"))
    user_email = normalize_identity(request.headers.get("X-Rocky-User-Email"))
    user_name = str(request.headers.get("X-Rocky-User-Name") or "").strip()

    return {
        "user_id": user_id or user_email,
        "user_email": user_email or None,
        "user_name": user_name or None,
    }


def get_chat_user_context(key_doc):
    if (
        is_trusted_web_key_doc(key_doc)
        and forwarded_identity_headers_present()
        and not has_valid_internal_proxy_secret()
    ):
        return None
    if is_service_key_doc(key_doc):
        context = get_forwarded_user_context()
        if not context["user_id"]:
            return None
        return context

    if is_trusted_web_key_doc(key_doc) and has_valid_internal_proxy_secret():
        context = get_forwarded_user_context()
        if context["user_id"]:
            return context

    user_id = get_owner_id(key_doc)
    if not user_id:
        return None

    user_email = normalize_identity(key_doc.get("email")) if isinstance(key_doc, dict) else ""

    return {
        "user_id": user_id,
        "user_email": user_email or None,
        "user_name": None,
    }


def is_trusted_web_request(key_doc):
    return (
        is_trusted_web_key_doc(key_doc)
        and has_valid_internal_proxy_secret()
        and bool(get_forwarded_user_context().get("user_id"))
    )


def find_valid_key_doc(collection, query):
    if collection is None:
        return None
    key_doc = collection.find_one(query)
    if key_doc_is_active(key_doc):
        return key_doc
    return None


def current_api_keys_collection():
    """Return a fresh Mongita key view so cross-process writes are visible."""
    if not MONGITA_KEY_READ_REFRESH_ENABLED:
        return api_keys_col

    try:
        database = MongitaClientDisk(str(MONGITA_PATH))[DB_NAME]
        return database["api_keys"]
    except Exception as exc:
        logging.warning(
            "Could not refresh local API key records. error_type=%s",
            type(exc).__name__,
        )
        return None


def development_auth_bypass_enabled():
    bypass_requested = os.getenv("ROCKY_DEV_AUTH_BYPASS", "false").strip().lower() == "true"
    if not bypass_requested:
        return False
    if APP_ENV != "development":
        logging.warning(
            "Ignoring ROCKY_DEV_AUTH_BYPASS outside development. app_env=%s",
            APP_ENV,
        )
        return False
    return True

def get_key_doc(key):
    """
    Returns the API key document if valid.

    Development bypass:
    Set ROCKY_DEV_AUTH_BYPASS=true to skip real API key validation locally.
    This is only for local/dev history testing.
    """
    if development_auth_bypass_enabled():
        return {
            "api-key": "dev-bypass",
            "key_id": DEVELOPMENT_BYPASS_KEY_ID,
            "owner_id": "dev-user",
        }

    normalized_key = key.strip() if isinstance(key, str) else ""
    if not normalized_key:
        return None

    key_hash = hash_api_key(normalized_key)

    return find_valid_key_doc(current_api_keys_collection(), {"hash": key_hash})

def get_owner_id(key_doc):
    """Gets the user ID to see who owns the conversation"""
    if not key_doc:
        return "unknown-user"

    return str(
        key_doc.get("user_id")
        or key_doc.get("owner_id")
        or key_doc.get("email")
        or key_doc.get("_id")
        or "unknown-user"
    )


def response_owner_scope(key_doc):
    if is_trusted_web_request(key_doc):
        context = get_forwarded_user_context()
        return f"web-user:{context['user_id']}"
    credential_id = (
        key_doc.get("key_id")
        or key_doc.get("hash")
        or get_owner_id(key_doc)
    )
    return f"credential:{credential_id}"


def load_response_context(response_id, owner_scope):
    if responses_col is None:
        return None
    response_doc = responses_col.find_one({
        "response_id": response_id,
        "owner_scope": owner_scope,
    })
    if not isinstance(response_doc, dict):
        return None
    context_messages = response_doc.get("context_messages")
    return context_messages if isinstance(context_messages, list) else None


def save_response_context(response_id, owner_scope, context_messages):
    if responses_col is None:
        raise RuntimeError("Response storage is unavailable.")
    responses_col.insert_one({
        "response_id": response_id,
        "owner_scope": owner_scope,
        "model": PUBLIC_MODEL,
        "context_messages": context_messages,
        "created_at": utc_now(),
    })


def message_character_count(message):
    if not isinstance(message, dict):
        return 0
    return len(extract_message_content_text(message.get("content")))


def bounded_history_messages(history_messages, current_messages, instructions=None):
    history = history_messages if isinstance(history_messages, list) else []
    current_size = sum(message_character_count(message) for message in current_messages)
    if isinstance(instructions, str):
        current_size += len(instructions)
    remaining = max(0, MAX_CONTEXT_CHARS - current_size)

    selected_reversed = []
    for message in reversed(history):
        size = message_character_count(message)
        if size > remaining:
            break
        selected_reversed.append(message)
        remaining -= size

    selected = list(reversed(selected_reversed))
    return selected, len(history) - len(selected)

def should_store_response(request_body):
    """Responses are stored by default; institutional telemetry is independent."""
    return not (
        isinstance(request_body, dict)
        and request_body.get("store") is False
    )


def should_use_web_history(request_body, key_doc):
    if not isinstance(request_body, dict) or not should_store_response(request_body):
        return False
    return bool(request_body.get("conversation_id")) or is_trusted_web_request(key_doc)


def should_store_history(request_body):
    """Backward-compatible helper retained for callers outside the main route."""
    return should_store_response(request_body)


def extract_user_message_text(request_body):
    """Extracts the latest user message from the request body."""
    if isinstance(request_body, str):
        return request_body if request_body.strip() else ""

    if not isinstance(request_body, dict):
        return ""

    input_value = request_body.get("input")
    if isinstance(input_value, str):
        return input_value if input_value.strip() else ""

    if not isinstance(input_value, list):
        return ""

    for message in reversed(input_value):
        if not isinstance(message, dict) or message.get("role", "user") != "user":
            continue
        text = extract_message_content_text(message.get("content"))
        if text:
            return text
    return ""

def get_or_create_conversation(user_id, conversation_id, first_message, user_context=None):
    """
    Reuses an existing conversation if conversation_id is provided.
    Otherwise creates a new conversation document.
    """
    if conversation_id:
        existing = conversations_col.find_one({
            "conversation_id": conversation_id,
            "user_id": user_id
        })

        if existing:
            return conversation_id
        return None

    new_conversation_id = str(uuid4())

    title = first_message[:60].strip() or "New Chat"

    context = user_context if isinstance(user_context, dict) else {}

    conversations_col.insert_one({
        "conversation_id": new_conversation_id,
        "user_id": user_id,
        "user_email": context.get("user_email"),
        "user_name": context.get("user_name"),
        "title": title,
        "created_at": utc_now(),
        "updated_at": utc_now()
    })

    return new_conversation_id

def save_message(
    conversation_id,
    user_id,
    role,
    content,
    model=None,
    user_context=None,
    status="sent",
):
    """
    Saves one chat message to MongoDB/Mongita.

    Each user or assistant turn becomes one document in the messages collection.
    """
    context = user_context if isinstance(user_context, dict) else {}

    message_id = str(uuid4())
    messages_col.insert_one({
        "message_id": message_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "user_email": context.get("user_email"),
        "role": role,
        "content": content,
        "model": model,
        "status": status,
        "created_at": utc_now()
    })

    conversations_col.update_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id
        },
        {
            "$set": {
                "updated_at": utc_now()
            }
        }
    )

    return message_id


def update_message_status(conversation_id, user_id, message_id, status):
    """Updates the durable delivery state for one owned chat message."""
    messages_col.update_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "message_id": message_id,
        },
        {"$set": {"status": status}},
    )

def load_recent_messages(conversation_id, user_id, limit=20):
    """
    Loads the most recent messages for a conversation.

    Sorting is done in Python so it works with both MongoDB and Mongita.
    """
    messages = list(messages_col.find({
        "conversation_id": conversation_id,
        "user_id": user_id
    }))

    messages = [
        message
        for message in messages
        if message.get("status", "sent") == "sent"
    ]
    messages.sort(key=lambda item: item.get("created_at", ""))

    return messages[-limit:]

def load_conversation_messages(conversation_id, user_id):
    """
    Loads every message for one conversation owned by this user.
    Used for export, not model context.
    """
    messages = list(messages_col.find({
        "conversation_id": conversation_id,
        "user_id": user_id
    }))

    messages.sort(key=lambda item: item.get("created_at", ""))

    return messages

def clean_conversation_for_list(conversation):
    return {
        "conversation_id": conversation.get("conversation_id"),
        "title": conversation.get("title"),
        "created_at": conversation.get("created_at"),
        "updated_at": conversation.get("updated_at")
    }


def clean_message_for_export(message):
    """
    Removes Mongo/internal fields so jsonify does not choke on ObjectId.
    """
    return {
        "message_id": message.get("message_id"),
        "role": message.get("role"),
        "content": message.get("content"),
        "model": message.get("model"),
        "status": message.get("status", "sent"),
        "created_at": message.get("created_at")
    }


def format_conversation_markdown(conversation, messages):
    """
    Converts one conversation into a readable Markdown transcript.
    """
    title = conversation.get("title", "Rocky Conversation")
    conversation_id = conversation.get("conversation_id", "")
    created_at = conversation.get("created_at", "")
    updated_at = conversation.get("updated_at", "")

    lines = [
        f"# {title}",
        "",
        f"- Conversation ID: `{conversation_id}`",
        f"- Created at: {created_at}",
        f"- Updated at: {updated_at}",
        "",
        "---",
        ""
    ]

    for message in messages:
        role = str(message.get("role", "unknown")).title()
        created = message.get("created_at", "")
        content = str(message.get("content", "")).strip()

        lines.extend([
            f"## {role}",
            "",
            f"*{created}*",
            "",
            content,
            "",
            "---",
            ""
        ])

    return "\n".join(lines)

def messages_to_granite_input(messages):
    """
    Converts stored DB messages into the Rocky style input[] format
    that granite-llm-server already knows how to parse.
    """
    granite_input = []

    for message in messages:
        if message.get("status", "sent") != "sent":
            continue
        role = message.get("role", "user")
        content = str(message.get("content", ""))

        if not content.strip():
            continue

        granite_input.append({
            "role": role,
            "content": [
                {
                    "type": "input_text",
                    "text": content
                }
            ]
        })

    return granite_input

def build_history_request_body(original_request_body, granite_input):
    """
    Builds a request body for Granite using loaded conversation history.
    Keeps generation options, but removes app-only fields.
    """
    if isinstance(original_request_body, dict):
        request_body = {
            k: v for k, v in original_request_body.items()
            if k not in {"input", "conversation_id", "store"}
        }
    else:
        request_body = {}

    request_body["model"] = PUBLIC_MODEL
    request_body["input"] = granite_input

    return request_body



def extract_message_content_text(content):
    if isinstance(content, str):
        return content if content.strip() else ""
    if not isinstance(content, list):
        return ""

    text_parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") not in {"input_text", "output_text", "text"}:
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text)
    return "\n".join(text_parts)


def normalize_input_messages(input_value):
    if isinstance(input_value, str):
        if not input_value.strip():
            return []
        return [{
            "role": "user",
            "content": [{"type": "input_text", "text": input_value}],
        }]

    if not isinstance(input_value, list):
        return []

    normalized_messages = []
    for message in input_value:
        if not isinstance(message, dict):
            continue
        text = extract_message_content_text(message.get("content"))
        if not text:
            continue
        role = str(message.get("role") or "user").strip().lower()
        if role not in {"user", "assistant", "system", "developer"}:
            continue
        if role == "developer":
            role = "system"
        normalized_messages.append({
            "role": role,
            "content": [{"type": "input_text", "text": text}],
        })
    return normalized_messages


def build_granite_payload_with_context(request_body, history_messages=None):
    if request_body is None:
        return None, [], 0, []

    if isinstance(request_body, str):
        request_body = {"input": request_body}

    if not isinstance(request_body, dict):
        return None, [], 0, []

    current_messages = normalize_input_messages(request_body.get("input"))
    if not current_messages:
        return None, [], 0, []

    instructions = request_body.get("instructions")
    if instructions is not None:
        if not isinstance(instructions, str) or not instructions.strip():
            return None, [], 0, []

    retained_history, omitted_history_count = bounded_history_messages(
        history_messages,
        current_messages,
        instructions=instructions,
    )
    input_messages = [*retained_history, *current_messages]
    if isinstance(instructions, str):
        input_messages.insert(0, {
            "role": "system",
            "content": [{"type": "input_text", "text": instructions.strip()}],
        })

    payload = {
        "model": INFERENCE_MODEL,
        "input": input_messages,
    }

    for option in (
        "frequency_penalty",
        "max_output_tokens",
        "presence_penalty",
                "temperature",
        "top_p",
    ):
        if option in request_body:
            payload[option] = request_body[option]

    return payload, current_messages, omitted_history_count, retained_history


def _build_granite_payload(request_body):
    payload, _current_messages, _omitted_history_count, _retained_history = (
        build_granite_payload_with_context(request_body)
    )
    return payload


def build_response_payload(output_text, request_body, metadata, model_metrics):
    response_id = f"resp_{uuid4().hex}"
    message_id = f"msg_{uuid4().hex}"
    prompt_tokens = int((model_metrics or {}).get("prompt_eval_count") or 0)
    output_tokens = int((model_metrics or {}).get("eval_count") or 0)

    payload = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": PUBLIC_MODEL,
        "parallel_tool_calls": False,
        "tool_choice": "none",
        "tools": [],
        "output": [{
            "id": message_id,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": output_text,
                "annotations": [],
            }],
        }],
        "output_text": output_text,
        "metadata": (
            request_body.get("metadata", {})
            if isinstance(request_body, dict)
            and isinstance(request_body.get("metadata", {}), dict)
            else {}
        ),
        "usage": {
            "input_tokens": prompt_tokens,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 0,
            },
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": prompt_tokens + output_tokens,
        },
    }

    if isinstance(request_body, dict):
        for field in ("max_output_tokens", "temperature", "top_p"):
            if field in request_body:
                payload[field] = request_body[field]
    return payload


def extract_granite_telemetry(data):
    if not isinstance(data, dict):
        return {}
    telemetry = data.get("telemetry")
    if not isinstance(telemetry, dict):
        return {}
    provider = telemetry.get("provider")
    metrics = dict(provider) if isinstance(provider, dict) else {}
    metrics["model_input_bytes"] = telemetry.get("model_input_bytes")
    metrics["model_output_bytes"] = telemetry.get("model_output_bytes")
    return sanitize_model_metrics(metrics)


def model_failure(error_type, metrics=None, message=None):
    messages = {
        "bad_request": "Granite rejected the request.",
        "busy": "The model is busy. Try again shortly.",
        "timeout": "Model request timed out.",
        "bad_response": "Granite returned an invalid response.",
    }
    return {
        "error": (
            message.strip()[:512]
            if isinstance(message, str) and message.strip()
            else messages.get(error_type, "Model service request failed.")
        ),
        "error_type": error_type,
        "_telemetry": metrics or {},
    }


def request_ai(request_body):
    payload = _build_granite_payload(request_body)
    if payload is None:
        return model_failure("bad_request")

    try:
        headers = {}
        if GRANITE_AUTH_TOKEN:
            headers["X-Rocky-Granite-Token"] = GRANITE_AUTH_TOKEN
        resp = requests.post(
            GRANITE_URL,
            json=payload,
            headers=headers,
            timeout=GRANITE_TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        return model_failure("timeout")
    except requests.RequestException:
        return model_failure("network")

    response_status = getattr(resp, "status_code", 500)
    try:
        data = resp.json()
    except ValueError:
        if response_status == 504:
            return model_failure("timeout")
        error_type = "bad_response" if 200 <= response_status < 300 else "network"
        return model_failure(error_type)

    if not isinstance(data, dict):
        if response_status == 504:
            return model_failure("timeout")
        return model_failure(
            "bad_response" if 200 <= response_status < 300 else "network"
        )

    model_metrics = extract_granite_telemetry(data)
    granite_error = data.get("error")
    granite_error_type = (
        granite_error.get("type")
        if isinstance(granite_error, dict)
        else None
    )

    if not 200 <= response_status < 300 or granite_error is not None:
        if response_status == 400 or granite_error_type == "bad_request":
            error_type = "bad_request"
        elif response_status == 503 or granite_error_type == "model_busy":
            error_type = "busy"
        elif response_status == 504 or granite_error_type == "model_timeout":
            error_type = "timeout"
        else:
            error_type = "network"
        safe_message = None
        if error_type == "bad_request" and isinstance(granite_error, dict):
            safe_message = granite_error.get("message")
        return model_failure(error_type, model_metrics, message=safe_message)

    output_text = data.get("output_text")
    if not isinstance(output_text, str) or not output_text.strip():
        return model_failure("bad_response", model_metrics)

    result = dict(data)
    result.pop("telemetry", None)
    result["_telemetry"] = model_metrics
    return result


if __name__ == "__main__":
    app.run(
        host=CHAT_API_HOST,
        port=CHAT_API_PORT,
        debug=APP_ENV == "development",
        use_reloader=False,
    )
