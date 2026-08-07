from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import ceil, floor
from typing import Any, Iterable


WINDOWS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
BUCKETS = {
    "minute": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
}
BREAKDOWN_DIMENSIONS = {
    "user", "course", "key", "group", "model", "source", "outcome",
}
OUTCOMES = ("completed", "rejected", "failed", "timed_out")
MAX_BUCKETS = 1_000
MAX_BREAKDOWN_ROWS = 100
MAX_REQUEST_ROWS = 200
DEFAULT_UNRESOLVED_AFTER_SECONDS = 240
ANALYTICS_ROW_PROJECTION = {
    "request_id": 1,
    "state": 1,
    "received_at": 1,
    "accepted_at": 1,
    "terminal_at": 1,
    "outcome": 1,
    "http_status": 1,
    "source": 1,
    "actor": 1,
    "credential": 1,
    "course": 1,
    "model": 1,
    "usage": 1,
    "performance": 1,
    "review": 1,
    "error_stage": 1,
    "error_type": 1,
    "prompt_eval_count": 1,
    "eval_count": 1,
    "model_input_bytes": 1,
    "model_output_bytes": 1,
    "total_duration": 1,
    "load_duration": 1,
    "prompt_eval_duration": 1,
    "eval_duration": 1,
    "request_latency_ms": 1,
    "actual_model": 1,
}


class AnalyticsQueryError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def nested(document: dict[str, Any], *path: str, default=None):
    value: Any = document
    for part in path:
        if not isinstance(value, dict):
            return default
        value = value.get(part)
    return default if value is None else value


def nonnegative_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, value)


def integer(value: Any) -> int:
    return int(nonnegative_number(value))


def window_range(window: str | None, now: datetime | None = None):
    normalized = (window or "24h").strip().lower()
    duration = WINDOWS.get(normalized)
    if duration is None:
        raise AnalyticsQueryError(
            f"Unsupported window. Choose one of: {', '.join(WINDOWS)}."
        )
    end = as_utc(now or utc_now())
    if end is None:
        raise AnalyticsQueryError("The analytics clock is invalid.")
    return normalized, end - duration, end


def default_bucket(window: str) -> str:
    if window in {"15m", "1h", "6h"}:
        return "minute"
    if window in {"24h", "7d"}:
        return "hour"
    return "day"


def resolve_bucket(window: str, start: datetime, end: datetime,
                   bucket: str | None):
    normalized = (bucket or default_bucket(window)).strip().lower()
    duration = BUCKETS.get(normalized)
    if duration is None:
        raise AnalyticsQueryError(
            f"Unsupported bucket. Choose one of: {', '.join(BUCKETS)}."
        )
    points = ceil((end - start) / duration)
    if points > MAX_BUCKETS:
        raise AnalyticsQueryError(
            f"That window and bucket produce {points} rows; the limit is {MAX_BUCKETS}."
        )
    return normalized, duration


def bounded_int(value: str | None, default: int, maximum: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise AnalyticsQueryError("Limit must be an integer.") from error
    if parsed < 1 or parsed > maximum:
        raise AnalyticsQueryError(f"Limit must be between 1 and {maximum}.")
    return parsed


def documents_in_range(collection, start: datetime, end: datetime,
                       projection: dict[str, int] | None = None):
    """Read only the selected interval, including pre-v2 accepted_at records."""
    rows: dict[str, dict[str, Any]] = {}
    queries = (
        {"received_at": {"$gte": start, "$lt": end}},
        {"received_at": {"$exists": False},
         "accepted_at": {"$gte": start, "$lt": end}},
    )
    try:
        iterables = [
            collection.find(query, projection) if projection else collection.find(query)
            for query in queries
        ]
        for result in iterables:
            for row in result:
                identifier = str(row.get("request_id") or row.get("_id"))
                rows[identifier] = row
    except Exception:
        if "mongita" not in type(collection).__module__.lower():
            raise
        # Mongita has deliberately limited query-operator support. This fallback
        # is only used by the local development backend.
        for row in collection.find({}):
            timestamp = received_at(row)
            if timestamp is not None and start <= timestamp < end:
                identifier = str(row.get("request_id") or row.get("_id"))
                if projection:
                    rows[identifier] = {
                        key: row.get(key)
                        for key, included in projection.items()
                        if included and key in row
                    }
                    rows[identifier]["_id"] = row.get("_id")
                else:
                    rows[identifier] = row
    return list(rows.values())


def received_at(row: dict[str, Any]) -> datetime | None:
    return as_utc(row.get("received_at") or row.get("accepted_at"))


def open_interaction_counts(collection, generated_at: datetime | None = None,
                            unresolved_after_seconds: int = DEFAULT_UNRESOLVED_AFTER_SECONDS):
    if unresolved_after_seconds <= 0:
        raise ValueError("Unresolved request threshold must be positive.")
    now = as_utc(generated_at or utc_now())
    if now is None:
        raise ValueError("The analytics clock is invalid.")
    try:
        rows = collection.find(
            {"state": {"$in": ["received", "accepted"]}},
            {"received_at": 1, "accepted_at": 1},
        )
    except Exception:
        if "mongita" not in type(collection).__module__.lower():
            raise
        rows = (
            row for row in collection.find({})
            if row.get("state") in {"received", "accepted"}
        )

    active = 0
    unresolved = 0
    for row in rows:
        started_at = received_at(row)
        if started_at is None:
            unresolved += 1
            continue
        age_seconds = max(0, (now - started_at).total_seconds())
        if age_seconds > unresolved_after_seconds:
            unresolved += 1
        else:
            active += 1
    return {"active_requests": active, "unresolved_interactions": unresolved}


def usage(row: dict[str, Any]) -> tuple[int, int, int]:
    input_tokens = integer(nested(
        row, "usage", "input_tokens", default=row.get("prompt_eval_count")
    ))
    output_tokens = integer(nested(
        row, "usage", "output_tokens", default=row.get("eval_count")
    ))
    total_tokens = integer(nested(row, "usage", "total_tokens"))
    return input_tokens, output_tokens, total_tokens or input_tokens + output_tokens


def bytes_used(row: dict[str, Any]) -> tuple[int, int]:
    return (
        integer(nested(row, "usage", "input_bytes", default=row.get("model_input_bytes"))),
        integer(nested(row, "usage", "output_bytes", default=row.get("model_output_bytes"))),
    )


def duration_ns(row: dict[str, Any], structured_name: str, legacy_name: str):
    value = nested(row, "performance", structured_name, default=row.get(legacy_name))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def latency(row: dict[str, Any]) -> float | None:
    value = nested(
        row, "performance", "request_latency_ms",
        default=row.get("request_latency_ms"),
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def outcome(row: dict[str, Any]) -> str:
    value = row.get("outcome")
    if value in OUTCOMES:
        return value
    return "active"


def percentile(values: Iterable[float], percentage: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * percentage
    lower = floor(position)
    upper = ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    result = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(result, 2)


def metric_accumulator():
    return {
        "requests": 0,
        "completed": 0,
        "rejected": 0,
        "failed": 0,
        "timed_out": 0,
        "active": 0,
        "flagged": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "input_bytes": 0,
        "output_bytes": 0,
        "latencies": [],
        "model_total_durations_ns": [],
        "model_load_durations_ns": [],
        "prompt_eval_durations_ns": [],
        "generation_durations_ns": [],
        "prompt_throughput_tokens": 0,
        "generation_throughput_tokens": 0,
    }


def add_row(metrics: dict[str, Any], row: dict[str, Any]):
    row_outcome = outcome(row)
    input_tokens, output_tokens, total_tokens = usage(row)
    input_bytes, output_bytes = bytes_used(row)
    metrics["requests"] += 1
    metrics[row_outcome] += 1
    metrics["flagged"] += int(bool(nested(row, "review", "flagged", default=False)))
    metrics["input_tokens"] += input_tokens
    metrics["output_tokens"] += output_tokens
    metrics["total_tokens"] += total_tokens
    metrics["input_bytes"] += input_bytes
    metrics["output_bytes"] += output_bytes
    row_latency = latency(row)
    if row_latency is not None:
        metrics["latencies"].append(row_latency)
    durations = (
        ("model_total_durations_ns", "model_total_duration_ns", "total_duration"),
        ("model_load_durations_ns", "model_load_duration_ns", "load_duration"),
        ("prompt_eval_durations_ns", "prompt_eval_duration_ns", "prompt_eval_duration"),
        ("generation_durations_ns", "generation_duration_ns", "eval_duration"),
    )
    for target, structured_name, legacy_name in durations:
        value = duration_ns(row, structured_name, legacy_name)
        if value is not None:
            metrics[target].append(value)
            if target == "prompt_eval_durations_ns":
                metrics["prompt_throughput_tokens"] += input_tokens
            elif target == "generation_durations_ns":
                metrics["generation_throughput_tokens"] += output_tokens


def rate(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def public_metrics(metrics: dict[str, Any]):
    terminal = sum(metrics[name] for name in OUTCOMES)
    inference_attempts = metrics["completed"] + metrics["failed"] + metrics["timed_out"]
    latencies = metrics["latencies"]

    def duration_summary(values):
        milliseconds = [value / 1_000_000 for value in values]
        return {
            "samples": len(milliseconds),
            "average_ms": round(sum(milliseconds) / len(milliseconds), 2) if milliseconds else None,
            "p95_ms": percentile(milliseconds, 0.95),
        }

    prompt_seconds = sum(metrics["prompt_eval_durations_ns"]) / 1_000_000_000
    generation_seconds = sum(metrics["generation_durations_ns"]) / 1_000_000_000
    return {
        "requests": metrics["requests"],
        "terminal": terminal,
        "active": metrics["active"],
        "outcomes": {name: metrics[name] for name in OUTCOMES},
        "flagged": metrics["flagged"],
        "success_rate": rate(metrics["completed"], inference_attempts),
        "acceptance_rate": rate(metrics["requests"] - metrics["rejected"], metrics["requests"]),
        "usage": {
            "input_tokens": metrics["input_tokens"],
            "output_tokens": metrics["output_tokens"],
            "total_tokens": metrics["total_tokens"],
            "input_bytes": metrics["input_bytes"],
            "output_bytes": metrics["output_bytes"],
        },
        "latency_ms": {
            "samples": len(latencies),
            "average": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "model_performance": {
            "total_duration": duration_summary(metrics["model_total_durations_ns"]),
            "load_duration": duration_summary(metrics["model_load_durations_ns"]),
            "prompt_eval_duration": duration_summary(metrics["prompt_eval_durations_ns"]),
            "generation_duration": duration_summary(metrics["generation_durations_ns"]),
            "prompt_tokens_per_second": (
                round(metrics["prompt_throughput_tokens"] / prompt_seconds, 2)
                if prompt_seconds else None
            ),
            "generation_tokens_per_second": (
                round(metrics["generation_throughput_tokens"] / generation_seconds, 2)
                if generation_seconds else None
            ),
        },
    }


def minute_peaks(rows: list[dict[str, Any]]):
    buckets: dict[datetime, dict[str, int]] = defaultdict(
        lambda: {"requests": 0, "tokens": 0}
    )
    for row in rows:
        timestamp = received_at(row)
        if timestamp is None:
            continue
        minute = timestamp.replace(second=0, microsecond=0)
        buckets[minute]["requests"] += 1
        buckets[minute]["tokens"] += usage(row)[2]
    return (
        max((item["requests"] for item in buckets.values()), default=0),
        max((item["tokens"] for item in buckets.values()), default=0),
    )


def summary(rows: list[dict[str, Any]], window: str,
            start: datetime, end: datetime):
    metrics = metric_accumulator()
    for row in rows:
        add_row(metrics, row)
    result = public_metrics(metrics)
    minutes = max((end - start).total_seconds() / 60, 1)
    peak_rpm, peak_tpm = minute_peaks(rows)
    result.update({
        "window": window,
        "start": iso(start),
        "end": iso(end),
        "rates": {
            "average_requests_per_minute": round(metrics["requests"] / minutes, 4),
            "average_requests_per_hour": round(metrics["requests"] / minutes * 60, 4),
            "average_tokens_per_minute": round(metrics["total_tokens"] / minutes, 4),
            "average_tokens_per_hour": round(metrics["total_tokens"] / minutes * 60, 4),
            "peak_requests_per_minute": peak_rpm,
            "peak_tokens_per_minute": peak_tpm,
        },
    })
    return result


def floor_bucket(value: datetime, bucket: str) -> datetime:
    if bucket == "minute":
        return value.replace(second=0, microsecond=0)
    if bucket == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def timeseries(rows: list[dict[str, Any]], window: str, start: datetime,
               end: datetime, bucket: str):
    duration = BUCKETS[bucket]
    first = floor_bucket(start, bucket)
    by_bucket: dict[datetime, dict[str, Any]] = {}
    cursor = first
    while cursor < end:
        by_bucket[cursor] = metric_accumulator()
        cursor += duration
    for row in rows:
        timestamp = received_at(row)
        if timestamp is not None:
            key = floor_bucket(timestamp, bucket)
            if key in by_bucket:
                add_row(by_bucket[key], row)
    bucket_minutes = duration.total_seconds() / 60
    result = []
    for bucket_start, metrics in sorted(by_bucket.items()):
        item = public_metrics(metrics)
        item.update({
            "start": iso(bucket_start),
            "end": iso(min(bucket_start + duration, end)),
            "requests_per_minute": round(metrics["requests"] / bucket_minutes, 4),
            "requests_per_hour": round(metrics["requests"] / bucket_minutes * 60, 4),
            "tokens_per_minute": round(metrics["total_tokens"] / bucket_minutes, 4),
            "tokens_per_hour": round(metrics["total_tokens"] / bucket_minutes * 60, 4),
        })
        result.append(item)
    return {
        "window": window,
        "bucket": bucket,
        "start": iso(start),
        "end": iso(end),
        "buckets": result,
    }


def dimension_value(row: dict[str, Any], dimension: str):
    if dimension == "user":
        identifier = nested(row, "actor", "user_id") or nested(row, "actor", "email")
        label = nested(row, "actor", "name") or nested(row, "actor", "email") or identifier
    elif dimension == "course":
        identifier = nested(row, "course", "course_id") or nested(row, "course", "course_code")
        label = nested(row, "course", "course_code") or identifier
    elif dimension == "key":
        identifier = nested(row, "credential", "key_id")
        label = nested(row, "credential", "key_name") or identifier
    elif dimension == "group":
        identifier = nested(row, "course", "group_id")
        label = identifier
    elif dimension == "model":
        identifier = nested(row, "model", "actual_model") or row.get("actual_model") or nested(row, "request", "model")
        label = identifier
    elif dimension == "source":
        identifier = row.get("source")
        label = identifier
    else:
        identifier = outcome(row)
        label = identifier
    identifier = str(identifier) if identifier not in (None, "") else "unattributed"
    return identifier, str(label or identifier)


def breakdown(rows: list[dict[str, Any]], window: str, start: datetime,
              end: datetime, dimension: str, limit: int):
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier, label = dimension_value(row, dimension)
        if identifier not in grouped:
            grouped[identifier] = {"label": label, "metrics": metric_accumulator()}
        add_row(grouped[identifier]["metrics"], row)
    ordered = sorted(
        grouped.items(),
        key=lambda item: (-item[1]["metrics"]["requests"], item[0]),
    )[:limit]
    return {
        "window": window,
        "start": iso(start),
        "end": iso(end),
        "dimension": dimension,
        "rows": [
            {
                "id": identifier,
                "label": item["label"],
                **public_metrics(item["metrics"]),
            }
            for identifier, item in ordered
        ],
    }


def serialize_value(value: Any):
    if isinstance(value, datetime):
        return iso(as_utc(value))
    if isinstance(value, dict):
        return {
            str(key): serialize_value(item)
            for key, item in value.items()
            if key != "_id"
        }
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def request_summary(row: dict[str, Any]):
    return serialize_value({
        "request_id": row.get("request_id") or row.get("_id"),
        "received_at": received_at(row),
        "terminal_at": as_utc(row.get("terminal_at")),
        "state": row.get("state"),
        "outcome": outcome(row),
        "http_status": row.get("http_status"),
        "source": row.get("source"),
        "actor": row.get("actor"),
        "credential": row.get("credential"),
        "course": row.get("course"),
        "model": row.get("model"),
        "usage": row.get("usage"),
        "performance": row.get("performance"),
        "review": row.get("review"),
        "error_stage": row.get("error_stage"),
        "error_type": row.get("error_type"),
    })


def filter_requests(rows: list[dict[str, Any]], *, requested_outcome=None,
                    user_id=None, course_id=None, flagged=None,
                    review_status=None):
    filtered = []
    for row in rows:
        if requested_outcome and outcome(row) != requested_outcome:
            continue
        if user_id and str(nested(row, "actor", "user_id", default="")) != user_id:
            continue
        if course_id and str(nested(row, "course", "course_id", default="")) != course_id:
            continue
        if flagged is not None and bool(nested(row, "review", "flagged", default=False)) != flagged:
            continue
        if review_status and str(nested(
            row, "review", "status", default="unreviewed"
        )) != review_status:
            continue
        filtered.append(row)
    return filtered


def recent_requests(rows: list[dict[str, Any]], window: str,
                    start: datetime, end: datetime, limit: int, **filters):
    filtered = filter_requests(rows, **filters)
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    filtered.sort(
        key=lambda row: received_at(row) or minimum,
        reverse=True,
    )
    return {
        "window": window,
        "start": iso(start),
        "end": iso(end),
        "matched": len(filtered),
        "limit": limit,
        "requests": [request_summary(row) for row in filtered[:limit]],
    }


def request_detail(collection, request_id: str):
    row = collection.find_one({"request_id": request_id})
    if row is None:
        row = collection.find_one({"_id": request_id})
    if row is None:
        return None
    result = serialize_value(row)
    result["request_id"] = str(row.get("request_id") or row.get("_id"))
    result["outcome"] = outcome(row)
    return result


def current_snapshot(document: dict[str, Any] | None,
                     generated_at: datetime | None = None,
                     open_counts: dict[str, int] | None = None):
    row = document if isinstance(document, dict) else {}
    latency_samples = integer(row.get("request_latency_samples_total"))
    latency_total = nonnegative_number(row.get("request_latency_ms_total"))
    return {
        "generated_at": iso(as_utc(generated_at or utc_now())),
        "updated_at": iso(as_utc(row.get("updated_at"))),
        "last_interaction_at": iso(as_utc(row.get("last_interaction_at"))),
        "last_terminal_at": iso(as_utc(row.get("last_terminal_at"))),
        "last_model": row.get("last_model"),
        "last_stop_reason": row.get("last_stop_reason"),
        "active_requests": integer(
            open_counts.get("active_requests")
            if isinstance(open_counts, dict)
            else row.get("active_requests")
        ),
        "unresolved_interactions": integer(
            open_counts.get("unresolved_interactions")
            if isinstance(open_counts, dict)
            else row.get("unresolved_interactions")
        ),
        "registered_users": integer(row.get("registered_users")),
        "lifetime": {
            "requests": integer(
                row.get("interactions_received_total", row.get("interactions_accepted_total"))
            ),
            "outcomes": {
                name: integer(row.get(f"interactions_{name}_total"))
                for name in OUTCOMES
            },
            "usage": {
                "input_tokens": integer(row.get("prompt_tokens_total")),
                "output_tokens": integer(row.get("output_tokens_total")),
                "input_bytes": integer(row.get("model_input_bytes_total")),
                "output_bytes": integer(row.get("model_output_bytes_total")),
            },
            "latency_ms": {
                "samples": latency_samples,
                "average": (
                    round(latency_total / latency_samples, 2)
                    if latency_samples else None
                ),
            },
        },
    }
