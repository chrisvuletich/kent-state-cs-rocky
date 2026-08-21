from __future__ import annotations

from typing import Any

from flask import jsonify, request


def get_user_settings(deps: dict[str, Any]):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_user_record = deps["_resolve_user_record"]
    _can_access_user_record = deps["_can_access_user_record"]
    _get_settings_for_user = deps["_get_settings_for_user"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401

    email, is_admin = identity
    user_record = _resolve_user_record(request.args.get("userId"), request.args.get("email") or email)
    if not user_record:
        return jsonify({"error": "User not found"}), 404
    if not _can_access_user_record(email, is_admin, user_record):
        return jsonify({"error": "You may only access your own settings."}), 403

    settings_payload = _get_settings_for_user(user_record)
    return jsonify({"settings": settings_payload})


def patch_user_setting(deps: dict[str, Any], setting_key: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_user_record = deps["_resolve_user_record"]
    _can_access_user_record = deps["_can_access_user_record"]
    _sanitize_user_settings = deps["_sanitize_user_settings"]
    _upsert_settings_for_user = deps["_upsert_settings_for_user"]
    _bad_request = deps["_bad_request"]
    normalize_str = deps["normalize_str"]
    ALLOWED_THEME_PREFERENCES = deps["ALLOWED_THEME_PREFERENCES"]
    ALLOWED_PROFILE_PICTURES = deps["ALLOWED_PROFILE_PICTURES"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401

    email, is_admin = identity
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    user_record = _resolve_user_record(data.get("userId"), data.get("email") or email)
    if not user_record:
        return jsonify({"error": "User not found"}), 404
    if not _can_access_user_record(email, is_admin, user_record):
        return jsonify({"error": "You may only access your own settings."}), 403

    current = _sanitize_user_settings(user_record.get("settings"))
    if setting_key == "themePreference":
        value = normalize_str(data.get("value")).lower()
        if value not in ALLOWED_THEME_PREFERENCES:
            allowed = ", ".join(sorted(ALLOWED_THEME_PREFERENCES))
            return _bad_request(f"themePreference must be one of: {allowed}.")
        current["themePreference"] = value
    elif setting_key == "profilePicture":
        value = normalize_str(data.get("value"))
        if value not in ALLOWED_PROFILE_PICTURES:
            allowed = ", ".join(sorted(ALLOWED_PROFILE_PICTURES))
            return _bad_request(f"profilePicture must be one of: {allowed}.")
        current["profilePicture"] = value
    else:
        return _bad_request(f"Unsupported user setting key: {setting_key}.")

    _upsert_settings_for_user(user_record, current)
    return jsonify({"settings": current})
