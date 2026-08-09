from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


# Keep this list short and focused on the records needed to prove that a Rocky
# restore contains its accounts, authorization data, and institutional audit
# history. Add a row here when a new durable collection becomes important.
IMPORTANT_COLLECTIONS: tuple[tuple[str, str], ...] = (
    ("users", "users"),
    ("whitelist_users", "whitelist_users"),
    ("courses", "courses"),
    ("api_keys", "api_keys"),
    ("api_history", "api_history"),
    ("telemetry_interactions", "telemetry_interactions"),
    ("telemetry_current", "telemetry_current"),
    ("telemetry_hardware", "telemetry_hardware"),
    ("conversations", "conversations"),
    ("messages", "messages"),
    ("responses", "responses"),
)


@dataclass(frozen=True)
class DatabaseCount:
    collection: str
    documents: int


def collect_database_counts(collections: Any) -> list[DatabaseCount]:
    """Return deterministic document counts for Rocky's durable collections."""

    counts: list[DatabaseCount] = []
    for attribute, collection_name in IMPORTANT_COLLECTIONS:
        collection = getattr(collections, attribute)
        counts.append(
            DatabaseCount(
                collection=collection_name,
                documents=int(collection.count_documents({})),
            )
        )
    return counts


def render_database_counts(counts: Iterable[DatabaseCount]) -> list[str]:
    return [f"{count.collection:<24} {count.documents:>12,}" for count in counts]
