from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from html import escape as html_escape
from typing import Any

from flask import Response, jsonify, render_template, request

from backend.telemetry_analytics import (
    AnalyticsQueryError,
    ANALYTICS_ROW_PROJECTION,
    BREAKDOWN_DIMENSIONS,
    MAX_BREAKDOWN_ROWS,
    MAX_REQUEST_ROWS,
    OPERATIONS,
    OUTCOMES,
    bounded_int,
    breakdown,
    current_snapshot,
    documents_in_range,
    filter_requests,
    recent_requests,
    request_detail,
    open_interaction_counts,
    outcome,
    received_at,
    resolve_bucket,
    summary,
    timeseries,
    user_usage_summary,
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
            "description": "Administrative and course audit events.",
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
    return _analytics_rows_with_projection(deps, ANALYTICS_ROW_PROJECTION)


def _bounded_filter(name: str, maximum: int = 256) -> str | None:
    value = (request.args.get(name) or "").strip()
    if len(value) > maximum:
        raise AnalyticsQueryError(f"{name} must contain at most {maximum} characters.")
    return value or None


def _analytics_filter_values() -> dict[str, Any]:
    operation = (_bounded_filter("operation", 64) or "").lower() or None
    if operation and operation not in OPERATIONS:
        raise AnalyticsQueryError(
            "operation must be models.list, responses.create, or unknown."
        )
    requested_outcome = (_bounded_filter("outcome", 32) or "").lower() or None
    if requested_outcome not in (*OUTCOMES, "active", None):
        raise AnalyticsQueryError(
            "outcome must be active, completed, rejected, failed, or timed_out."
        )
    review_status = (_bounded_filter("review_status", 32) or "").lower() or None
    if review_status not in (*REVIEW_STATUSES, None):
        raise AnalyticsQueryError(
            "review_status must be unreviewed, in_review, or resolved."
        )
    return {
        "requested_outcome": requested_outcome,
        "user_id": _bounded_filter("user_id"),
        "course_id": _bounded_filter("course_id"),
        "key_id": _bounded_filter("key_id"),
        "model": _bounded_filter("model"),
        "source": _bounded_filter("source", 128),
        "operation": operation,
        "flagged": _optional_bool(request.args.get("flagged")),
        "review_status": review_status,
    }


def _analytics_rows_with_projection(
    deps: dict[str, Any], projection: dict[str, int] | None
):
    window, start, end = window_range(request.args.get("window"))
    rows = documents_in_range(
        deps["telemetry_interactions"],
        start,
        end,
        projection,
    )
    rows = filter_requests(rows, **_analytics_filter_values())
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


def get_my_usage(deps: dict[str, Any]):
    identity = deps["require_requester_identity"]()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, _ = identity
    user_id = deps["_resolve_requester_user_id"](email)
    try:
        return jsonify(user_usage_summary(
            deps["telemetry_interactions"],
            [identifier for identifier in (user_id, email) if identifier],
        ))
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
        rows, window, start, end = _analytics_rows(deps)
        return jsonify(recent_requests(
            rows,
            window,
            start,
            end,
            limit,
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


MAX_EXPORT_ROWS = 10_000
EXPORT_FORMATS = {"json", "csv"}
EXPORT_COLUMNS = (
    "request_id",
    "received_at",
    "terminal_at",
    "user_id",
    "user_email",
    "user_name",
    "course_id",
    "course_code",
    "key_id",
    "key_name",
    "source",
    "operation",
    "public_model",
    "actual_model",
    "outcome",
    "http_status",
    "request_latency_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt",
    "response",
    "error_stage",
    "error_type",
)


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value)
    return f"'{rendered}" if rendered.startswith(("=", "+", "-", "@")) else rendered


def _export_row(row: dict[str, Any]) -> dict[str, Any]:
    actor = row.get("actor") if isinstance(row.get("actor"), dict) else {}
    course = row.get("course") if isinstance(row.get("course"), dict) else {}
    credential = row.get("credential") if isinstance(row.get("credential"), dict) else {}
    model = row.get("model") if isinstance(row.get("model"), dict) else {}
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    performance = row.get("performance") if isinstance(row.get("performance"), dict) else {}
    request_record = row.get("request") if isinstance(row.get("request"), dict) else {}
    response_record = row.get("response") if isinstance(row.get("response"), dict) else {}
    prompt = request_record.get("input_text", request_record.get("body"))
    response_content = response_record.get("output_text", response_record.get("body"))
    return {
        "request_id": row.get("request_id") or row.get("_id"),
        "received_at": row.get("received_at") or row.get("accepted_at"),
        "terminal_at": row.get("terminal_at"),
        "user_id": actor.get("user_id"),
        "user_email": actor.get("email"),
        "user_name": actor.get("name"),
        "course_id": course.get("course_id"),
        "course_code": course.get("course_code"),
        "key_id": credential.get("key_id"),
        "key_name": credential.get("key_name"),
        "source": row.get("source"),
        "operation": row.get("operation") or "responses.create",
        "public_model": model.get("public_model") or request_record.get("model"),
        "actual_model": model.get("actual_model") or row.get("actual_model"),
        "outcome": outcome(row),
        "http_status": row.get("http_status"),
        "request_latency_ms": performance.get("request_latency_ms") or row.get("request_latency_ms"),
        "input_tokens": usage.get("input_tokens") or row.get("prompt_eval_count"),
        "output_tokens": usage.get("output_tokens") or row.get("eval_count"),
        "total_tokens": usage.get("total_tokens"),
        "prompt": prompt,
        "response": response_content,
        "error_stage": row.get("error_stage"),
        "error_type": row.get("error_type"),
    }


def get_analytics_export(deps: dict[str, Any]):
    unauthorized = _require_analytics_admin(deps)
    if unauthorized:
        return unauthorized
    export_format = (request.args.get("format") or "json").strip().lower()
    if export_format not in EXPORT_FORMATS:
        return jsonify({"error": "format must be json or csv."}), 400
    try:
        limit = bounded_int(request.args.get("limit"), MAX_EXPORT_ROWS, MAX_EXPORT_ROWS)
        rows, window, start, end = _analytics_rows_with_projection(deps, None)
    except AnalyticsQueryError as error:
        return _analytics_error(error)
    except Exception as error:
        return _analytics_failure(deps, error)
    if len(rows) > limit:
        return jsonify({
            "error": (
                f"This export contains {len(rows):,} rows, which exceeds the {limit:,}-row limit. "
                "Choose a shorter range or add filters."
            )
        }), 413

    rows.sort(
        key=lambda row: received_at(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    exported_rows = [_export_row(row) for row in rows]
    try:
        deps["record_audit_event"](
            deps,
            "analytics-export",
            target_type="telemetry",
            target_id=window,
            metadata={"format": export_format, "row_count": len(exported_rows), "filters": _analytics_filter_values()},
        )
    except Exception as error:
        deps["logger"].error("analytics.export_audit_failed error_type=%s", type(error).__name__)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"rocky-analytics-{stamp}.{export_format}"
    if export_format == "json":
        payload = {
            "exported_at": datetime.now(timezone.utc),
            "window": window,
            "start": start,
            "end": end,
            "count": len(exported_rows),
            "records": exported_rows,
        }
        return Response(
            json.dumps(payload, default=str, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({key: _csv_safe(value) for key, value in row.items()} for row in exported_rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        deps["record_audit_event"](
            deps,
            "telemetry-review",
            course={"id": course.get("course_id"), "code": course.get("course_code") or ""},
            target_type="telemetry-request",
            target_id=request_id,
            changes={
                "status": {"before": previous["status"], "after": updated["status"]},
                "flagged": {"before": previous["flagged"], "after": updated["flagged"]},
                "flag_reasons": updated["flag_reasons"],
            },
        )
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
