from __future__ import annotations

from datetime import datetime, timezone
from html import escape as html_escape
from typing import Any

from flask import jsonify, render_template, request

from backend.telemetry_analytics import (
    AnalyticsQueryError,
    ANALYTICS_ROW_PROJECTION,
    BREAKDOWN_DIMENSIONS,
    MAX_BREAKDOWN_ROWS,
    MAX_REQUEST_ROWS,
    OUTCOMES,
    bounded_int,
    breakdown,
    current_snapshot,
    documents_in_range,
    recent_requests,
    request_detail,
    open_interaction_counts,
    resolve_bucket,
    summary,
    timeseries,
    window_range,
)
from backend.telemetry_review import (
    REVIEW_STATUSES,
    ReviewValidationError,
    normalize_existing_review,
    validate_review_patch,
)
from backend.telemetry_hardware import (
    hardware_documents_in_range,
    hardware_history,
)


def _redact_inspector_value(value: Any):
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key == "html" or normalized_key.endswith("_html"):
                continue
            redacted[key] = _redact_inspector_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_inspector_value(item) for item in value]
    if isinstance(value, str):
        return html_escape(value)
    return value


def health_check(deps: dict[str, Any]):
    settings = deps["settings"]
    return jsonify({"ok": True, "env": settings.app_env})


def index_page(deps: dict[str, Any]):
    settings = deps["settings"]
    _get_collection_snapshot = deps["_get_collection_snapshot"]
    users = deps["users"]
    whitelist_users = deps["whitelist_users"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    api_history = deps["api_history"]

    if settings.app_env == "production" and not settings.enable_db_inspector:
        return jsonify({"error": "Not found"}), 404

    collections_snapshot = {
        "users": {
            "docs": _redact_inspector_value(_get_collection_snapshot(users)),
            "description": "Canonical user records; each user document owns its settings.",
        },
        "whitelist_users": {
            "docs": _redact_inspector_value(_get_collection_snapshot(whitelist_users)),
            "description": "Approved non-@kent.edu addresses for Microsoft OAuth login.",
        },
        "courses": {
            "docs": _redact_inspector_value(_get_collection_snapshot(courses)),
            "description": "Course records and memberships.",
        },
        "api_keys": {
            "docs": _redact_inspector_value(_get_collection_snapshot(api_keys)),
            "description": "Issued API keys.",
        },
        "api_history": {
            "docs": _redact_inspector_value(_get_collection_snapshot(api_history)),
            "description": "Per-course API request history.",
        },
    }
    return render_template(
        "index.html",
        generated_at=datetime.now(timezone.utc).isoformat(),
        collections=collections_snapshot,
    )


def _require_analytics_admin(deps: dict[str, Any]):
    ok, _ = deps["require_admin"]()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403
    return None


def _analytics_rows(deps: dict[str, Any]):
    window, start, end = window_range(request.args.get("window"))
    rows = documents_in_range(
        deps["telemetry_interactions"],
        start,
        end,
        ANALYTICS_ROW_PROJECTION,
    )
    return rows, window, start, end


def _analytics_error(error: AnalyticsQueryError):
    return jsonify({"error": str(error)}), 400


def _analytics_failure(deps: dict[str, Any], error: Exception):
    deps["logger"].error(
        "analytics.query_failed error_type=%s", type(error).__name__
    )
    return jsonify({"error": "Analytics are temporarily unavailable."}), 503


def get_analytics_summary(deps: dict[str, Any]):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        rows, window, start, end = _analytics_rows(deps)
        return jsonify(summary(rows, window, start, end))
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)


def get_analytics_current(deps: dict[str, Any]):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        document = deps["telemetry_current"].find_one({"_id": "rocky:model-runtime"})
        generated_at = datetime.now(timezone.utc)
        open_counts = open_interaction_counts(
            deps["telemetry_interactions"], generated_at
        )
        return jsonify(current_snapshot(document, generated_at, open_counts))
    except Exception as error:
        return _analytics_failure(deps, error)


def get_analytics_timeseries(deps: dict[str, Any]):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        rows, window, start, end = _analytics_rows(deps)
        bucket, _ = resolve_bucket(
            window, start, end, request.args.get("bucket")
        )
        return jsonify(timeseries(rows, window, start, end, bucket))
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)


def get_analytics_hardware(deps: dict[str, Any]):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        rows, window, start, end = _analytics_rows(deps)
        bucket, _ = resolve_bucket(
            window, start, end, request.args.get("bucket")
        )
        hardware_rows = hardware_documents_in_range(
            deps["telemetry_hardware"], start, end
        )
        return jsonify(hardware_history(
            hardware_rows,
            rows,
            window,
            start,
            end,
            bucket,
            deps["settings"].hardware_sample_interval_seconds,
        ))
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)


def get_analytics_breakdown(deps: dict[str, Any]):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        dimension = (request.args.get("dimension") or "user").strip().lower()
        if dimension not in BREAKDOWN_DIMENSIONS:
            raise AnalyticsQueryError(
                "Unsupported dimension. Choose one of: "
                f"{', '.join(sorted(BREAKDOWN_DIMENSIONS))}."
            )
        limit = bounded_int(request.args.get("limit"), 25, MAX_BREAKDOWN_ROWS)
        rows, window, start, end = _analytics_rows(deps)
        return jsonify(breakdown(
            rows, window, start, end, dimension, limit
        ))
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)


def _optional_bool(value: str | None):
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise AnalyticsQueryError("flagged must be true or false.")


def get_analytics_requests(deps: dict[str, Any]):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        limit = bounded_int(request.args.get("limit"), 50, MAX_REQUEST_ROWS)
        requested_outcome = (request.args.get("outcome") or "").strip().lower() or None
        if requested_outcome not in (*OUTCOMES, "active", None):
            raise AnalyticsQueryError(
                "outcome must be active, completed, rejected, failed, or timed_out."
            )
        review_status = (request.args.get("review_status") or "").strip().lower() or None
        if review_status not in (*REVIEW_STATUSES, None):
            raise AnalyticsQueryError(
                "review_status must be unreviewed, in_review, or resolved."
            )
        rows, window, start, end = _analytics_rows(deps)
        return jsonify(recent_requests(
            rows,
            window,
            start,
            end,
            limit,
            requested_outcome=requested_outcome,
            user_id=(request.args.get("user_id") or "").strip() or None,
            course_id=(request.args.get("course_id") or "").strip() or None,
            flagged=_optional_bool(request.args.get("flagged")),
            review_status=review_status,
        ))
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)


def get_analytics_request(deps: dict[str, Any], request_id: str):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    if not request_id or len(request_id) > 256:
        return jsonify({"error": "Invalid request ID."}), 400
    try:
        detail = request_detail(deps["telemetry_interactions"], request_id)
    except Exception as error:
        return _analytics_failure(deps, error)
    if detail is None:
        return jsonify({"error": "Telemetry request not found."}), 404
    return jsonify(detail)


def patch_analytics_request_review(deps: dict[str, Any], request_id: str):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    if not request_id or len(request_id) > 256:
        return jsonify({"error": "Invalid request ID."}), 400

    identity = deps["require_requester_identity"]()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, _ = identity
    reviewer_id = deps["_resolve_requester_user_id"](email)
    interactions = deps["telemetry_interactions"]
    try:
        row = interactions.find_one({"request_id": request_id})
        if row is None:
            row = interactions.find_one({"_id": request_id})
    except Exception as error:
        return _analytics_failure(deps, error)
    if row is None:
        return jsonify({"error": "Telemetry request not found."}), 404

    previous = normalize_existing_review(row.get("review"))
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    expected_version = payload.get("version")
    if not isinstance(expected_version, int) or expected_version < 0:
        return jsonify({"error": "Review version must be a nonnegative integer."}), 400
    if expected_version != previous["version"]:
        return jsonify({
            "error": "This review was changed by another administrator. Reload it before saving.",
            "current_review": previous,
        }), 409
    try:
        updated = validate_review_patch(
            {key: value for key, value in payload.items() if key != "version"},
            previous,
            {"user_id": reviewer_id, "email": email},
        )
    except ReviewValidationError as error:
        return jsonify({"error": str(error)}), 400

    updated["version"] = expected_version + 1
    history_entry = {
        "reviewed_at": updated["reviewed_at"],
        "reviewed_by": updated["reviewed_by"],
        "previous": {
            "version": previous["version"],
            "flagged": previous["flagged"],
            "flag_reasons": previous["flag_reasons"],
            "status": previous["status"],
            "notes": previous["notes"],
        },
        "updated": {
            "version": updated["version"],
            "flagged": updated["flagged"],
            "flag_reasons": updated["flag_reasons"],
            "status": updated["status"],
            "notes": updated["notes"],
        },
    }
    try:
        review_filter = {"_id": row["_id"]}
        if isinstance(row.get("review"), dict) and "version" in row["review"]:
            review_filter["review.version"] = expected_version
        else:
            review_filter["review.version"] = {"$exists": False}
        result = interactions.update_one(
            review_filter,
            {"$set": {"review": updated}, "$push": {"review_history": history_entry}},
        )
        if getattr(result, "matched_count", 0) != 1:
            current = interactions.find_one({"_id": row["_id"]})
            if current is None:
                return jsonify({"error": "Telemetry request not found."}), 404
            return jsonify({
                "error": "This review was changed by another administrator. Reload it before saving.",
                "current_review": normalize_existing_review(current.get("review")),
            }), 409
    except Exception as error:
        return _analytics_failure(deps, error)

    try:
        course = row.get("course") if isinstance(row.get("course"), dict) else {}
        deps["api_history"].insert_one({
            "u_id": reviewer_id or email,
            "c_id": course.get("course_code") or "",
            "course_id": course.get("course_id"),
            "group_id": course.get("group_id"),
            "is_group_member": bool(course.get("group_id")),
            "event_type": "telemetry-review",
            "created": updated["reviewed_at"].isoformat(),
            "meta": {
                "path": request.path,
                "request_id": request_id,
                "previous_status": previous["status"],
                "status": updated["status"],
                "previous_flagged": previous["flagged"],
                "flagged": updated["flagged"],
                "flag_reasons": updated["flag_reasons"],
            },
        })
    except Exception as error:
        deps["logger"].error(
            "analytics.review_audit_failed error_type=%s", type(error).__name__
        )

    try:
        detail = request_detail(interactions, request_id)
    except Exception as error:
        return _analytics_failure(deps, error)
    if detail is None:
        return jsonify({"error": "Telemetry request not found."}), 404
    return jsonify(detail)


def get_analytics_kpis(deps: dict[str, Any]):
    """Compatibility response for the current dashboard during Phase 2."""
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        rows, window, start, end = _analytics_rows(deps)
        metrics = summary(rows, window, start, end)
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)

    latency = metrics["latency_ms"]["average"]
    success = metrics["success_rate"]
    return jsonify([
        {
            "label": f"Total Requests ({window})",
            "value": f'{metrics["requests"]:,}',
            "delta": f'{metrics["rates"]["average_requests_per_minute"]:,} avg RPM',
        },
        {
            "label": "Average Response Time",
            "value": f"{latency:,.0f} ms" if latency is not None else "N/A",
            "delta": f'{metrics["latency_ms"]["samples"]:,} samples',
        },
        {
            "label": "Model Success Rate",
            "value": f"{success * 100:.1f}%" if success is not None else "N/A",
            "delta": "Completed inference attempts",
        },
        {
            "label": f"Total Tokens ({window})",
            "value": f'{metrics["usage"]["total_tokens"]:,}',
            "delta": f'{metrics["rates"]["average_tokens_per_minute"]:,} avg TPM',
        },
    ])


def get_analytics_activity(deps: dict[str, Any]):
    """Compatibility response for the current dashboard during Phase 2."""
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    try:
        rows, window, start, end = _analytics_rows(deps)
        bucket, _ = resolve_bucket(
            window, start, end, request.args.get("bucket")
        )
        result = timeseries(rows, window, start, end, bucket)
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)

    activity = []
    for item in result["buckets"]:
        success = item["success_rate"]
        activity.append({
            "window": f'{item["start"]} – {item["end"]}',
            "requests": item["requests"],
            "flagged": item["flagged"],
            "successRate": f"{success * 100:.1f}%" if success is not None else "N/A",
        })
    return jsonify(activity)


def get_default_widgets(deps: dict[str, Any]):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    _resolve_user_record = deps["_resolve_user_record"]
    _can_access_user_record = deps["_can_access_user_record"]
    _get_settings_for_user = deps["_get_settings_for_user"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401

    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)
    user_record = _resolve_user_record(requester_id, email)
    if not user_record:
        return jsonify({"error": "User not found"}), 404

    if not _can_access_user_record(email, is_admin, user_record):
        return jsonify({"error": "You may only access your own settings."}), 403

    settings_payload = _get_settings_for_user(user_record)
    return jsonify(settings_payload.get("widgets", []))


def get_help_faq(deps: dict[str, Any]):
    _get_collection_snapshot = deps["_get_collection_snapshot"]
    help_faq = deps["help_faq"]
    return jsonify(_get_collection_snapshot(help_faq))
