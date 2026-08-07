from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request
from pymongo.errors import DuplicateKeyError

from backend.api_key_generator import generate_api_key_id, generate_hidden_api_key_pair


DEFAULT_USER_API_KEY_NAME = "default"


def _document_id_str(document: dict[str, Any]) -> str:
    raw_id = document.get("_id")
    if raw_id is not None:
        return str(raw_id).strip().lower()
    fallback_id = document.get("id")
    return fallback_id.strip().lower() if isinstance(fallback_id, str) else ""


def _find_default_user_api_key(api_keys, owner_id: str):
    for entry in api_keys.find():
        if not isinstance(entry, dict):
            continue
        if entry.get("course_id") is not None or entry.get("c_id") is not None:
            continue
        key_scope = (entry.get("key_scope") or "").strip().lower()
        if key_scope and key_scope != "user-default":
            continue
        if (entry.get("owner_type") or "person").strip().lower() != "person":
            continue
        if (entry.get("owner_id") or "").strip().lower() != owner_id:
            continue
        if (entry.get("key_name") or "").strip().lower() != DEFAULT_USER_API_KEY_NAME:
            continue
        return entry
    return None


def ensure_default_api_key_for_user(deps: dict[str, Any], user_record: dict[str, Any] | None):
    if not isinstance(user_record, dict):
        return None

    owner_id = _document_id_str(user_record)
    if not owner_id:
        return None

    api_keys = deps["api_keys"]
    existing = _find_default_user_api_key(api_keys, owner_id)
    _, expected_hash = generate_hidden_api_key_pair(owner_id)
    now = datetime.now(timezone.utc).isoformat()

    if isinstance(existing, dict) and existing.get("hash") and existing.get("is_active", True) is not False and not existing.get("deleted_at"):
        existing_key_id = existing.get("key_id") if isinstance(existing.get("key_id"), str) else ""
        if not existing_key_id.strip() or existing.get("hash") != expected_hash:
            updated_existing = dict(existing)
            updated_existing["key_id"] = existing_key_id.strip() or generate_api_key_id()
            updated_existing["hash"] = expected_hash
            updated_existing["updated_at"] = now
            api_keys.replace_one({"_id": existing.get("_id")}, updated_existing)
            return updated_existing
        return existing

    existing_key_id = existing.get("key_id") if isinstance(existing, dict) and isinstance(existing.get("key_id"), str) else ""

    key_doc = {
        "key_id": existing_key_id.strip() or generate_api_key_id(),
        "owner_type": "person",
        "owner_id": owner_id,
        "key_scope": "user-default",
        "key_name": DEFAULT_USER_API_KEY_NAME,
        "slot_index": 0,
        "hash": expected_hash,
        "is_active": True,
        "expire": None,
        "created": existing.get("created") if isinstance(existing, dict) and existing.get("created") else now,
        "updated_at": now,
    }

    if isinstance(existing, dict):
        key_doc["_id"] = existing.get("_id")
        api_keys.replace_one({"_id": existing.get("_id")}, key_doc)
        return key_doc

    try:
        api_keys.insert_one(key_doc)
    except DuplicateKeyError:
        return _find_default_user_api_key(api_keys, owner_id)
    return key_doc


def get_preview_users(deps: dict[str, Any]):
    settings = deps["settings"]
    users = deps["users"]
    whitelist_users = deps["whitelist_users"]
    _serialize_user = deps["_serialize_user"]
    normalize_str = deps["normalize_str"]
    _is_user_active = deps["_is_user_active"]
    _default_user_settings = deps["_default_user_settings"]

    if not settings.enable_preview_login:
        return jsonify({"error": "Not found"}), 404

    result = [_serialize_user(user) for user in users.find()]
    known_emails = {normalize_str(user.get("email")).lower() for user in result if isinstance(user, dict)}
    for entry in whitelist_users.find():
        email = normalize_str(entry.get("email")).lower()
        if not email or email in known_emails:
            continue
        result.append(
            _serialize_user(
                {
                    "id": normalize_str(entry.get("id")),
                    "first_name": normalize_str(entry.get("first_name")),
                    "last_name": normalize_str(entry.get("last_name")),
                    "email": email,
                    "is_admin": bool(entry.get("is_admin")),
                    "is_active": _is_user_active(entry),
                    "settings": entry.get("settings", _default_user_settings()),
                    "created_at": entry.get("created_at"),
                }
            )
        )
    return jsonify(result)


def get_session_user(deps: dict[str, Any]):
    ok, _ = deps["require_internal_proxy"]()
    if not ok:
        return jsonify({"error": "Trusted proxy access is required."}), 403
    normalize_str = deps["normalize_str"]
    is_valid_email = deps["is_valid_email"]
    _bad_request = deps["_bad_request"]
    _resolve_user_record = deps["_resolve_user_record"]
    _serialize_user = deps["_serialize_user"]
    reconcile_course_members_for_user = deps["reconcile_course_members_for_user"]
    courses = deps["courses"]

    email = normalize_str(request.args.get("email")).lower()
    if not is_valid_email(email):
        return _bad_request("A valid email query parameter is required.")

    user_record = _resolve_user_record(None, email)
    if not user_record:
        return jsonify({"error": "User not found"}), 404

    updated_courses = reconcile_course_members_for_user(courses, user_record)
    if updated_courses:
        user_record = _resolve_user_record(None, email) or user_record

    ensure_default_api_key_for_user(deps, user_record)
    return jsonify(_serialize_user(user_record))


def microsoft_login(deps: dict[str, Any]):
    ok, _ = deps["require_internal_proxy"]()
    if not ok:
        return jsonify({"error": "Trusted proxy access is required."}), 403
    settings = deps["settings"]
    _normalize_oauth_payload = deps["_normalize_oauth_payload"]
    _bad_request = deps["_bad_request"]
    _is_kent_email = deps["_is_kent_email"]
    _resolve_user_record = deps["_resolve_user_record"]
    users = deps["users"]
    _default_user_settings = deps["_default_user_settings"]
    _serialize_user = deps["_serialize_user"]
    whitelist_users = deps["whitelist_users"]
    normalize_str = deps["normalize_str"]
    _is_user_active = deps["_is_user_active"]
    logger = deps["logger"]
    reconcile_course_members_for_user = deps["reconcile_course_members_for_user"]
    courses = deps["courses"]

    if not settings.enable_microsoft_oauth:
        return jsonify({"error": "Not found"}), 404

    cleaned, payload_error = _normalize_oauth_payload(request.get_json(silent=True))
    if payload_error:
        logger.warning("[oauth] login denied: invalid payload (%s)", payload_error)
        return _bad_request(payload_error)

    email = cleaned["email"]
    first_name = cleaned["first_name"]
    last_name = cleaned["last_name"]
    if _is_kent_email(email):
        user_record = _resolve_user_record(None, email)

        if not user_record:
            to_insert = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "is_admin": False,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "settings": _default_user_settings(),
            }
            inserted_id = users.insert_one(to_insert).inserted_id
            users.update_one({"_id": inserted_id}, {"$set": {"id": str(inserted_id)}})
            user_record = users.find_one({"_id": inserted_id})
            logger.info("[oauth] login success: created Kent user %s", email)
        else:
            users.update_one(
                {"_id": user_record.get("_id")},
                {
                    "$set": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "id": str(user_record.get("id") or user_record.get("_id") or ""),
                    }
                },
            )
            user_record = users.find_one({"_id": user_record.get("_id")})
            logger.info("[oauth] login success: existing Kent user %s", email)

        reconcile_course_members_for_user(courses, user_record)
        ensure_default_api_key_for_user(deps, user_record)
        return jsonify({"ok": True, "user": _serialize_user(user_record)})

    whitelist_record = whitelist_users.find_one({"email": email})
    if not whitelist_record:
        logger.warning("[oauth] login denied: non-Kent email not whitelisted (%s)", email)
        return jsonify({"error": "This email is not approved for access."}), 403

    user_record = users.find_one({"email": email})
    if not user_record:
        whitelist_is_active = _is_user_active(whitelist_record)
        to_insert = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "is_admin": False,
            "is_active": whitelist_is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "settings": _default_user_settings(),
        }
        inserted_id = users.insert_one(to_insert).inserted_id
        users.update_one({"_id": inserted_id}, {"$set": {"id": str(inserted_id)}})
        user_record = users.find_one({"_id": inserted_id})
        logger.info("[oauth] login success: created whitelisted user %s", email)
    else:
        whitelist_is_active = _is_user_active(whitelist_record)
        users.update_one(
            {"_id": user_record.get("_id")},
            {
                "$set": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "id": str(user_record.get("id") or user_record.get("_id") or ""),
                    "is_active": whitelist_is_active,
                }
            },
        )
        user_record = users.find_one({"_id": user_record.get("_id")})
        logger.info("[oauth] login success: existing whitelisted user %s", email)

    reconcile_course_members_for_user(courses, user_record)
    ensure_default_api_key_for_user(deps, user_record)
    return jsonify({"ok": True, "user": _serialize_user(user_record)})


def get_oauth_whitelist(deps: dict[str, Any]):
    require_admin = deps["require_admin"]
    whitelist_users = deps["whitelist_users"]
    _serialize_whitelist_user = deps["_serialize_whitelist_user"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    result = [_serialize_whitelist_user(entry) for entry in whitelist_users.find()]
    return jsonify(result)


def add_oauth_whitelist_entry(deps: dict[str, Any]):
    require_admin = deps["require_admin"]
    _bad_request = deps["_bad_request"]
    normalize_str = deps["normalize_str"]
    is_valid_email = deps["is_valid_email"]
    _is_kent_email = deps["_is_kent_email"]
    whitelist_users = deps["whitelist_users"]
    require_requester_identity = deps["require_requester_identity"]
    _default_user_settings = deps["_default_user_settings"]
    _serialize_whitelist_user = deps["_serialize_whitelist_user"]
    logger = deps["logger"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _bad_request("Request body must be a JSON object.")

    first_name = normalize_str(payload.get("firstName") or payload.get("first_name"))
    last_name = normalize_str(payload.get("lastName") or payload.get("last_name"))
    email = normalize_str(payload.get("email")).lower()

    if not first_name:
        return _bad_request("firstName is required.")
    if not last_name:
        return _bad_request("lastName is required.")
    if not is_valid_email(email):
        return _bad_request("A valid email is required.")
    if _is_kent_email(email):
        return _bad_request("@kent.edu emails should not be added to the external whitelist.")

    existing = whitelist_users.find_one({"email": email})
    if existing:
        logger.info("[oauth] whitelist unchanged: entry already exists for %s", email)
        return jsonify({"message": "Whitelist entry already exists.", "entry": _serialize_whitelist_user(existing)})

    identity = require_requester_identity()
    requester_email = ""
    if identity[0] is not None:
        requester_email, _ = identity

    created = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "is_admin": False,
        "is_active": True,
        "settings": _default_user_settings(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": requester_email,
    }
    inserted_id = whitelist_users.insert_one(created).inserted_id
    whitelist_users.update_one({"_id": inserted_id}, {"$set": {"id": str(inserted_id)}})
    saved = whitelist_users.find_one({"_id": inserted_id})

    logger.info("[oauth] whitelist add success: %s", email)
    return jsonify({"message": "Whitelist entry added.", "entry": _serialize_whitelist_user(saved)}), 201


def update_or_delete_oauth_whitelist_entry(deps: dict[str, Any], entry_id: str):
    require_admin = deps["require_admin"]
    normalize_str = deps["normalize_str"]
    _bad_request = deps["_bad_request"]
    whitelist_users = deps["whitelist_users"]
    users = deps["users"]
    _serialize_whitelist_user = deps["_serialize_whitelist_user"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    normalized_entry_id = normalize_str(entry_id)
    if not normalized_entry_id:
        return _bad_request("Invalid whitelist entry id.")

    entry = whitelist_users.find_one({"id": normalized_entry_id})
    if not entry:
        entry = whitelist_users.find_one({"_id": normalized_entry_id})
    if not entry:
        return jsonify({"error": "Whitelist entry not found"}), 404

    entry_email = normalize_str(entry.get("email")).lower()

    if request.method == "PATCH":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _bad_request("Request body must be a JSON object.")
        if "is_active" not in payload:
            return _bad_request("is_active is required.")
        if not isinstance(payload.get("is_active"), bool):
            return _bad_request("is_active must be a boolean.")

        is_active = payload.get("is_active")
        whitelist_users.update_one({"_id": entry.get("_id")}, {"$set": {"is_active": is_active}})
        if entry_email:
            users.update_one({"email": entry_email}, {"$set": {"is_active": is_active}})
        updated = whitelist_users.find_one({"_id": entry.get("_id")})
        return jsonify({"message": "Whitelist entry updated.", "entry": _serialize_whitelist_user(updated)})

    whitelist_users.delete_one({"_id": entry.get("_id")})
    if entry_email:
        users.delete_many({"email": entry_email})
    return jsonify({"message": "Whitelist entry removed."})
