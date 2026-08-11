from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from mongita.errors import DuplicateKeyError as MongitaDuplicateKeyError

try:
    from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError
except Exception:  # pragma: no cover - PyMongo is optional for local Mongita use
    PyMongoDuplicateKeyError = None


RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_COUNTER_RETENTION_SECONDS = 5 * 60
MONGITA_CLEANUP_INTERVAL_SECONDS = 5 * 60
RATE_LIMIT_TTL_INDEX_NAME = "rate_limit_expiration_ttl"

_DUPLICATE_KEY_ERRORS = tuple(
    error_type
    for error_type in (MongitaDuplicateKeyError, PyMongoDuplicateKeyError)
    if isinstance(error_type, type)
)


class RateLimitStoreUnavailable(RuntimeError):
    """Raised when a rate-limit decision cannot be persisted safely."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining_requests: int
    retry_after_seconds: int


def ensure_rate_limit_ttl_index(collection):
    """Create the production MongoDB TTL index for expired counter windows."""
    if collection is None:
        raise ValueError("A rate-limit collection is required.")
    return collection.create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name=RATE_LIMIT_TTL_INDEX_NAME,
    )


class FixedWindowRateLimiter:
    """Atomic per-key request limiting for MongoDB-compatible collections."""

    def __init__(
        self,
        collection,
        *,
        clock: Callable[[], float] = time.time,
        cleanup_expired: bool = False,
        cleanup_interval_seconds: int = MONGITA_CLEANUP_INTERVAL_SECONDS,
        logger: logging.Logger | None = None,
    ):
        if collection is None:
            raise ValueError("A rate-limit collection is required.")
        if (
            isinstance(cleanup_interval_seconds, bool)
            or not isinstance(cleanup_interval_seconds, int)
            or cleanup_interval_seconds < 1
        ):
            raise ValueError("cleanup_interval_seconds must be a positive integer.")

        self._collection = collection
        self._clock = clock
        self._cleanup_expired = cleanup_expired
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._logger = logger or logging.getLogger(__name__)
        self._cleanup_lock = threading.Lock()
        self._next_cleanup_at = 0.0

    def consume(
        self,
        *,
        key_id: str,
        operation: str,
        limit: int,
    ) -> RateLimitDecision:
        normalized_key_id = key_id.strip() if isinstance(key_id, str) else ""
        normalized_operation = operation.strip() if isinstance(operation, str) else ""
        if not normalized_key_id:
            raise ValueError("key_id must be a non-empty string.")
        if not normalized_operation:
            raise ValueError("operation must be a non-empty string.")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer.")

        now_epoch = float(self._clock())
        if not math.isfinite(now_epoch) or now_epoch < 0:
            raise ValueError("The rate-limit clock must return a non-negative finite value.")

        window_number = math.floor(now_epoch / RATE_LIMIT_WINDOW_SECONDS)
        window_started_epoch = window_number * RATE_LIMIT_WINDOW_SECONDS
        window_ends_epoch = window_started_epoch + RATE_LIMIT_WINDOW_SECONDS
        retry_after_seconds = max(1, math.ceil(window_ends_epoch - now_epoch))
        window_started_at = datetime.fromtimestamp(
            window_started_epoch,
            tz=timezone.utc,
        )
        window_ends_at = datetime.fromtimestamp(window_ends_epoch, tz=timezone.utc)
        expires_at = datetime.fromtimestamp(
            window_ends_epoch + RATE_LIMIT_COUNTER_RETENTION_SECONDS,
            tz=timezone.utc,
        )
        bucket_id = f"{normalized_operation}:{normalized_key_id}:{window_number}"

        self._maybe_cleanup_expired(now_epoch)

        try:
            self._collection.insert_one({
                "_id": bucket_id,
                "key_id": normalized_key_id,
                "operation": normalized_operation,
                "window_started_at": window_started_at,
                "window_ends_at": window_ends_at,
                "expires_at": expires_at,
                "count": 0,
            })
        except _DUPLICATE_KEY_ERRORS:
            pass
        except Exception as error:
            raise RateLimitStoreUnavailable(
                "Rate-limit storage is unavailable."
            ) from error

        try:
            result = self._collection.update_one(
                {"_id": bucket_id, "count": {"$lt": limit}},
                {"$inc": {"count": 1}},
            )
        except Exception as error:
            raise RateLimitStoreUnavailable(
                "Rate-limit storage is unavailable."
            ) from error

        modified_count = getattr(result, "modified_count", None)
        if modified_count not in {0, 1}:
            raise RateLimitStoreUnavailable(
                "Rate-limit storage returned an invalid update result."
            )

        try:
            counter = self._collection.find_one({"_id": bucket_id})
        except Exception as error:
            raise RateLimitStoreUnavailable(
                "Rate-limit storage is unavailable."
            ) from error

        count = counter.get("count") if isinstance(counter, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RateLimitStoreUnavailable(
                "Rate-limit storage returned an invalid counter."
            )

        return RateLimitDecision(
            allowed=modified_count == 1,
            limit=limit,
            remaining_requests=max(0, limit - count),
            retry_after_seconds=retry_after_seconds,
        )

    def _maybe_cleanup_expired(self, now_epoch: float) -> None:
        if not self._cleanup_expired or now_epoch < self._next_cleanup_at:
            return

        with self._cleanup_lock:
            if now_epoch < self._next_cleanup_at:
                return
            self._next_cleanup_at = now_epoch + self._cleanup_interval_seconds
            cutoff = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
            try:
                self._collection.delete_many({"expires_at": {"$lt": cutoff}})
            except Exception as error:
                self._logger.warning(
                    "rate_limit.cleanup_failed error_type=%s",
                    type(error).__name__,
                )
