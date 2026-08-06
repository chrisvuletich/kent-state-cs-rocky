from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request


def create_user(deps: dict[str, Any]):
    require_admin = deps["require_admin"]
    validate_user_payload = deps["validate_user_payload"]
    users = deps["users"]
    _bad_request = deps["_bad_request"]
    _default_user_settings = deps["_default_user_settings"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    cleaned, error = validate_user_payload(request.get_json(silent=True))
    if error:
        return _bad_request(error)

    cleaned["created_at"] = datetime.now(timezone.utc).isoformat()
    cleaned["settings"] = _default_user_settings()
    cleaned["is_active"] = True
    cleaned.pop("id", None)
    inserted_id = users.insert_one(cleaned).inserted_id
    users.update_one({"_id": inserted_id}, {"$set": {"id": str(inserted_id)}})
    return jsonify({"message": "User created"})


def get_users(deps: dict[str, Any]):
    require_admin = deps["require_admin"]
    users = deps["users"]
    _serialize_user = deps["_serialize_user"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    result = [_serialize_user(user) for user in users.find()]
    return jsonify(result)


def bulk_update_users(deps: dict[str, Any]):
    """Apply an activation state to a deliberately selected set of accounts."""
    require_admin = deps["require_admin"]
    require_requester_identity = deps["require_requester_identity"]
    _resolve_user_record = deps["_resolve_user_record"]
    users = deps["users"]
    whitelist_users = deps["whitelist_users"]
    _bad_request = deps["_bad_request"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403
    requester_email, requester_detail = require_requester_identity()
    if requester_email is None:
        return jsonify(requester_detail[0]), requester_detail[1]

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")
    user_ids = data.get("user_ids")
    is_active = data.get("is_active")
    if not isinstance(user_ids, list) or not user_ids or not all(isinstance(value, str) and value.strip() for value in user_ids):
        return _bad_request("user_ids must be a non-empty list of user IDs.")
    if not isinstance(is_active, bool):
        return _bad_request("is_active must be a boolean.")

    resolved_users = []
    missing: list[str] = []
    for user_id in dict.fromkeys(value.strip() for value in user_ids):
        user = _resolve_user_record(user_id, None)
        if user:
            resolved_users.append(user)
        else:
            missing.append(user_id)
    if not is_active and any(
        str(user.get("email") or "").strip().lower() == requester_email for user in resolved_users
    ):
        return jsonify({"error": "Administrators cannot deactivate their own account."}), 409
    updated: list[str] = []
    for user in resolved_users:
        resolved_id = user["id"]
        users.update_one({"id": resolved_id}, {"$set": {"is_active": is_active}})
        whitelist_users.update_one({"id": resolved_id}, {"$set": {"is_active": is_active}})
        updated.append(resolved_id)

    return jsonify({"updated_ids": updated, "missing_ids": missing, "is_active": is_active})


def get_user(deps: dict[str, Any], user_id: str):
    require_admin = deps["require_admin"]
    _resolve_user_record = deps["_resolve_user_record"]
    _serialize_user = deps["_serialize_user"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    user = _resolve_user_record(user_id, None)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(_serialize_user(user))


def update_user(deps: dict[str, Any], user_id: str):
    require_admin = deps["require_admin"]
    require_requester_identity = deps["require_requester_identity"]
    _resolve_user_record = deps["_resolve_user_record"]
    users = deps["users"]
    whitelist_users = deps["whitelist_users"]
    _bad_request = deps["_bad_request"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403
    requester_email, requester_detail = require_requester_identity()
    if requester_email is None:
        return jsonify(requester_detail[0]), requester_detail[1]

    user = _resolve_user_record(user_id, None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return _bad_request("Request body must be a non-empty JSON object.")

    allowed_fields = {"is_active", "is_admin", "role"}
    if not set(data).issubset(allowed_fields):
        return _bad_request("Only is_active, is_admin, and role may be updated through this endpoint.")
    if any(not isinstance(data.get(key), bool) for key in {"is_active", "is_admin"} & set(data)):
        return _bad_request("is_active and is_admin must be booleans.")
    if "role" in data and data["role"] not in {"student", "instructor", "admin"}:
        return _bad_request("role must be one of: student, instructor, admin.")

    is_requester = str(user.get("email") or "").strip().lower() == requester_email
    removes_admin_access = (
        data.get("is_active") is False
        or data.get("is_admin") is False
        or ("role" in data and data["role"] != "admin")
    )
    if is_requester and removes_admin_access:
        return jsonify({"error": "Administrators cannot deactivate or demote their own account."}), 409

    changes = {key: bool(value) for key, value in data.items()}
    if "role" in data:
        changes["role"] = data["role"]
        changes["is_admin"] = data["role"] == "admin"
    elif "is_admin" in data:
        changes["role"] = "admin" if data["is_admin"] else "student"
    users.update_one({"id": user["id"]}, {"$set": changes})
    whitelist_users.update_one({"id": user["id"]}, {"$set": changes})
    return jsonify({"message": "User updated"})


def delete_user(deps: dict[str, Any], user_id: str):
    require_admin = deps["require_admin"]
    _resolve_user_record = deps["_resolve_user_record"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    user = _resolve_user_record(user_id, None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"error": "User deletion is disabled. Use account activation controls."}), 405
