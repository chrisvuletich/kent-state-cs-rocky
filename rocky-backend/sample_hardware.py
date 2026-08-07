from __future__ import annotations

import argparse
import logging
import signal
from threading import Event

from backend.config import get_settings
from backend.hardware_sampler import HardwareSampler
from backend.storage import build_collections


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample Granite hardware telemetry.")
    parser.add_argument("--once", action="store_true", help="Collect one snapshot and exit.")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.hardware_telemetry_enabled:
        logging.getLogger("rocky.hardware-sampler").info(
            "Hardware telemetry is disabled."
        )
        return 0

    collections = build_collections(settings)
    sampler = HardwareSampler(collections.telemetry_hardware, settings)
    if args.once:
        return 0 if sampler.sample_once() else 1

    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    sampler.run(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
