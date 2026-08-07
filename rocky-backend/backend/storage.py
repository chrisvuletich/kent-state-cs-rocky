from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mongita import MongitaClientDisk, MongitaClientMemory
from pymongo import MongoClient

from .config import Settings


@dataclass
class Collections:
    users: any
    whitelist_users: any
    courses: any
    api_keys: any
    api_history: any
    telemetry_interactions: any
    telemetry_current: any
    telemetry_hardware: any
    analytics_kpis: any
    analytics_activity: any
    widgets_default: any
    help_faq: any


def _from_db(db) -> Collections:
    return Collections(
        users=db["users"],
        whitelist_users=db["whitelist_users"],
        courses=db["courses"],
        api_keys=db["api_keys"],
        api_history=db["api_history"],
        telemetry_interactions=db["telemetry_interactions"],
        telemetry_current=db["telemetry_current"],
        telemetry_hardware=db["telemetry_hardware"],
        analytics_kpis=db["analytics_kpis"],
        analytics_activity=db["analytics_activity"],
        widgets_default=db["widgets_default"],
        help_faq=db["help_faq"],
    )


def _create_index(collection, keys, **kwargs) -> None:
    try:
        collection.create_index(keys, **kwargs)
    except Exception:
        # Index support varies between MongoDB and the local Mongita fallback.
        pass


def ensure_indexes(collections: Collections) -> None:
    _create_index(
        collections.telemetry_interactions,
        [("received_at", -1)],
        name="telemetry_received_at",
    )
    _create_index(
        collections.telemetry_interactions,
        [("actor.user_id", 1), ("received_at", -1)],
        name="telemetry_actor_received_at",
    )
    _create_index(
        collections.telemetry_interactions,
        [("course.course_id", 1), ("received_at", -1)],
        name="telemetry_course_received_at",
    )
    _create_index(
        collections.telemetry_interactions,
        [("outcome", 1), ("received_at", -1)],
        name="telemetry_outcome_received_at",
    )
    _create_index(
        collections.telemetry_interactions,
        [("review.status", 1), ("received_at", -1)],
        name="telemetry_review_status_received_at",
    )
    _create_index(
        collections.telemetry_interactions,
        [("review.flagged", 1), ("received_at", -1)],
        name="telemetry_review_received_at",
    )
    _create_index(
        collections.telemetry_hardware,
        [("sampled_at", -1)],
        name="telemetry_hardware_sampled_at",
    )
    _create_index(
        collections.telemetry_hardware,
        [("expires_at", 1)],
        name="telemetry_hardware_expiry",
        expireAfterSeconds=0,
    )
    _create_index(
        collections.api_keys,
        [("course_id", 1), ("owner_type", 1), ("owner_id", 1), ("slot_index", 1)],
        unique=True,
        partialFilterExpression={"course_id": {"$exists": True}},
    )
    _create_index(
        collections.api_keys,
        [("c_id", 1), ("owner_type", 1), ("owner_id", 1), ("slot_index", 1)],
        unique=True,
        partialFilterExpression={"c_id": {"$exists": True}},
    )
    _create_index(
        collections.api_keys,
        [("hash", 1)],
        unique=True,
        partialFilterExpression={"hash": {"$exists": True, "$gt": ""}},
    )
    _create_index(
        collections.api_keys,
        [("key_id", 1)],
        unique=True,
        partialFilterExpression={"key_id": {"$exists": True, "$gt": ""}},
    )
    _create_index(
        collections.api_keys,
        [("key_scope", 1), ("owner_type", 1), ("owner_id", 1), ("key_name", 1)],
        unique=True,
        partialFilterExpression={"key_scope": "user-default"},
    )


def build_collections(settings: Settings) -> Collections:
    if settings.db_backend == "mongodb" or settings.app_env == "production":
        if not settings.mongodb_uri:
            raise RuntimeError("ROCKY_MONGODB_URI is required for the MongoDB backend")
        client = MongoClient(settings.mongodb_uri)
        db = client[settings.db_name]
        collections = _from_db(db)
        ensure_indexes(collections)
        return collections

    if settings.db_backend != "mongita":
        raise RuntimeError(
            f"Unsupported ROCKY_DB_BACKEND value: {settings.db_backend!r}. "
            "Expected 'mongodb' or 'mongita'."
        )

    Path(settings.mongita_path).mkdir(parents=True, exist_ok=True)
    client = MongitaClientDisk(settings.mongita_path)
    db = client[settings.db_name]
    collections = _from_db(db)
    ensure_indexes(collections)
    return collections


def build_in_memory_collections(db_name: str = "rocky_test_db") -> Collections:
    client = MongitaClientMemory()
    db = client[db_name]
    collections = _from_db(db)
    ensure_indexes(collections)
    return collections
