from __future__ import annotations

import os
import hashlib
from datetime import datetime, timezone
from uuid import uuid4
import time

from flask import Flask, request, jsonify, Response
import requests
import logging
from mongita import MongitaClientDisk
from telemetry import TelemetryStore, sanitize_model_metrics

# Try PyMongo first (default to localhost). If unavailable, fall back to Mongita.
try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except Exception:  # pragma: no cover - optional dependency
    MongoClient = None
    PyMongoError = Exception


app = Flask(__name__)

CHAT_API_KEY_CONFIGURED = "ROCKY_CHAT_API_KEY" in os.environ and bool(os.getenv("ROCKY_CHAT_API_KEY", "").strip())
CHAT_API_KEY = os.getenv("ROCKY_CHAT_API_KEY", "SOME_API_KEY")
CHAT_SERVICE_OWNER_ID = os.getenv("ROCKY_CHAT_SERVICE_OWNER_ID", "rocky-chat-service@kent.edu").strip() or "rocky-chat-service@kent.edu"
CHAT_SERVICE_KEY_NAME = "rocky-chat-service"
GRANITE_URL = os.getenv("ROCKY_GRANITE_URL", "http://127.0.0.1:5002/generate")
DEFAULT_MODEL = os.getenv("ROCKY_CHAT_MODEL", os.getenv("OLLAMA_MODEL", "gemma4:latest"))
CHAT_API_HOST = os.getenv("ROCKY_CHAT_API_HOST", "127.0.0.1")
CHAT_API_PORT = int(os.getenv("ROCKY_CHAT_API_PORT", "5003"))
GRANITE_TIMEOUT_SECONDS = int(os.getenv("ROCKY_GRANITE_TIMEOUT_SECONDS", "195"))


api_keys_col = None
conversations_col = None
messages_col = None
telemetry_interactions_col = None
telemetry_current_col = None
telemetry_store = None


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


# Database configuration
DB_BACKEND = os.getenv("ROCKY_DB_BACKEND", "mongodb").strip().lower()
MONGODB_URI = os.getenv(
    "ROCKY_MONGODB_URI",
    "mongodb://127.0.0.1:27017"
).strip()
DB_NAME = os.getenv("ROCKY_DB_NAME", "rocky_db").strip() or "rocky_db"

MONGODB_CONNECT_ATTEMPTS = int(
    os.getenv("ROCKY_MONGODB_CONNECT_ATTEMPTS", "10")
)
MONGODB_RETRY_SECONDS = float(
    os.getenv("ROCKY_MONGODB_RETRY_SECONDS", "2")
)


def initialize_database():
    global api_keys_col
    global conversations_col
    global messages_col
    global telemetry_interactions_col
    global telemetry_current_col

    if DB_BACKEND == "mongodb":
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
                telemetry_interactions_col = database["telemetry_interactions"]
                telemetry_current_col = database["telemetry_current"]

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
            "Using Mongita database at api-rocky/mongitaDB. "
            "This backend should only be used for local development."
        )

        client = MongitaClientDisk("mongitaDB")
        database = client[DB_NAME]

        api_keys_col = database["api_keys"]
        conversations_col = database["conversations"]
        messages_col = database["messages"]
        return

    raise RuntimeError(
        f"Unsupported ROCKY_DB_BACKEND value: {DB_BACKEND!r}. "
        "Expected 'mongodb' or 'mongita'."
    )


telemetry_enabled = os.getenv(
    "ROCKY_TELEMETRY_ENABLED", "true"
).strip().lower() not in {"0", "false", "no", "off"}


def should_skip_database_initialization_for_tests():
    skip_requested = os.getenv("ROCKY_TEST_SKIP_DATABASE_INIT","false").strip().lower() == "true"

    if not skip_requested:
        return False

    app_environment = os.getenv("ROCKY_APP_ENV","").strip().lower()

    if app_environment != "test":
        raise RuntimeError("Database initialization can only be skipped when ROCKY_APP_ENV=test")

    return True

if not should_skip_database_initialization_for_tests():
    initialize_database()
    ensure_chat_indexes()
    ensure_chat_service_api_key()

    if DB_BACKEND == "mongodb" and telemetry_enabled:
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


def begin_telemetry_interaction():
    if telemetry_store is None:
        return None
    try:
        return telemetry_store.record_accepted()
    except Exception as error:
        app.logger.warning(
            "telemetry.accept_unexpected_failure error_type=%s",
            type(error).__name__,
        )
        return None


def finish_telemetry_interaction(interaction, outcome, model_metrics=None):
    if telemetry_store is None or interaction is None:
        return False
    try:
        return telemetry_store.record_terminal(
            interaction, outcome, model_metrics=model_metrics
        )
    except Exception as error:
        app.logger.warning(
            "telemetry.terminal_unexpected_failure error_type=%s",
            type(error).__name__,
        )
        return False


def model_error_status(error_type):
    return {"bad_request": 400, "timeout": 504}.get(error_type, 502)


def telemetry_json(payload, status, interaction):
    response = jsonify(payload)
    if isinstance(interaction, dict) and interaction.get("request_id"):
        response.headers["X-Rocky-Request-Id"] = interaction["request_id"]
    return response, status



@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "api-rocky"}), 200


@app.route("/v1/responses", methods=["POST"])
def rocky_api():

    # parse incoming JSON into `apirequest` with keys: `apikey`, `requestbody`
    apirequest = parse_api_request()
    if not apirequest:
        return jsonify({"error": "Bad request: expected JSON payload"}), 400

    #verify and request AI
    key_doc = get_key_doc(apirequest.get("apikey"))

    if not key_doc:
        return jsonify({"error": "Invalid API key"}), 401

    request_body = apirequest.get("requestbody")
    store_history = should_store_history(request_body)
    granite_payload = None
    chat_user_context = None
    user_id = None
    user_message = None
    requested_conversation_id = None

    if store_history:
        chat_user_context = get_chat_user_context(key_doc)
        if not chat_user_context:
            return jsonify({"error": "Missing chat user context."}), 400

        user_id = chat_user_context["user_id"]
        user_message = extract_user_message_text(request_body)
        if not user_message:
            return jsonify({"error": "Missing message."}), 400
        if isinstance(request_body, dict):
            requested_conversation_id = request_body.get("conversation_id")
    else:
        granite_payload = _build_granite_payload(request_body)
        if not has_effective_user_prompt(granite_payload):
            return jsonify({"error": "Missing message."}), 400

    interaction = begin_telemetry_interaction()
    model_metrics = None
    conversation_id = None
    try:
        model_request = granite_payload
        if store_history:
            conversation_id = get_or_create_conversation(
                user_id=user_id,
                conversation_id=requested_conversation_id,
                first_message=user_message,
                user_context=chat_user_context
            )

            save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=user_message,
                user_context=chat_user_context
            )

            recent_messages = load_recent_messages(conversation_id, user_id)
            granite_input = messages_to_granite_input(recent_messages)
            history_request_body = build_history_request_body(
                request_body,
                granite_input,
            )
            model_request = history_request_body

        response = request_ai(model_request)
        model_metrics = response.get("_telemetry")
        if response.get("error"):
            outcome = (
                "timed_out"
                if response.get("error_type") == "timeout"
                else "failed"
            )
            finish_telemetry_interaction(interaction, outcome, model_metrics)
            return telemetry_json(
                {"error": response["error"]},
                model_error_status(response.get("error_type")),
                interaction,
            )

        assistant_reply = response["output_text"]
        if store_history:
            save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=assistant_reply,
                model=response.get("model"),
                user_context=chat_user_context
            )
    except Exception:
        finish_telemetry_interaction(interaction, "failed", model_metrics)
        raise

    finish_telemetry_interaction(interaction, "completed", model_metrics)
    response_payload = {
        "reply": assistant_reply,
        "model": response.get("model"),
        "metadata": response.get("metadata", {}),
    }
    if conversation_id is not None:
        response_payload["conversation_id"] = conversation_id
    return telemetry_json(response_payload, 200, interaction)

@app.route("/conversations/<conversation_id>/export", methods=["POST"])
def export_conversation(conversation_id):
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Bad request: expected JSON payload"}), 400

    key_doc = get_key_doc(payload.get("api-key"))

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

    key_doc = get_key_doc(payload.get("api-key"))

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

    key_doc = get_key_doc(payload.get("api-key"))

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
    return get_key_doc(key) is not None

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def hash_api_key(key):
    return hash_api_key_value(key)

def parse_expiration(value):
    if value in {None, ""}:
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

    expires_at = parse_expiration(key_doc.get("expire") or key_doc.get("expires_at"))
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


def normalize_identity(value):
    return str(value).strip().lower() if value is not None else ""


def get_forwarded_user_context():
    user_id = normalize_identity(request.headers.get("X-Rocky-User-Id"))
    user_email = normalize_identity(request.headers.get("X-Rocky-User-Email"))
    user_name = str(request.headers.get("X-Rocky-User-Name") or "").strip()

    return {
        "user_id": user_id or user_email,
        "user_email": user_email or None,
        "user_name": user_name or None,
    }


def get_chat_user_context(key_doc):
    if is_service_key_doc(key_doc):
        context = get_forwarded_user_context()
        if not context["user_id"]:
            return None
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


def find_valid_key_doc(collection, query):
    if collection is None:
        return None
    key_doc = collection.find_one(query)
    if key_doc_is_active(key_doc):
        return key_doc
    return None

def get_key_doc(key):
    """
    Returns the API key document if valid.

    Development bypass:
    Set ROCKY_DEV_AUTH_BYPASS=true to skip real API key validation locally.
    This is only for local/dev history testing.
    """
    if os.getenv("ROCKY_DEV_AUTH_BYPASS", "false").lower() == "true":
        return {
            "api-key": "dev-bypass",
            "owner_id": "dev-user"
        }

    normalized_key = key.strip() if isinstance(key, str) else ""
    if not normalized_key:
        return None

    key_hash = hash_api_key(normalized_key)

    return find_valid_key_doc(api_keys_col, {"hash": key_hash})

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

def should_store_history(request_body):
    """
    History is enabled by default.
    If request has store: false, do not save/load history.

    Maybe add a setting in settings to turn on and off History?
    """
    if isinstance(request_body, dict) and request_body.get("store") is False:
        return False

    return True


def extract_user_message_text(request_body):
    """Extracts the latest user message from the request body."""
    if isinstance(request_body, str):
        return request_body.strip()

    if not isinstance(request_body, dict):
        return ""

    message = request_body.get("message")
    return message.strip() if isinstance(message, str) else ""

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

def save_message(conversation_id, user_id, role, content, model=None, user_context=None):
    """
    Saves one chat message to MongoDB/Mongita.

    Each user or assistant turn becomes one document in the messages collection.
    """
    context = user_context if isinstance(user_context, dict) else {}

    messages_col.insert_one({
        "message_id": str(uuid4()),
        "conversation_id": conversation_id,
        "user_id": user_id,
        "user_email": context.get("user_email"),
        "role": role,
        "content": content,
        "model": model,
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

def load_recent_messages(conversation_id, user_id, limit=20):
    """
    Loads the most recent messages for a conversation.

    Sorting is done in Python so it works with both MongoDB and Mongita.
    """
    messages = list(messages_col.find({
        "conversation_id": conversation_id,
        "user_id": user_id
    }))

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
        role = message.get("role", "user")
        content = str(message.get("content", "")).strip()

        if not content:
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
            if k not in {"message", "conversation_id", "store"}
        }
    else:
        request_body = {}

    request_body["model"] = str(request_body.get("model") or DEFAULT_MODEL)
    request_body["input"] = granite_input

    return request_body



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

    message_text = request_body.get("message")
    if not isinstance(message_text, str) or not message_text.strip():
        return None
    message_text = message_text.strip()

    payload = {
        "model": str(request_body.get("model") or DEFAULT_MODEL),
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": message_text}],
            }
        ],
    }

    if "frequency_penalty" in request_body:
        payload["frequency_penalty"] = request_body["frequency_penalty"]
    if "max_output_tokens" in request_body:
        payload["max_output_tokens"] = request_body["max_output_tokens"]
    if "presence_penalty" in request_body:
        payload["presence_penalty"] = request_body["presence_penalty"]
    if "temperature" in request_body:
        payload["temperature"] = request_body["temperature"]
    if "top_p" in request_body:
        payload["top_p"] = request_body["top_p"]
    if "max_output_tokens" in request_body:
        payload["max_output_tokens"] = request_body["max_output_tokens"]

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


def model_failure(error_type, metrics=None):
    messages = {
        "bad_request": "Granite rejected the request.",
        "timeout": "Model request timed out.",
        "bad_response": "Granite returned an invalid response.",
    }
    return {
        "error": messages.get(error_type, "Model service request failed."),
        "error_type": error_type,
        "_telemetry": metrics or {},
    }


def request_ai(request_body):
    payload = _build_granite_payload(request_body)
    if payload is None:
        return model_failure("bad_request")

    try:
        resp = requests.post(
            GRANITE_URL,
            json=payload,
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
        elif response_status == 504 or granite_error_type == "model_timeout":
            error_type = "timeout"
        else:
            error_type = "network"
        return model_failure(error_type, model_metrics)

    output_text = data.get("output_text")
    if not isinstance(output_text, str) or not output_text.strip():
        return model_failure("bad_response", model_metrics)

    result = dict(data)
    result.pop("telemetry", None)
    result["_telemetry"] = model_metrics
    return result


if __name__ == "__main__":
	# default local dev run
	app.run(host=CHAT_API_HOST, port=CHAT_API_PORT, debug=True)
