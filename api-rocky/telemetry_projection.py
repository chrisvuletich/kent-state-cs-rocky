"""Refresh derived fields in permanent Rocky telemetry_current."""

import logging
import os
from datetime import datetime, timezone

from telemetry import CURRENT_DOCUMENT_ID, count, utc


DEFAULT_UNRESOLVED_AFTER_SECONDS = 240
logger = logging.getLogger("rocky.telemetry_projection")


def counter(document, field):
    value = count(document.get(field, 0))
    if value is None:
        raise ValueError(f"Telemetry current has an invalid {field}.")
    return value


def refresh_current(interactions, current, users, as_of=None,
                    unresolved_after_seconds=DEFAULT_UNRESOLVED_AFTER_SECONDS):
    if unresolved_after_seconds <= 0:
        raise ValueError("Unresolved threshold must be positive.")
    projection_time = utc(as_of or datetime.now(timezone.utc))
    prior = current.find_one({"_id": CURRENT_DOCUMENT_ID})
    if not isinstance(prior, dict):
        raise RuntimeError("Telemetry current is unavailable.")
    prior_updated_at = prior.get("updated_at")
    if (isinstance(prior_updated_at, datetime)
            and utc(prior_updated_at) > projection_time):
        return prior

    revision = counter(prior, "counter_revision")
    latency_total = counter(prior, "request_latency_ms_total")
    latency_samples = counter(prior, "request_latency_samples_total")
    accepted = counter(prior, "interactions_accepted_total")
    terminal = sum(counter(prior, field) for field in (
        "interactions_completed_total",
        "interactions_rejected_total",
        "interactions_failed_total",
        "interactions_timed_out_total",
    ))
    if terminal > accepted:
        raise ValueError("Telemetry terminal totals exceed accepted total.")
    active = accepted - terminal
    unresolved = 0
    for row in interactions.find({
        "state": {"$in": ["accepted", "received"]},
    }):
        accepted_at = row.get("received_at") or row.get("accepted_at")
        if not isinstance(accepted_at, datetime):
            raise ValueError("Active telemetry is missing its received time.")
        age = (projection_time - utc(accepted_at)).total_seconds()
        if age < 0:
            continue
        if age > unresolved_after_seconds:
            unresolved += 1

    registered_users = count(users.count_documents({}))
    if registered_users is None:
        raise ValueError("Registered user count must be nonnegative.")
    derived = {
        "registered_users": registered_users,
        "active_requests": active,
        "unresolved_interactions": unresolved,
        "average_latency_ms": (
            latency_total / latency_samples if latency_samples else None),
        "updated_at": projection_time,
    }

    query = {
        "_id": CURRENT_DOCUMENT_ID,
        "counter_revision": revision,
        "updated_at": ({"$lte": projection_time}
                       if isinstance(prior_updated_at, datetime) else None),
    }
    result = current.update_one(query, {"$set": derived})
    if getattr(result, "matched_count", 0) != 1:
        return current.find_one({"_id": CURRENT_DOCUMENT_ID}) or prior
    return current.find_one({"_id": CURRENT_DOCUMENT_ID})


def safe_log(event, error):
    logger.error("%s error_type=%s", event, type(error).__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    client = None
    try:
        from pymongo import MongoClient
        from telemetry import TelemetryStore

        if os.getenv("ROCKY_DB_BACKEND", "").strip().lower() != "mongodb":
            raise RuntimeError("The telemetry projection requires MongoDB.")
        mongodb_uri = os.getenv("ROCKY_MONGODB_URI", "").strip()
        database_name = os.getenv("ROCKY_DB_NAME", "").strip()
        unresolved_seconds = int(os.getenv(
            "ROCKY_TELEMETRY_UNRESOLVED_AFTER_SECONDS",
            DEFAULT_UNRESOLVED_AFTER_SECONDS,
        ))
        if not mongodb_uri or not database_name or unresolved_seconds <= 0:
            raise RuntimeError("Invalid telemetry projection configuration.")
        client = MongoClient(
            mongodb_uri, serverSelectionTimeoutMS=2000, tz_aware=True
        )
        client.admin.command("ping")
        database = client[database_name]
        interactions = database["telemetry_interactions"]
        current = database["telemetry_current"]
        store = TelemetryStore(interactions, current, logger=logger)
        if not store.ensure_indexes():
            raise RuntimeError("Telemetry indexes are unavailable.")
        refresh_current(interactions, current, database["users"],
                        unresolved_after_seconds=unresolved_seconds)
    except Exception as error:
        safe_log("telemetry.projection_failed", error)
        return 1
    finally:
        if client is not None:
            client.close()
    logger.info("telemetry.projection_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
