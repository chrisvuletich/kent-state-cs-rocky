from __future__ import annotations

import getpass
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any


def parse_before_date(value: str) -> datetime:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("--before must use YYYY-MM-DD format.") from error
    cutoff = datetime.combine(parsed, time.min, tzinfo=timezone.utc)
    if cutoff > datetime.now(timezone.utc):
        raise ValueError("--before cannot be a future date.")
    return cutoff


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    return None


@dataclass(frozen=True)
class RetentionResult:
    cutoff: datetime
    matched: int
    deleted: int
    oldest: datetime | None
    newest: datetime | None
    applied: bool


class RequestRetention:
    def __init__(self, telemetry_interactions, api_history):
        self.telemetry_interactions = telemetry_interactions
        self.api_history = api_history

    def run(self, cutoff: datetime, *, apply: bool = False) -> RetentionResult:
        matching: list[tuple[Any, datetime]] = []
        for row in self.telemetry_interactions.find({}):
            timestamp = _as_utc(row.get("received_at"))
            if timestamp is not None and timestamp < cutoff:
                matching.append((row.get("_id"), timestamp))

        timestamps = [timestamp for _, timestamp in matching]
        deleted = 0
        if apply and matching:
            identifiers = [identifier for identifier, _ in matching if identifier is not None]
            try:
                result = self.telemetry_interactions.delete_many({"_id": {"$in": identifiers}})
                deleted = int(getattr(result, "deleted_count", 0))
            except Exception:
                for identifier in identifiers:
                    result = self.telemetry_interactions.delete_one({"_id": identifier})
                    deleted += int(getattr(result, "deleted_count", 0))

        result = RetentionResult(
            cutoff=cutoff,
            matched=len(matching),
            deleted=deleted,
            oldest=min(timestamps) if timestamps else None,
            newest=max(timestamps) if timestamps else None,
            applied=apply,
        )
        if apply:
            self.api_history.insert_one({
                "u_id": f"maintenance:{getpass.getuser()}",
                "c_id": "",
                "course_id": None,
                "event_type": "telemetry-purge",
                "group_id": None,
                "group_name": None,
                "is_group_member": False,
                "meta": {
                    "path": "manage.py purge-requests",
                    "actor_id": f"maintenance:{getpass.getuser()}",
                    "actor_email": None,
                    "target_type": "telemetry",
                    "target_id": cutoff.date().isoformat(),
                    "cutoff": cutoff.isoformat(),
                    "matched": result.matched,
                    "deleted": result.deleted,
                },
                "created": datetime.now(timezone.utc).isoformat(),
            })
        return result
