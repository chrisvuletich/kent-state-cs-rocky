from __future__ import annotations

from typing import Any

from flask import jsonify, request


def get_audit_logs(deps: dict[str, Any]):
    require_admin = deps["require_admin"]
    api_history = deps["api_history"]
    users = deps["users"]
    whitelist_users = deps["whitelist_users"]
    normalize_str = deps["normalize_str"]
    _serialize_value = deps["_serialize_value"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    search = normalize_str(request.args.get("search")).lower()
    role = normalize_str(request.args.get("role")).lower()
    course = normalize_str(request.args.get("course")).lower()
    action = normalize_str(request.args.get("action")).lower()
    date_from = normalize_str(request.args.get("date_from"))
    date_to = normalize_str(request.args.get("date_to"))
    people = list(users.find()) + list(whitelist_users.find())
    people_by_email = {normalize_str(person.get("email")).lower(): person for person in people}

    rows = []
    for record in api_history.find():
        row = _serialize_value(record)
        email = normalize_str(row.get("u_id")).lower()
        person = people_by_email.get(email, {})
        display_name = " ".join(filter(None, [normalize_str(person.get("first_name")), normalize_str(person.get("last_name"))])).strip()
        row["user_email"] = email
        row["user_name"] = display_name or email or "Unknown user"
        stored_role = normalize_str(person.get("role")).lower()
        row["user_role"] = stored_role if stored_role in {"student", "instructor", "admin"} else ("admin" if person.get("is_admin") else "student")
        haystack = " ".join([row["user_name"], email, normalize_str(row.get("c_id")), normalize_str(row.get("event_type"))]).lower()
        created = normalize_str(row.get("created"))
        if search and search not in haystack:
            continue
        if role and row["user_role"] != role:
            continue
        if course and course not in normalize_str(row.get("c_id")).lower():
            continue
        if action and action not in normalize_str(row.get("event_type")).lower():
            continue
        if date_from and created[:10] < date_from:
            continue
        if date_to and created[:10] > date_to:
            continue
        rows.append(row)

    rows.sort(key=lambda item: normalize_str(item.get("created")), reverse=True)
    return jsonify(rows)
