from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from threading import Event
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pymongo.errors import DuplicateKeyError


MAX_DEVICES = 16
MAX_MODELS = 16
MAX_TEXT = 256
SOURCE_ID_PATTERN = re.compile(r"[^a-zA-Z0-9_.-]+")


class HardwareSnapshotError(ValueError):
    pass


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(value: Any, fallback: str = "unknown") -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()[:MAX_TEXT] or fallback


def _number(value: Any, maximum: float | None = None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = max(0.0, float(value))
    if maximum is not None:
        normalized = min(normalized, maximum)
    return round(normalized, 2)


def _integer(value: Any, maximum: int = 10**18) -> int | None:
    number = _number(value, maximum)
    return round(number) if number is not None else None


def _gpu(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    devices = []
    raw_devices = value.get("devices")
    if isinstance(raw_devices, list):
        for row in raw_devices[:MAX_DEVICES]:
            if not isinstance(row, dict):
                continue
            devices.append({
                "index": _integer(row.get("index"), MAX_DEVICES),
                "name": _text(row.get("name"), "GPU"),
                "utilization_percent": _number(row.get("utilization_percent"), 100),
                "memory_used_bytes": _integer(row.get("memory_used_bytes")),
                "memory_total_bytes": _integer(row.get("memory_total_bytes")),
                "temperature_c": _number(row.get("temperature_c"), 200),
                "power_watts": _number(row.get("power_watts"), 100_000),
            })
    return {
        "available": True,
        "count": _integer(value.get("count"), MAX_DEVICES) or len(devices),
        "utilization_percent": _number(value.get("utilization_percent"), 100),
        "memory_used_bytes": _integer(value.get("memory_used_bytes")),
        "memory_total_bytes": _integer(value.get("memory_total_bytes")),
        "memory_percent": _number(value.get("memory_percent"), 100),
        "temperature_c": _number(value.get("temperature_c"), 200),
        "power_watts": _number(value.get("power_watts"), 100_000),
        "devices": devices,
    }


def _system(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    load = value.get("load_average")
    return {
        "cpu_percent": _number(value.get("cpu_percent"), 100),
        "memory_used_bytes": _integer(value.get("memory_used_bytes")),
        "memory_total_bytes": _integer(value.get("memory_total_bytes")),
        "memory_percent": _number(value.get("memory_percent"), 100),
        "load_average": [
            number for item in (load[:3] if isinstance(load, list) else [])
            if (number := _number(item, 1_000_000)) is not None
        ],
    }


def _model(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    models = []
    raw_models = value.get("loaded_models")
    if isinstance(raw_models, list):
        for row in raw_models[:MAX_MODELS]:
            if isinstance(row, dict):
                models.append({
                    "name": _text(row.get("name")),
                    "size_vram_bytes": _integer(row.get("size_vram_bytes")),
                })
    return {
        "loaded_model_count": _integer(value.get("loaded_model_count"), MAX_MODELS) or len(models),
        "loaded_models": models,
        "loaded_vram_bytes": _integer(value.get("loaded_vram_bytes")),
    }


def _runtime(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "active_inference_requests": _integer(
            value.get("active_inference_requests"), 100_000
        ) or 0,
    }


def normalize_snapshot(payload: Any, retention_days: int,
                       received_at: datetime | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HardwareSnapshotError("Hardware snapshot must be a JSON object.")
    sampled_at = _utc(payload.get("sampled_at"))
    now = received_at or datetime.now(timezone.utc)
    if sampled_at is None or sampled_at > now + timedelta(minutes=5):
        raise HardwareSnapshotError("Hardware snapshot timestamp is invalid.")
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    host = _text(source.get("host"))
    source_id = SOURCE_ID_PATTERN.sub("-", host).strip("-") or "unknown"
    gpu = _gpu(payload.get("gpu"))
    system = _system(payload.get("system"))
    model = _model(payload.get("model"))
    runtime = _runtime(payload.get("runtime"))
    missing = []
    for name, value in (("gpu", gpu), ("system", system), ("model", model)):
        if value is None:
            missing.append(name)
    bucket = int(sampled_at.timestamp())
    return {
        "_id": f"{source_id}:{bucket}",
        "schema_version": 1,
        "sampled_at": sampled_at,
        "received_at": now,
        "expires_at": sampled_at + timedelta(days=retention_days),
        "source": {
            "service": _text(source.get("service"), "granite-hardware"),
            "host": host,
        },
        "gpu": gpu,
        "system": system,
        "model": model,
        "runtime": runtime,
        "partial": bool(missing),
        "missing": missing,
    }


class HardwareSampler:
    def __init__(self, collection, settings, logger: logging.Logger | None = None):
        self.collection = collection
        self.settings = settings
        self.logger = logger or logging.getLogger("rocky.hardware-sampler")

    def fetch(self) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.settings.hardware_metrics_token:
            headers["X-Rocky-Metrics-Token"] = self.settings.hardware_metrics_token
        request = Request(self.settings.hardware_metrics_url, headers=headers)
        try:
            with urlopen(
                request, timeout=self.settings.hardware_metrics_timeout_seconds
            ) as response:
                if response.status != 200:
                    raise HardwareSnapshotError("Hardware endpoint returned an error.")
                body = response.read(1_000_001)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise HardwareSnapshotError("Hardware endpoint is unavailable.") from error
        if len(body) > 1_000_000:
            raise HardwareSnapshotError("Hardware snapshot is too large.")
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HardwareSnapshotError("Hardware snapshot is not valid JSON.") from error

    def sample_once(self) -> bool:
        try:
            document = normalize_snapshot(
                self.fetch(), self.settings.hardware_retention_days
            )
            self.collection.insert_one(document)
            self._prune_expired(document["received_at"])
            return True
        except DuplicateKeyError:
            return True
        except Exception as error:
            self.logger.warning(
                "hardware.sample_failed error_type=%s", type(error).__name__
            )
            return False

    def _prune_expired(self, now: datetime) -> None:
        try:
            self.collection.delete_many({"expires_at": {"$lte": now}})
        except Exception:
            for row in self.collection.find({}):
                expires_at = row.get("expires_at")
                if isinstance(expires_at, datetime) and expires_at <= now:
                    self.collection.delete_one({"_id": row.get("_id")})

    def run(self, stop: Event) -> None:
        while not stop.is_set():
            started = time.monotonic()
            self.sample_once()
            remaining = max(
                0.0,
                self.settings.hardware_sample_interval_seconds
                - (time.monotonic() - started),
            )
            stop.wait(remaining)
