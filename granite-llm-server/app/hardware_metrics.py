from __future__ import annotations

import os
import socket
import subprocess
from datetime import datetime, timezone
from typing import Any

import requests

try:
    import psutil
except ImportError:  # Keep model generation available if optional metrics deps lag deployment.
    psutil = None

from app.runtime_state import active_inference_requests
from app.config import env_float, env_http_url


OLLAMA_BASE_URL = env_http_url("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
HARDWARE_COMMAND_TIMEOUT_SECONDS = env_float(
    "ROCKY_HARDWARE_COMMAND_TIMEOUT_SECONDS", 3, minimum=0, allow_minimum=False
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(max(0.0, float(value)), 2)


def _bytes_from_mebibytes(value: str) -> int | None:
    try:
        return max(0, round(float(value.strip()) * 1024 * 1024))
    except (TypeError, ValueError):
        return None


def _float(value: str) -> float | None:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def _nvidia_snapshot() -> dict[str, Any] | None:
    fields = (
        "index,name,utilization.gpu,memory.used,memory.total,"
        "temperature.gpu,power.draw"
    )
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={fields}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=HARDWARE_COMMAND_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None

    devices = []
    for line in result.stdout.splitlines():
        values = [value.strip() for value in line.split(",")]
        if len(values) != 7:
            continue
        try:
            index = int(values[0])
        except ValueError:
            continue
        utilization = _float(values[2])
        temperature = _float(values[5])
        power = _float(values[6])
        memory_used = _bytes_from_mebibytes(values[3])
        memory_total = _bytes_from_mebibytes(values[4])
        devices.append({
            "index": index,
            "name": values[1][:256],
            "utilization_percent": _number(utilization),
            "memory_used_bytes": memory_used,
            "memory_total_bytes": memory_total,
            "temperature_c": _number(temperature),
            "power_watts": _number(power),
        })
    if not devices:
        return None

    used = sum(device["memory_used_bytes"] or 0 for device in devices)
    total = sum(device["memory_total_bytes"] or 0 for device in devices)
    utilizations = [device["utilization_percent"] for device in devices if device["utilization_percent"] is not None]
    temperatures = [device["temperature_c"] for device in devices if device["temperature_c"] is not None]
    powers = [device["power_watts"] for device in devices if device["power_watts"] is not None]
    return {
        "available": True,
        "count": len(devices),
        "utilization_percent": round(sum(utilizations) / len(utilizations), 2) if utilizations else None,
        "memory_used_bytes": used,
        "memory_total_bytes": total,
        "memory_percent": round((used / total) * 100, 2) if total else None,
        "temperature_c": max(temperatures) if temperatures else None,
        "power_watts": round(sum(powers), 2) if powers else None,
        "devices": devices,
    }


def _system_snapshot() -> dict[str, Any] | None:
    if psutil is None:
        return None
    memory = psutil.virtual_memory()
    try:
        load_average = os.getloadavg()
    except (AttributeError, OSError):
        load_average = ()
    return {
        "cpu_percent": _number(psutil.cpu_percent(interval=None)),
        "memory_used_bytes": int(memory.used),
        "memory_total_bytes": int(memory.total),
        "memory_percent": _number(memory.percent),
        "load_average": [round(max(0.0, value), 2) for value in load_average],
    }


def _model_snapshot() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/ps",
            timeout=HARDWARE_COMMAND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    models = []
    for row in rows[:16]:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        size_vram = row.get("size_vram")
        models.append({
            "name": name.strip()[:256] if isinstance(name, str) else "unknown",
            "size_vram_bytes": (
                max(0, size_vram)
                if isinstance(size_vram, int) and not isinstance(size_vram, bool)
                else None
            ),
        })
    return {
        "loaded_model_count": len(models),
        "loaded_models": models,
        "loaded_vram_bytes": sum(row["size_vram_bytes"] or 0 for row in models),
    }


def collect_hardware_snapshot(include_runtime: bool = True) -> dict[str, Any]:
    gpu = _nvidia_snapshot()
    system = _system_snapshot()
    model = _model_snapshot()
    missing = []
    if gpu is None:
        missing.append("gpu")
    if system is None:
        missing.append("system")
    if model is None:
        missing.append("model")
    return {
        "schema_version": 1,
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "service": "granite-hardware",
            "host": socket.gethostname()[:256],
        },
        "gpu": gpu,
        "system": system,
        "model": model,
        "runtime": {
            "active_inference_requests": active_inference_requests(),
        } if include_runtime else None,
        "partial": bool(missing),
        "missing": missing,
    }
