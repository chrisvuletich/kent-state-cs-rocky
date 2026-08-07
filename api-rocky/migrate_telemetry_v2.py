"""Migrate Rocky telemetry to permanent schema-versioned request records."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

from telemetry import TelemetryStore


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = Path(__file__).resolve().parent
TTL_INDEX_NAME = "telemetry_terminal_expiry"


def load_environment() -> None:
    load_dotenv(REPOSITORY_ROOT / ".env", override=False)
    load_dotenv(REPOSITORY_ROOT / ".env.local", override=True)
    load_dotenv(SERVICE_ROOT / ".env", override=False)
    load_dotenv(SERVICE_ROOT / ".env.local", override=True)


def migrate(interactions, current, *, dry_run: bool = False) -> dict[str, int | bool]:
    expiring_documents = interactions.count_documents(
        {"expires_at": {"$exists": True}}
    )
    legacy_documents = interactions.count_documents(
        {"schema_version": {"$exists": False}}
    )
    index_information = interactions.index_information()
    ttl_index_present = TTL_INDEX_NAME in index_information

    result: dict[str, int | bool] = {
        "expiring_documents": expiring_documents,
        "legacy_documents": legacy_documents,
        "ttl_index_present": ttl_index_present,
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    if expiring_documents:
        interactions.update_many(
            {"expires_at": {"$exists": True}},
            {"$unset": {"expires_at": ""}},
        )
    if legacy_documents:
        interactions.update_many(
            {"schema_version": {"$exists": False}},
            {"$set": {
                "schema_version": 1,
                "content_available": False,
            }},
        )
    if ttl_index_present:
        interactions.drop_index(TTL_INDEX_NAME)

    if not TelemetryStore(interactions, current).ensure_indexes():
        raise RuntimeError("Unable to create schema-v2 telemetry indexes.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove Rocky telemetry expiration and mark legacy records."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report affected records without changing MongoDB.",
    )
    args = parser.parse_args()

    load_environment()
    if os.getenv("ROCKY_DB_BACKEND", "").strip().lower() != "mongodb":
        raise RuntimeError("The telemetry migration requires ROCKY_DB_BACKEND=mongodb.")
    mongodb_uri = os.getenv("ROCKY_MONGODB_URI", "").strip()
    database_name = os.getenv("ROCKY_DB_NAME", "").strip()
    if not mongodb_uri or not database_name:
        raise RuntimeError("ROCKY_MONGODB_URI and ROCKY_DB_NAME are required.")

    client = MongoClient(
        mongodb_uri,
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
    )
    try:
        client.admin.command("ping")
        database = client[database_name]
        result = migrate(
            database["telemetry_interactions"],
            database["telemetry_current"],
            dry_run=args.dry_run,
        )
    finally:
        client.close()

    for key in (
        "dry_run",
        "expiring_documents",
        "legacy_documents",
        "ttl_index_present",
    ):
        print(f"{key}={result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
