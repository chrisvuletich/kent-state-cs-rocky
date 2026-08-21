from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import logging
import random
import sys
from typing import Any
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId
from flask import Flask, jsonify, request

from backend.authz import get_requester, require_admin, require_internal_proxy, require_requester_identity
from backend.course_actions import (
    add_course_members,
    add_group_member,
    apply_course_metadata_patch,
    can_manage_api_keys,
    can_manage_metadata,
    can_manage_people,
    can_request_api_key,
    create_course_group,
    delete_course_api_keys,
    filter_visible_courses,
    get_course_record,
    remove_course_member,
    remove_group_member,
    regenerate_course_api_key,
    reconcile_course_members_for_user,
    resolve_course_key_owner,
    set_course_active_state,
    set_course_api_key_active_state,
    update_course_group_key_limit,
    update_course_instructor_key_limit,
    update_course_instructor_handout_limit,
    update_course_member_key_limit,
)
from backend.config import get_settings
from backend.storage import Collections, build_collections
from backend.validation import (
    is_valid_email,
    normalize_str,
    validate_course_payload,
    validate_user_payload,
)
from backend.route_handlers import auth as auth_handlers
from backend.route_handlers import audit as audit_handlers
from backend.route_handlers import content as content_handlers
from backend.route_handlers import courses as course_handlers
from backend.route_handlers import settings as settings_handlers
from backend.route_handlers import users as user_handlers

SEED_DATA_DIR = Path(__file__).resolve().parent / "seed-data"
if str(SEED_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(SEED_DATA_DIR))


def _load_seed_data_module():
    module_path = SEED_DATA_DIR / "seed_data.py"
    spec = importlib.util.spec_from_file_location("rocky_backend_seed_data", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load seed data module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_seed_data = _load_seed_data_module()
seed_data_database = _seed_data.seed_database

settings = get_settings()
app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rocky.backend")

collections: Collections = build_collections(settings)
users = collections.users
whitelist_users = collections.whitelist_users
courses = collections.courses
api_keys = collections.api_keys
api_history = collections.api_history
telemetry_interactions = collections.telemetry_interactions
telemetry_current = collections.telemetry_current
telemetry_hardware = collections.telemetry_hardware

ALLOWED_THEME_PREFERENCES = {"light", "dark"}
ALLOWED_PROFILE_PICTURES = {
    "/batch_squirrel.svg",
    "/batch_dog.svg",
    "/batch_duck.svg",
    "/batch_fish.svg",
    "/batch_penguin.svg",
    "/batch_cat.svg",
}
API_KEY_REGENERATION_COOLDOWN = timedelta(minutes=5)
KENT_EMAIL_SUFFIX = "@kent.edu"


def _parse_object_id(value: str):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _bad_request(message: str):
    return jsonify({"error": message}), 400


def _iter_course_api_keys(course: dict[str, Any]) -> list[dict[str, Any]]:
    course_code = normalize_str(course.get("code"))
    course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None
    keys: list[dict[str, Any]] = []
    for entry in api_keys.find():
        if not isinstance(entry, dict):
            continue
        if course_numeric_id is not None:
            if entry.get("course_id") != course_numeric_id:
                continue
        elif course_code:
            if normalize_str(entry.get("c_id")) != course_code:
                continue
        else:
            continue
        keys.append(entry)
    return keys


def _get_active_course_api_key(course: dict[str, Any]):
    keys = [
        entry
        for entry in _iter_course_api_keys(course)
        if normalize_str(entry.get("hash")) and bool(entry.get("is_active", True))
    ]
    if not keys:
        return None
    return max(keys, key=lambda entry: normalize_str(entry.get("created")))


def _get_owner_key_limit(course: dict[str, Any], owner_type: str, owner_id: str) -> int:
    normalized_owner_type = normalize_str(owner_type).lower() or "person"
    normalized_owner_id = normalize_str(owner_id).lower()
    if normalized_owner_type == "group":
        target_group = next(
            (
                group
                for group in course.get("groups", [])
                if isinstance(group, dict) and normalize_str(group.get("id")).lower() == normalized_owner_id
            ),
            None,
        )
        key_limit = target_group.get("key_limit") if isinstance(target_group, dict) else None
        return key_limit if isinstance(key_limit, int) and key_limit >= 0 else 1

    def normalize_identifier(value: Any) -> str:
        if value is None:
            return ""
        string_value = str(value) if not isinstance(value, str) else value
        return normalize_str(string_value).lower()

    instructor_identifiers = {
        normalize_identifier(course.get("instructor_id") or course.get("instructorId")),
        normalize_identifier(course.get("instructor_email") or course.get("instructorEmail")),
    }
    ta_ids_list = course.get("ta_ids") if isinstance(course.get("ta_ids"), list) else course.get("taIds") if isinstance(course.get("taIds"), list) else []
    ta_emails_list = course.get("ta_emails") if isinstance(course.get("ta_emails"), list) else course.get("taEmails") if isinstance(course.get("taEmails"), list) else []
    instructor_identifiers.update(
        normalize_identifier(identifier)
        for identifier in ta_ids_list
    )
    instructor_identifiers.update(
        normalize_identifier(identifier)
        for identifier in ta_emails_list
    )
    instructor_identifiers.discard("")
    if normalized_owner_id in instructor_identifiers:
        instructor_key_limit = course.get("instructor_key_limit") if course.get("instructor_key_limit") is not None else course.get("instructorKeyLimit")
        instructor_handout_limit = course.get("instructor_handout_limit") if course.get("instructor_handout_limit") is not None else course.get("instructorHandoutLimit")
        if normalized_owner_type == "person":
            limit = instructor_key_limit if isinstance(instructor_key_limit, int) and instructor_key_limit >= 0 else 2
            return limit
        if isinstance(instructor_handout_limit, int) and instructor_handout_limit >= 0:
            return instructor_handout_limit
        limit = instructor_key_limit if isinstance(instructor_key_limit, int) and instructor_key_limit >= 0 else 2
        return limit

    target_member = next(
        (
            member
            for member in course.get("members", [])
            if isinstance(member, dict)
            and (
                normalize_str(member.get("id")).lower() == normalized_owner_id
                or normalize_str(member.get("email")).lower() == normalized_owner_id
            )
        ),
        None,
    )
    key_limit = target_member.get("key_limit") if isinstance(target_member, dict) else None
    if isinstance(key_limit, int) and key_limit >= 0:
        return key_limit
    
    return 0


def _serialize_api_key_summary(entry: dict[str, Any]) -> dict[str, Any]:
    slot_index = entry.get("slot_index") if isinstance(entry.get("slot_index"), int) else None
    if slot_index is None or slot_index < 1:
        key_name = normalize_str(entry.get("key_name"))
        if key_name.startswith("key-") and key_name[4:].isdigit():
            slot_index = int(key_name[4:])
        else:
            slot_index = 0

    return {
        "key_id": normalize_str(entry.get("key_id")),
        "owner_type": normalize_str(entry.get("owner_type")).lower() or "person",
        "owner_id": normalize_str(entry.get("owner_id")).lower(),
        "key_name": normalize_str(entry.get("key_name")) or "key-1",
        "slot_index": slot_index,
        "created": entry.get("created"),
        "course_id": entry.get("course_id"),
        "has_hash": bool(normalize_str(entry.get("hash"))),
        "is_active": bool(entry.get("is_active", True)),
    }


def _attach_course_key_state(course: dict[str, Any]) -> dict[str, Any]:
    attached = dict(course)
    active_key = _get_active_course_api_key(course)
    attached["has_api_key"] = active_key is not None
    if isinstance(active_key, dict):
        attached["api_key_owner_type"] = normalize_str(active_key.get("owner_type")).lower() or None
        attached["api_key_owner_id"] = normalize_str(active_key.get("owner_id")) or None
        attached["api_key_group_created_by"] = normalize_str(active_key.get("group_created_by")) or None
        attached["api_key_created"] = active_key.get("created")
    return attached


def _parse_iso_datetime(value: Any):
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _default_user_settings() -> dict[str, Any]:
    return {
        "themePreference": "light",
        "profilePicture": "/batch_dog.svg",
    }


def _serialize_value(value: Any):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def _get_collection_snapshot(collection):
    return [_serialize_value(item) for item in collection.find()]


def _resolve_user_record(user_id: str | None, email: str | None):
    normalized_email = normalize_str(email).lower()
    if is_valid_email(normalized_email):
        user = users.find_one({"email": normalized_email})
        if user:
            return user

        whitelist_user = whitelist_users.find_one({"email": normalized_email})
        if whitelist_user:
            return {
                "id": normalize_str(whitelist_user.get("id")),
                "first_name": normalize_str(whitelist_user.get("first_name")),
                "last_name": normalize_str(whitelist_user.get("last_name")),
                "email": normalized_email,
                "is_admin": bool(whitelist_user.get("is_admin")),
                "role": _user_role(whitelist_user),
                "is_active": _is_user_active(whitelist_user),
                "settings": whitelist_user.get("settings", _default_user_settings()),
                "created_at": whitelist_user.get("created_at"),
            }

    normalized_user_id = normalize_str(user_id)
    if normalized_user_id:
        user = users.find_one({"id": normalized_user_id})
        if user:
            return user

        object_id = _parse_object_id(normalized_user_id)
        if object_id is not None:
            user = users.find_one({"_id": object_id})
            if user:
                return user

        whitelist_user = whitelist_users.find_one({"id": normalized_user_id})
        if whitelist_user:
            return {
                "id": normalize_str(whitelist_user.get("id") or whitelist_user.get("_id")),
                "first_name": normalize_str(whitelist_user.get("first_name")),
                "last_name": normalize_str(whitelist_user.get("last_name")),
                "email": normalize_str(whitelist_user.get("email")).lower(),
                "is_admin": bool(whitelist_user.get("is_admin")),
                "role": _user_role(whitelist_user),
                "is_active": _is_user_active(whitelist_user),
                "settings": whitelist_user.get("settings", _default_user_settings()),
                "created_at": whitelist_user.get("created_at"),
            }

    return None


def _is_user_active(user_record: dict[str, Any]) -> bool:
    if "is_active" not in user_record:
        return True
    return bool(user_record.get("is_active"))


def _is_kent_email(email: str) -> bool:
    return email.lower().endswith(KENT_EMAIL_SUFFIX)


@app.before_request
def reject_inactive_requester():
    """Keep inactive accounts out of protected backend routes.

    The SvelteKit proxy performs the same check for a quick response. This
    database-backed check protects the Flask application if a proxy route is
    accidentally made too permissive later.
    """
    allowed_paths = {
        "/",
        "/health",
        "/auth/preview-users",
        "/auth/session-user",
        "/auth/microsoft/login",
    }
    if request.path in allowed_paths:
        return None

    email, _ = get_requester()
    if not email:
        return None

    user_record = _resolve_user_record(None, email)
    if user_record is not None and not _is_user_active(user_record):
        return jsonify({
            "error": {
                "message": "This account is inactive.",
                "type": "permission_error",
                "code": "account_inactive",
            }
        }), 403

    return None


def _normalize_oauth_payload(payload: Any):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."

    first_name = normalize_str(payload.get("firstName") or payload.get("first_name"))
    last_name = normalize_str(payload.get("lastName") or payload.get("last_name"))
    email = normalize_str(payload.get("email")).lower()
    user_id = normalize_str(payload.get("id"))

    if not is_valid_email(email):
        return None, "A valid OAuth email is required."
    if not first_name and not last_name:
        return None, "At least one of firstName or lastName is required."

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "id": user_id,
    }, None


def _resolve_requester_user_id(email: str) -> str:
    user_record = _resolve_user_record(None, email)
    if user_record:
        user_id = normalize_str(user_record.get("id") or user_record.get("_id"))
        if user_id:
            return user_id
    return normalize_str(email).lower()


def _user_role(user_record: dict[str, Any]) -> str:
    role = normalize_str(user_record.get("role")).lower()
    if role in {"student", "instructor", "admin"}:
        return role
    return "admin" if bool(user_record.get("is_admin")) else "student"


def _serialize_user(user_record: dict[str, Any]) -> dict[str, Any]:
    first_name = normalize_str(user_record.get("first_name"))
    last_name = normalize_str(user_record.get("last_name"))
    api_key_owner_id = normalize_str(user_record.get("_id") or user_record.get("id")).lower()

    return _serialize_value(
        {
            "first_name": first_name,
            "last_name": last_name,
            "email": normalize_str(user_record.get("email")).lower(),
            "id": normalize_str(user_record.get("id") or user_record.get("_id")),
            "api_key_owner_id": api_key_owner_id,
            "role": _user_role(user_record),
            "is_admin": _user_role(user_record) == "admin",
            "is_active": _is_user_active(user_record),
            "created_at": user_record.get("created_at"),
            "settings": user_record.get("settings", _default_user_settings()),
        }
    )


def _serialize_whitelist_user(entry: dict[str, Any]) -> dict[str, Any]:
    return _serialize_value(
        {
            "first_name": normalize_str(entry.get("first_name")),
            "last_name": normalize_str(entry.get("last_name")),
            "email": normalize_str(entry.get("email")).lower(),
            "id": normalize_str(entry.get("id") or entry.get("_id")),
            "role": _user_role(entry),
            "is_admin": _user_role(entry) == "admin",
            "is_active": _is_user_active(entry),
            "settings": entry.get("settings", _default_user_settings()),
            "created_at": entry.get("created_at"),
            "created_by": entry.get("created_by"),
        }
    )


def _can_access_user_record(requester_email: str, requester_is_admin: bool, target_user: dict[str, Any]) -> bool:
    if requester_is_admin:
        return True
    return normalize_str(target_user.get("email")).lower() == normalize_str(requester_email).lower()


def _sanitize_user_settings(raw: Any):
    settings_payload = _default_user_settings()
    if isinstance(raw, dict):
        theme = normalize_str(raw.get("themePreference")).lower()
        if theme in ALLOWED_THEME_PREFERENCES:
            settings_payload["themePreference"] = theme
        profile_picture = normalize_str(raw.get("profilePicture"))
        if profile_picture in ALLOWED_PROFILE_PICTURES:
            settings_payload["profilePicture"] = profile_picture

    return settings_payload


def _get_settings_for_user(user_record: dict[str, Any]):
    current = _sanitize_user_settings(user_record.get("settings"))
    existing = users.find_one({"id": user_record["id"]})
    if existing:
        users.update_one(
            {"id": user_record["id"]},
            {
                "$set": {
                    "settings": current,
                }
            },
        )
    else:
        created_at = datetime.now(timezone.utc).isoformat()
        users.insert_one(
            {
                "id": user_record["id"],
                "first_name": normalize_str(user_record.get("first_name")),
                "last_name": normalize_str(user_record.get("last_name")),
                "email": normalize_str(user_record.get("email")).lower(),
                "is_admin": bool(user_record.get("is_admin")),
                "is_active": _is_user_active(user_record),
                "created_at": user_record.get("created_at") or created_at,
                "settings": current,
            }
        )
    return current


def _upsert_settings_for_user(user_record: dict[str, Any], settings_payload: dict[str, Any]):
    existing = users.find_one({"id": user_record["id"]})
    if existing:
        users.update_one(
            {"id": user_record["id"]},
            {
                "$set": {
                    "settings": settings_payload,
                }
            },
        )
    else:
        created_at = datetime.now(timezone.utc).isoformat()
        users.insert_one(
            {
                "id": user_record["id"],
                "first_name": normalize_str(user_record.get("first_name")),
                "last_name": normalize_str(user_record.get("last_name")),
                "email": normalize_str(user_record.get("email")).lower(),
                "is_admin": bool(user_record.get("is_admin")),
                "is_active": _is_user_active(user_record),
                "created_at": user_record.get("created_at") or created_at,
                "settings": settings_payload,
            }
        )


def seed_database(payload: dict[str, Any]) -> dict[str, int]:
	return seed_data_database(collections, payload)


def _route_deps() -> dict[str, Any]:
    return {
        "settings": settings,
        "users": users,
        "whitelist_users": whitelist_users,
        "courses": courses,
        "api_keys": api_keys,
        "api_history": api_history,
        "telemetry_interactions": telemetry_interactions,
        "telemetry_current": telemetry_current,
        "telemetry_hardware": telemetry_hardware,
        "is_valid_email": is_valid_email,
        "logger": logger,
        "require_admin": require_admin,
        "require_internal_proxy": require_internal_proxy,
        "require_requester_identity": require_requester_identity,
        "normalize_str": normalize_str,
        "_bad_request": _bad_request,
        "_get_collection_snapshot": _get_collection_snapshot,
        "_resolve_user_record": _resolve_user_record,
        "_resolve_requester_user_id": _resolve_requester_user_id,
        "_serialize_user": _serialize_user,
        "_serialize_whitelist_user": _serialize_whitelist_user,
        "_user_role": _user_role,
        "_is_user_active": _is_user_active,
        "_default_user_settings": _default_user_settings,
        "_normalize_oauth_payload": _normalize_oauth_payload,
        "_is_kent_email": _is_kent_email,
        "_can_access_user_record": _can_access_user_record,
        "_get_settings_for_user": _get_settings_for_user,
        "_sanitize_user_settings": _sanitize_user_settings,
        "_upsert_settings_for_user": _upsert_settings_for_user,
        "_serialize_value": _serialize_value,
        "_attach_course_key_state": _attach_course_key_state,
        "record_audit_event": audit_handlers.record_audit_event,
        "set_user_api_keys_active_state": user_handlers.set_user_api_keys_active_state,
        "validate_user_payload": validate_user_payload,
        "validate_course_payload": validate_course_payload,
        "filter_visible_courses": filter_visible_courses,
        "get_course_record": get_course_record,
        "apply_course_metadata_patch": apply_course_metadata_patch,
        "can_manage_metadata": can_manage_metadata,
        "can_manage_people": can_manage_people,
        "can_request_api_key": can_request_api_key,
        "can_manage_api_keys": can_manage_api_keys,
        "add_course_members": add_course_members,
        "remove_course_member": remove_course_member,
        "create_course_group": create_course_group,
        "add_group_member": add_group_member,
        "remove_group_member": remove_group_member,
        "update_course_member_key_limit": update_course_member_key_limit,
        "update_course_instructor_key_limit": update_course_instructor_key_limit,
        "update_course_instructor_handout_limit": update_course_instructor_handout_limit,
        "update_course_group_key_limit": update_course_group_key_limit,
        "delete_course_api_keys": delete_course_api_keys,
        "regenerate_course_api_key": regenerate_course_api_key,
        "resolve_course_key_owner": resolve_course_key_owner,
        "reconcile_course_members_for_user": reconcile_course_members_for_user,
        "set_course_active_state": set_course_active_state,
        "set_course_api_key_active_state": set_course_api_key_active_state,
        "_get_owner_key_limit": _get_owner_key_limit,
        "_iter_course_api_keys": _iter_course_api_keys,
        "_serialize_api_key_summary": _serialize_api_key_summary,
        "_parse_iso_datetime": _parse_iso_datetime,
        "API_KEY_REGENERATION_COOLDOWN": API_KEY_REGENERATION_COOLDOWN,
        "ALLOWED_THEME_PREFERENCES": ALLOWED_THEME_PREFERENCES,
        "ALLOWED_PROFILE_PICTURES": ALLOWED_PROFILE_PICTURES,
    }


@app.route("/health", methods=["GET"])
def health_check():
    return content_handlers.health_check(_route_deps())


@app.route("/", methods=["GET"])
def index_page():
    return content_handlers.index_page(_route_deps())


@app.route("/auth/preview-users", methods=["GET"])
def get_preview_users():
    return auth_handlers.get_preview_users(_route_deps())


@app.route("/auth/session-user", methods=["GET"])
def get_session_user():
    return auth_handlers.get_session_user(_route_deps())


@app.route("/auth/microsoft/login", methods=["POST"])
def microsoft_login():
    return auth_handlers.microsoft_login(_route_deps())


@app.route("/auth/microsoft/whitelist", methods=["GET"])
def get_oauth_whitelist():
    return auth_handlers.get_oauth_whitelist(_route_deps())


@app.route("/auth/microsoft/whitelist", methods=["POST"])
def add_oauth_whitelist_entry():
    return auth_handlers.add_oauth_whitelist_entry(_route_deps())


@app.route("/auth/microsoft/whitelist/<entry_id>", methods=["PATCH", "DELETE"])
def update_or_delete_oauth_whitelist_entry(entry_id):
    return auth_handlers.update_or_delete_oauth_whitelist_entry(_route_deps(), entry_id)


@app.route("/users", methods=["POST"])
def create_user():
    return user_handlers.create_user(_route_deps())


@app.route("/users", methods=["GET"])
def get_users():
    return user_handlers.get_users(_route_deps())


@app.route("/users/bulk-status", methods=["PATCH"])
def bulk_update_users():
    return user_handlers.bulk_update_users(_route_deps())


@app.route("/audit-logs", methods=["GET"])
def get_audit_logs():
    return audit_handlers.get_audit_logs(_route_deps())


@app.route("/audit/export", methods=["GET"])
def export_audit_logs():
    return audit_handlers.get_audit_export(_route_deps())


@app.route("/users/<user_id>", methods=["GET"])
def get_user(user_id):
    return user_handlers.get_user(_route_deps(), user_id)


@app.route("/users/<user_id>", methods=["PUT"])
def update_user(user_id):
    return user_handlers.update_user(_route_deps(), user_id)


@app.route("/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):
    return user_handlers.delete_user(_route_deps(), user_id)


@app.route("/courses", methods=["POST"])
def create_course():
    return course_handlers.create_course(_route_deps())


@app.route("/courses", methods=["GET"])
def get_courses():
    return course_handlers.get_courses(_route_deps())


@app.route("/courses/<course_id>", methods=["GET"])
def get_course(course_id):
    return course_handlers.get_course(_route_deps(), course_id)


@app.route("/courses/<course_id>/metadata", methods=["PATCH"])
def patch_course_metadata(course_id):
    return course_handlers.patch_course_metadata(_route_deps(), course_id)


@app.route("/courses/<course_id>/status", methods=["PATCH"])
def update_course_status_route(course_id):
    return course_handlers.update_course_status_route(_route_deps(), course_id)


@app.route("/courses/<course_id>", methods=["DELETE"])
def delete_course(course_id):
    return course_handlers.delete_course(_route_deps(), course_id)


@app.route("/courses/<course_id>/members", methods=["POST"])
def add_course_members_route(course_id):
    return course_handlers.add_course_members_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/members", methods=["DELETE"])
def remove_course_member_route(course_id):
    return course_handlers.remove_course_member_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/groups", methods=["POST"])
def create_course_group_route(course_id):
    return course_handlers.create_course_group_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/groups/<group_id>/members", methods=["POST"])
def add_group_member_route(course_id, group_id):
    return course_handlers.add_group_member_route(_route_deps(), course_id, group_id)


@app.route("/courses/<course_id>/groups/<group_id>/members", methods=["DELETE"])
def remove_group_member_route(course_id, group_id):
    return course_handlers.remove_group_member_route(_route_deps(), course_id, group_id)


@app.route("/courses/<course_id>/members/<member_id>/key-limit", methods=["PATCH"])
def update_member_key_limit_route(course_id, member_id):
    return course_handlers.update_member_key_limit_route(_route_deps(), course_id, member_id)


@app.route("/courses/<course_id>/instructor-handout-limit", methods=["PATCH"])
def update_instructor_handout_limit_route(course_id):
    return course_handlers.update_instructor_handout_limit_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/instructor-key-limit", methods=["PATCH"])
def update_instructor_key_limit_route(course_id):
    return course_handlers.update_instructor_key_limit_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/groups/<group_id>/key-limit", methods=["PATCH"])
def update_group_key_limit_route(course_id, group_id):
    return course_handlers.update_group_key_limit_route(_route_deps(), course_id, group_id)


@app.route("/courses/<course_id>/api-keys", methods=["GET"])
def list_course_api_keys_route(course_id):
    return course_handlers.list_course_api_keys_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/api-key/regenerate", methods=["POST"])
def regenerate_course_api_key_route(course_id):
    return course_handlers.regenerate_course_api_key_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/api-key", methods=["DELETE"])
def delete_course_api_key_route(course_id):
    return course_handlers.delete_course_api_key_route(_route_deps(), course_id)


@app.route("/courses/<course_id>/api-key/status", methods=["PATCH"])
def update_course_api_key_status_route(course_id):
    return course_handlers.update_course_api_key_status_route(_route_deps(), course_id)


@app.route("/user-settings", methods=["GET"])
def get_user_settings():
    return settings_handlers.get_user_settings(_route_deps())


@app.route("/user-settings/<setting_key>", methods=["PATCH"])
def patch_user_setting(setting_key):
    return settings_handlers.patch_user_setting(_route_deps(), setting_key)


@app.route("/courses/<course_id>/api-history", methods=["GET"])
def get_course_api_history(course_id):
    return course_handlers.get_course_api_history(_route_deps(), course_id)


@app.route("/analytics/summary", methods=["GET"])
def get_analytics_summary():
    return content_handlers.get_analytics_summary(_route_deps())


@app.route("/analytics/current", methods=["GET"])
def get_analytics_current():
    return content_handlers.get_analytics_current(_route_deps())


@app.route("/analytics/my-usage", methods=["GET"])
def get_my_usage():
    return content_handlers.get_my_usage(_route_deps())


@app.route("/analytics/timeseries", methods=["GET"])
def get_analytics_timeseries():
    return content_handlers.get_analytics_timeseries(_route_deps())


@app.route("/analytics/hardware", methods=["GET"])
def get_analytics_hardware():
    return content_handlers.get_analytics_hardware(_route_deps())


@app.route("/analytics/breakdown", methods=["GET"])
def get_analytics_breakdown():
    return content_handlers.get_analytics_breakdown(_route_deps())


@app.route("/analytics/requests", methods=["GET"])
def get_analytics_requests():
    return content_handlers.get_analytics_requests(_route_deps())


@app.route("/analytics/export", methods=["GET"])
def export_analytics_requests():
    return content_handlers.get_analytics_export(_route_deps())


@app.route("/analytics/requests/<request_id>", methods=["GET"])
def get_analytics_request(request_id):
    return content_handlers.get_analytics_request(_route_deps(), request_id)


@app.route("/analytics/requests/<request_id>/review", methods=["PATCH"])
def patch_analytics_request_review(request_id):
    return content_handlers.patch_analytics_request_review(
        _route_deps(), request_id
    )


if __name__ == "__main__":
    app.run(
        debug=settings.debug,
        host=settings.host,
        port=settings.port,
        use_reloader=False,
    )
