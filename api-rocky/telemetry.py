import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4


CURRENT_DOCUMENT_ID = "rocky:model-runtime"
OUTCOMES = {"completed", "failed", "timed_out"}
BYTE_FIELDS = ("model_input_bytes", "model_output_bytes")
INTEGER_FIELDS = ("prompt_eval_count", "eval_count")
STRING_FIELDS = ("actual_model", "stop_reason")
CURRENT_COUNTER_DEFAULTS = {
    "counter_revision": 0,
    "interactions_accepted_total": 0,
    "interactions_completed_total": 0,
    "interactions_failed_total": 0,
    "interactions_timed_out_total": 0,
    "active_requests": 0,
    "model_input_bytes_total": 0,
    "model_output_bytes_total": 0,
    "request_latency_ms_total": 0,
    "request_latency_samples_total": 0,
}


def utc_now():
    return datetime.now(timezone.utc)


def utc(value):
    if not isinstance(value, datetime):
        raise TypeError("Telemetry timestamps must be datetime values.")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def sanitize_model_metrics(metrics):
    if not isinstance(metrics, dict):
        return {}
    safe = {}
    for field in BYTE_FIELDS + INTEGER_FIELDS:
        value = count(metrics.get(field))
        if value is not None:
            safe[field] = value
    for field in STRING_FIELDS:
        value = metrics.get(field)
        if isinstance(value, str) and value.strip():
            safe[field] = value.strip()[:256]
    return safe


def safe_log(logger, event, error):
    logger.warning("%s error_type=%s", event, type(error).__name__)


class TelemetryStore:
    def __init__(self, interactions, current, logger=None):
        self.interactions = interactions
        self.current = current
        self.logger = logger or logging.getLogger("rocky.telemetry")

    def ensure_indexes(self):
        ok = True
        indexes = (
            ([("state", 1), ("accepted_at", 1)],
             {"name": "telemetry_state_accepted_at"}),
            ([("expires_at", 1)], {
                "name": "telemetry_terminal_expiry", "expireAfterSeconds": 0,
            }),
        )
        for keys, options in indexes:
            try:
                self.interactions.create_index(keys, **options)
            except Exception as error:
                ok = False
                safe_log(self.logger, "telemetry.index_create_failed", error)
        try:
            self.current.update_one(
                {"_id": CURRENT_DOCUMENT_ID},
                {"$setOnInsert": CURRENT_COUNTER_DEFAULTS}, upsert=True)
        except Exception as error:
            ok = False
            safe_log(self.logger, "telemetry.current_init_failed", error)
        return ok

    def record_accepted(self):
        request_id = str(uuid4())
        accepted_at = utc_now()
        interaction = {
            "request_id": request_id,
            "started_monotonic_ns": time.monotonic_ns(),
            "current_counted": False,
        }
        try:
            self.interactions.insert_one({
                "_id": request_id,
                "accepted_at": accepted_at,
                "state": "accepted",
            })
        except Exception as error:
            safe_log(self.logger, "telemetry.accept_write_failed", error)
            return None
        try:
            result = self.current.update_one({"_id": CURRENT_DOCUMENT_ID}, {
                "$inc": {
                    "counter_revision": 1,
                    "interactions_accepted_total": 1,
                    "active_requests": 1,
                },
                "$max": {"last_interaction_at": accepted_at},
            })
            interaction["current_counted"] = (
                getattr(result, "modified_count", 0) == 1)
        except Exception as error:
            safe_log(self.logger, "telemetry.accept_counter_failed", error)
        return interaction

    def record_terminal(self, interaction, outcome, model_metrics=None,
                        terminal_at=None, request_latency_ms=None):
        if outcome not in OUTCOMES:
            raise ValueError(f"Unsupported telemetry outcome: {outcome!r}")
        if not isinstance(interaction, dict):
            return False
        terminal_at = utc(terminal_at or utc_now())
        if request_latency_ms is None:
            elapsed = time.monotonic_ns() - interaction["started_monotonic_ns"]
            request_latency_ms = max(0, elapsed // 1_000_000)
        else:
            request_latency_ms = count(request_latency_ms)
        if request_latency_ms is None:
            return False

        metrics = sanitize_model_metrics(model_metrics)
        try:
            result = self.interactions.update_one(
                {"_id": interaction["request_id"], "state": "accepted"},
                {"$set": {
                    "state": "terminal",
                    "outcome": outcome,
                    "terminal_at": terminal_at,
                    "expires_at": terminal_at + timedelta(days=7),
                    "request_latency_ms": request_latency_ms,
                    **metrics,
                }},
            )
        except Exception as error:
            safe_log(self.logger, "telemetry.terminal_write_failed", error)
            return False
        if (getattr(result, "modified_count", 0) != 1
                or not interaction["current_counted"]):
            return False

        increments = {
            "counter_revision": 1,
            f"interactions_{outcome}_total": 1,
            "active_requests": -1,
            "request_latency_ms_total": request_latency_ms,
            "request_latency_samples_total": 1,
        }
        for source, target in (
            ("model_input_bytes", "model_input_bytes_total"),
            ("model_output_bytes", "model_output_bytes_total"),
            ("prompt_eval_count", "prompt_tokens_total"),
            ("eval_count", "output_tokens_total"),
        ):
            if source in metrics:
                increments[target] = metrics[source]
        latest_terminal = {"$lte": [
            {"$ifNull": ["$last_terminal_at", terminal_at]}, terminal_at,
        ]}
        changes = {
            field: {"$add": [{"$ifNull": [f"${field}", 0]}, value]}
            for field, value in increments.items()
        }
        changes.update(
            last_interaction_at={"$max": [
                {"$ifNull": ["$last_interaction_at", terminal_at]}, terminal_at,
            ]},
            last_terminal_at={"$cond": [
                latest_terminal, terminal_at, "$last_terminal_at",
            ]},
        )
        if "actual_model" in metrics:
            changes["last_model"] = {"$cond": [
                latest_terminal, metrics["actual_model"], "$last_model",
            ]}
        if "stop_reason" in metrics:
            changes["last_stop_reason"] = {"$cond": [
                latest_terminal, metrics["stop_reason"], "$last_stop_reason",
            ]}
        try:
            result = self.current.update_one(
                {"_id": CURRENT_DOCUMENT_ID}, [{"$set": changes}]
            )
        except Exception as error:
            safe_log(self.logger, "telemetry.terminal_counter_failed", error)
            return False
        return getattr(result, "modified_count", 0) == 1
