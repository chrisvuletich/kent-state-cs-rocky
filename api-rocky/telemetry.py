import copy
import logging
import time
from datetime import datetime, timezone


CURRENT_DOCUMENT_ID = "rocky:model-runtime"
SCHEMA_VERSION = 3
OUTCOMES = {"completed", "rejected", "failed", "timed_out"}
DELIVERY_STATUSES = {"completed", "client_disconnected"}
BYTE_FIELDS = ("model_input_bytes", "model_output_bytes")
INTEGER_FIELDS = (
    "prompt_eval_count",
    "eval_count",
    "total_duration",
    "load_duration",
    "prompt_eval_duration",
    "eval_duration",
)
STRING_FIELDS = ("actual_model", "stop_reason")
QUEUE_STATUSES = {
    "not_queued",
    "admitted",
    "queue_full",
    "queue_memory_full",
    "timed_out",
    "cancelled",
}
QUEUE_INTEGER_FIELDS = (
    "depth_on_arrival",
    "wait_ms",
    "capacity",
    "queued_bytes_on_arrival",
)
CURRENT_COUNTER_DEFAULTS = {
    "counter_revision": 0,
    "interactions_received_total": 0,
    "interactions_completed_total": 0,
    "interactions_rejected_total": 0,
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
    queue = sanitize_queue_metrics(metrics.get("queue"))
    if queue is not None:
        safe["queue"] = queue
    return safe


def sanitize_queue_metrics(queue):
    if not isinstance(queue, dict) or queue.get("status") not in QUEUE_STATUSES:
        return None
    safe = {"status": queue["status"]}
    for field in QUEUE_INTEGER_FIELDS:
        value = count(queue.get(field))
        if value is None:
            return None
        safe[field] = value
    initial_position = queue.get("initial_position")
    if initial_position is not None:
        initial_position = count(initial_position)
        if initial_position is None:
            return None
        safe["initial_position"] = initial_position
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
            ([('state', 1), ('received_at', 1)],
             {"name": "telemetry_state_received_at"}),
            ([('operation', 1), ('received_at', -1)],
             {"name": "telemetry_operation_received_at"}),
            ([('actor.user_id', 1), ('received_at', -1)],
             {"name": "telemetry_actor_received_at"}),
            ([('credential.key_id', 1), ('received_at', -1)],
             {"name": "telemetry_key_received_at"}),
            ([('course.course_id', 1), ('received_at', -1)],
             {"name": "telemetry_course_received_at"}),
            ([('outcome', 1), ('received_at', -1)],
             {"name": "telemetry_outcome_received_at"}),
            ([('review.flagged', 1), ('received_at', -1)],
             {"name": "telemetry_review_received_at"}),
            ([('review.status', 1), ('received_at', -1)],
             {"name": "telemetry_review_status_received_at"}),
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

    def record_received(self, request_id, record=None, received_at=None,
                        started_monotonic_ns=None):
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("Telemetry request_id must be a non-empty string.")
        received_at = utc(received_at or utc_now())
        interaction = {
            "request_id": request_id,
            "started_monotonic_ns": (
                started_monotonic_ns
                if isinstance(started_monotonic_ns, int)
                else time.monotonic_ns()
            ),
            "current_counted": False,
            "persisted": False,
        }
        document = copy.deepcopy(record) if isinstance(record, dict) else {}
        document.update({
            "_id": request_id,
            "schema_version": SCHEMA_VERSION,
            "state": "received",
            "received_at": received_at,
            "review": document.get("review") if isinstance(document.get("review"), dict) else {
                "version": 0,
                "flagged": False,
                "flag_reasons": [],
                "status": "unreviewed",
                "reviewed_by": None,
                "reviewed_at": None,
                "notes": None,
            },
        })
        try:
            self.interactions.insert_one(document)
            interaction["persisted"] = True
        except Exception as error:
            safe_log(self.logger, "telemetry.receive_write_failed", error)
            return interaction
        try:
            result = self.current.update_one({"_id": CURRENT_DOCUMENT_ID}, {
                "$inc": {
                    "counter_revision": 1,
                    "interactions_received_total": 1,
                    "active_requests": 1,
                },
                "$max": {"last_interaction_at": received_at},
            })
            interaction["current_counted"] = (
                getattr(result, "modified_count", 0) == 1)
        except Exception as error:
            safe_log(self.logger, "telemetry.receive_counter_failed", error)
        return interaction

    def update_interaction(self, interaction, fields):
        if (not isinstance(interaction, dict)
                or not interaction.get("persisted")
                or not isinstance(fields, dict)
                or not fields):
            return False
        try:
            result = self.interactions.update_one(
                {"_id": interaction["request_id"], "state": "received"},
                {"$set": copy.deepcopy(fields)},
            )
        except Exception as error:
            safe_log(self.logger, "telemetry.enrich_write_failed", error)
            return False
        return getattr(result, "matched_count", 1) == 1

    def record_terminal(self, interaction, outcome, model_metrics=None,
                        terminal_at=None, request_latency_ms=None,
                        terminal_record=None):
        if outcome not in OUTCOMES:
            raise ValueError(f"Unsupported telemetry outcome: {outcome!r}")
        if not isinstance(interaction, dict) or not interaction.get("persisted"):
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
        terminal_fields = (
            copy.deepcopy(terminal_record)
            if isinstance(terminal_record, dict)
            else {}
        )
        terminal_fields.update({
            "state": "terminal",
            "outcome": outcome,
            "terminal_at": terminal_at,
        })
        performance = terminal_fields.get("performance")
        if not isinstance(performance, dict):
            performance = {}
        performance["request_latency_ms"] = request_latency_ms
        terminal_fields["performance"] = performance

        try:
            result = self.interactions.update_one(
                {"_id": interaction["request_id"], "state": "received"},
                {"$set": terminal_fields},
            )
        except Exception as error:
            safe_log(self.logger, "telemetry.terminal_write_failed", error)
            return False
        if getattr(result, "modified_count", 0) != 1:
            return False
        if not interaction["current_counted"]:
            return True

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
            return True
        return True

    def record_delivery(self, interaction, status, delivered_at=None):
        """Record post-generation stream delivery without changing counters."""
        if status not in DELIVERY_STATUSES:
            raise ValueError(f"Unsupported telemetry delivery status: {status!r}")
        if not isinstance(interaction, dict) or not interaction.get("persisted"):
            return False
        delivered_at = utc(delivered_at or utc_now())
        try:
            result = self.interactions.update_one(
                {
                    "_id": interaction["request_id"],
                    "state": "terminal",
                    "outcome": "completed",
                },
                {"$set": {
                    "delivery": {
                        "status": status,
                        "recorded_at": delivered_at,
                    },
                }},
            )
        except Exception as error:
            safe_log(self.logger, "telemetry.delivery_write_failed", error)
            return False
        return getattr(result, "matched_count", 1) == 1
