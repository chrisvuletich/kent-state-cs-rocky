from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from flask import Response, jsonify, request


ALLOWED_AUDIT_EVENTS = {
    "course-api-key-status-updated",
    "course-api-keys-deleted",
    "course-created",
    "course-deleted",
    "course-group-created",
    "course-group-key-limit-updated",
    "course-group-member-added",
    "course-group-member-removed",
    "course-instructor-handout-limit-updated",
    "course-instructor-key-limit-updated",
    "course-member-key-limit-updated",
    "course-member-removed",
    "course-members-added",
    "course-metadata-updated",
    "course-status-updated",
    "delete-key",
    "generate-key",
    "analytics-export",
    "audit-export",
    "telemetry-purge",
    "telemetry-review",
    "user-bulk-status-updated",
    "user-created",
    "user-updated",
    "whitelist-added",
    "whitelist-removed",
    "whitelist-updated",
}
SENSITIVE_AUDIT_FIELDS = {
    "api_key",
    "apikey",
    "api_key_hash",
    "authorization",
    "cookie",
    "hash",
    "key_hash",
    "password",
    "raw_key",
    "secret",
    "token",
}


def _audit_value(value: Any, depth: int = 0):
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        cleaned = {}
        for key, nested_value in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in SENSITIVE_AUDIT_FIELDS or normalized_key.endswith("_hash") or any(
                marker in normalized_key
                for marker in ("api_key", "authorization", "cookie", "password", "secret", "token")
            ):
                continue
            cleaned[str(key)] = _audit_value(nested_value, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [_audit_value(item, depth + 1) for item in list(value)[:100]]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:1000] if isinstance(value, str) else value
    return str(value)[:1000]


def record_audit_event(
    deps: dict[str, Any],
    event_type: str,
    *,
    course: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: Any = None,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Append a trusted, metadata-only event after a successful mutation."""
    normalized_event = str(event_type).strip().lower()
    if normalized_event not in ALLOWED_AUDIT_EVENTS:
        raise ValueError(f"Unsupported audit event: {normalized_event}")

    identity = deps["require_requester_identity"]()
    if identity[0] is None:
        raise RuntimeError("An authenticated actor is required for audit events.")
    email, _ = identity
    actor_id = deps["_resolve_requester_user_id"](email)
    normalize_str = deps["normalize_str"]
    course_record = course if isinstance(course, dict) else {}
    normalized_target_type = normalize_str(target_type).lower()
    normalized_target_id = normalize_str(str(target_id) if target_id is not None else "").lower()
    group_id = normalized_target_id if normalized_target_type == "group" else ""

    event_metadata = _audit_value(metadata or {})
    event_metadata.update({
        "path": request.path,
        "actor_id": actor_id or email,
        "actor_email": email,
        "target_type": normalized_target_type or None,
        "target_id": normalized_target_id or None,
    })
    if changes:
        event_metadata["changes"] = _audit_value(changes)

    document = {
        "u_id": actor_id or email,
        "c_id": normalize_str(course_record.get("code")),
        "course_id": course_record.get("id"),
        "event_type": normalized_event,
        "group_id": group_id or None,
        "group_name": None,
        "is_group_member": bool(group_id),
        "meta": event_metadata,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    deps["api_history"].insert_one(document)
    return document


def _audit_rows(deps: dict[str, Any]):
    api_history = deps["api_history"]
    users = deps["users"]
    whitelist_users = deps["whitelist_users"]
    normalize_str = deps["normalize_str"]
    _serialize_value = deps["_serialize_value"]

    search = normalize_str(request.args.get("search")).lower()
    role = normalize_str(request.args.get("role")).lower()
    course = normalize_str(request.args.get("course")).lower()
    action = normalize_str(request.args.get("action")).lower()
    date_from = normalize_str(request.args.get("date_from"))
    date_to = normalize_str(request.args.get("date_to"))
    people = list(users.find()) + list(whitelist_users.find())
    people_by_identifier: dict[str, dict[str, Any]] = {}
    for person in people:
        for identifier in (person.get("email"), person.get("id"), person.get("_id")):
            normalized_identifier = normalize_str(identifier).lower()
            if normalized_identifier:
                people_by_identifier[normalized_identifier] = person

    rows = []
    for record in api_history.find():
        row = _serialize_value(record)
        user_identifier = normalize_str(row.get("u_id")).lower()
        person = people_by_identifier.get(user_identifier, {})
        display_name = " ".join(filter(None, [normalize_str(person.get("first_name")), normalize_str(person.get("last_name"))])).strip()
        row["user_email"] = normalize_str(person.get("email")).lower() or user_identifier
        row["user_name"] = display_name or row["user_email"] or "Unknown user"
        stored_role = normalize_str(person.get("role")).lower()
        row["user_role"] = stored_role if stored_role in {"student", "instructor", "admin"} else ("admin" if person.get("is_admin") else "student")
        haystack = " ".join([row["user_name"], row["user_email"], normalize_str(row.get("c_id")), normalize_str(row.get("event_type"))]).lower()
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
    return rows


def get_audit_logs(deps: dict[str, Any]):
    ok, _ = deps["require_admin"]()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403
    rows = _audit_rows(deps)
    return jsonify(rows)


AUDIT_EXPORT_LIMIT = 10_000
AUDIT_EXPORT_COLUMNS = (
    "created",
    "event_type",
    "user_name",
    "user_email",
    "user_role",
    "course_id",
    "c_id",
    "group_id",
    "meta",
)


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value)
    return f"'{rendered}" if rendered.startswith(("=", "+", "-", "@")) else rendered


def get_audit_export(deps: dict[str, Any]):
    ok, _ = deps["require_admin"]()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403
    export_format = (request.args.get("format") or "csv").strip().lower()
    if export_format not in {"json", "csv"}:
        return jsonify({"error": "format must be json or csv."}), 400
    raw_limit = (request.args.get("limit") or str(AUDIT_EXPORT_LIMIT)).strip()
    try:
        limit = int(raw_limit)
    except ValueError:
        return jsonify({"error": "limit must be an integer."}), 400
    if limit < 1 or limit > AUDIT_EXPORT_LIMIT:
        return jsonify({"error": f"limit must be between 1 and {AUDIT_EXPORT_LIMIT}."}), 400

    rows = _audit_rows(deps)
    if len(rows) > limit:
        return jsonify({
            "error": (
                f"This export contains {len(rows):,} rows, which exceeds the {limit:,}-row limit. "
                "Choose a shorter date range or add filters."
            )
        }), 413
    try:
        record_audit_event(
            deps,
            "audit-export",
            target_type="audit-log",
            target_id="filtered",
            metadata={"format": export_format, "row_count": len(rows)},
        )
    except Exception as error:
        deps["logger"].error("audit.export_audit_failed error_type=%s", type(error).__name__)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"rocky-audit-{stamp}.{export_format}"
    if export_format == "json":
        return Response(
            json.dumps({
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "count": len(rows),
                "records": rows,
            }, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=AUDIT_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({key: _csv_safe(value) for key, value in row.items()} for row in rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
