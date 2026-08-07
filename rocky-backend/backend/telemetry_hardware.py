from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from .telemetry_analytics import (
    as_utc,
    floor_bucket,
    iso,
    nested,
    timeseries,
)


def hardware_documents_in_range(collection, start: datetime, end: datetime):
    try:
        return list(collection.find({"sampled_at": {"$gte": start, "$lt": end}}))
    except Exception:
        if "mongita" not in type(collection).__module__.lower():
            raise
        rows = []
        for row in collection.find({}):
            sampled_at = as_utc(row.get("sampled_at"))
            if sampled_at is not None and start <= sampled_at < end:
                rows.append(row)
        return rows


def _number(row: dict[str, Any], *path: str) -> float | None:
    value = nested(row, *path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, float(value))


def _summary(values: list[float]) -> dict[str, float | None]:
    return {
        "average": round(sum(values) / len(values), 2) if values else None,
        "maximum": round(max(values), 2) if values else None,
    }


def _latest_public(row: dict[str, Any] | None):
    if row is None:
        return None
    model_rows = nested(row, "model", "loaded_models", default=[])
    return {
        "sampled_at": iso(as_utc(row.get("sampled_at"))),
        "source": row.get("source") if isinstance(row.get("source"), dict) else {},
        "gpu": row.get("gpu") if isinstance(row.get("gpu"), dict) else None,
        "system": row.get("system") if isinstance(row.get("system"), dict) else None,
        "model": {
            "loaded_model_count": nested(row, "model", "loaded_model_count", default=0),
            "loaded_vram_bytes": nested(row, "model", "loaded_vram_bytes"),
            "loaded_models": model_rows if isinstance(model_rows, list) else [],
        } if isinstance(row.get("model"), dict) else None,
        "runtime": row.get("runtime") if isinstance(row.get("runtime"), dict) else None,
        "partial": bool(row.get("partial")),
        "missing": row.get("missing") if isinstance(row.get("missing"), list) else [],
    }


def hardware_history(hardware_rows: list[dict[str, Any]],
                     interaction_rows: list[dict[str, Any]], window: str,
                     start: datetime, end: datetime, bucket: str,
                     sample_interval_seconds: int):
    workload = timeseries(interaction_rows, window, start, end, bucket)
    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in hardware_rows:
        sampled_at = as_utc(row.get("sampled_at"))
        if sampled_at is not None:
            grouped[floor_bucket(sampled_at, bucket)].append(row)

    result = []
    for workload_bucket in workload["buckets"]:
        bucket_start = datetime.fromisoformat(
            workload_bucket["start"].replace("Z", "+00:00")
        )
        samples = sorted(
            grouped.get(bucket_start, []),
            key=lambda row: as_utc(row.get("sampled_at")) or start,
        )
        metrics = {
            "gpu_utilization_percent": [],
            "gpu_memory_percent": [],
            "gpu_temperature_c": [],
            "gpu_power_watts": [],
            "cpu_percent": [],
            "system_memory_percent": [],
        }
        paths = {
            "gpu_utilization_percent": ("gpu", "utilization_percent"),
            "gpu_memory_percent": ("gpu", "memory_percent"),
            "gpu_temperature_c": ("gpu", "temperature_c"),
            "gpu_power_watts": ("gpu", "power_watts"),
            "cpu_percent": ("system", "cpu_percent"),
            "system_memory_percent": ("system", "memory_percent"),
        }
        for sample in samples:
            for name, path in paths.items():
                value = _number(sample, *path)
                if value is not None:
                    metrics[name].append(value)
        latest = samples[-1] if samples else None
        result.append({
            "start": workload_bucket["start"],
            "end": workload_bucket["end"],
            "sample_count": len(samples),
            "hardware": {name: _summary(values) for name, values in metrics.items()},
            "model": {
                "loaded_model_count": nested(latest or {}, "model", "loaded_model_count"),
                "loaded_models": nested(latest or {}, "model", "loaded_models", default=[]),
            },
            "runtime": {
                "active_inference_requests": nested(
                    latest or {}, "runtime", "active_inference_requests"
                ),
            },
            "workload": {
                "requests": workload_bucket["requests"],
                "input_tokens": workload_bucket["usage"]["input_tokens"],
                "output_tokens": workload_bucket["usage"]["output_tokens"],
                "total_tokens": workload_bucket["usage"]["total_tokens"],
                "p95_latency_ms": workload_bucket["latency_ms"]["p95"],
                "generation_tokens_per_second": workload_bucket["model_performance"]["generation_tokens_per_second"],
                "generation_duration_ms": workload_bucket["model_performance"]["generation_duration"]["average_ms"],
                "load_duration_ms": workload_bucket["model_performance"]["load_duration"]["average_ms"],
            },
        })

    ordered = sorted(
        hardware_rows,
        key=lambda row: as_utc(row.get("sampled_at")) or start,
    )
    latest_row = ordered[-1] if ordered else None
    latest_at = as_utc(latest_row.get("sampled_at")) if latest_row else None
    stale_after = max(90, sample_interval_seconds * 3)
    if latest_row is None:
        status = "unavailable"
    elif latest_at is None or (end - latest_at).total_seconds() > stale_after:
        status = "stale"
    elif latest_row.get("partial"):
        status = "partial"
    else:
        status = "live"
    return {
        "window": window,
        "bucket": bucket,
        "start": iso(start),
        "end": iso(end),
        "sample_interval_seconds": sample_interval_seconds,
        "sample_count": len(hardware_rows),
        "status": status,
        "latest": _latest_public(latest_row),
        "buckets": result,
    }
