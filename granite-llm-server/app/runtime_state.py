from __future__ import annotations

from threading import Lock


_lock = Lock()
_active_inference_requests = 0


def begin_inference() -> None:
    global _active_inference_requests
    with _lock:
        _active_inference_requests += 1


def end_inference() -> None:
    global _active_inference_requests
    with _lock:
        _active_inference_requests = max(0, _active_inference_requests - 1)


def active_inference_requests() -> int:
    with _lock:
        return _active_inference_requests
