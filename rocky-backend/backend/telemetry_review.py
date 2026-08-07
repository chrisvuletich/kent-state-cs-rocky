from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


REVIEW_STATUSES = {"unreviewed", "in_review", "resolved"}
REVIEW_REASONS = {
    "academic_integrity",
    "harmful_content",
    "security_abuse",
    "policy_violation",
    "system_quality",
    "other",
}
MAX_REVIEW_NOTES = 4_000


class ReviewValidationError(ValueError):
    pass


def default_review():
    return {
        "version": 0,
        "flagged": False,
        "flag_reasons": [],
        "status": "unreviewed",
        "reviewed_by": None,
        "reviewed_at": None,
        "notes": None,
    }


def normalize_existing_review(value: Any):
    review = default_review()
    if isinstance(value, dict):
        review.update({
            key: deepcopy(value[key])
            for key in review
            if key in value
        })
    if review["status"] not in REVIEW_STATUSES:
        review["status"] = "unreviewed"
    if not isinstance(review["version"], int) or review["version"] < 0:
        review["version"] = 0
    if not isinstance(review["flag_reasons"], list):
        review["flag_reasons"] = []
    return review


def validate_review_patch(payload: Any, current: Any, reviewer: dict[str, Any],
                          reviewed_at: datetime | None = None):
    if not isinstance(payload, dict):
        raise ReviewValidationError("Request body must be a JSON object.")
    allowed = {"flagged", "flag_reasons", "status", "notes"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ReviewValidationError(
            f"Unsupported review field: {unknown[0]}."
        )
    if not payload:
        raise ReviewValidationError("At least one review field is required.")

    review = normalize_existing_review(current)
    if "flagged" in payload:
        if not isinstance(payload["flagged"], bool):
            raise ReviewValidationError("flagged must be a boolean.")
        review["flagged"] = payload["flagged"]

    if "flag_reasons" in payload:
        reasons = payload["flag_reasons"]
        if not isinstance(reasons, list) or not all(
            isinstance(reason, str) for reason in reasons
        ):
            raise ReviewValidationError("flag_reasons must be a list of strings.")
        normalized_reasons = list(dict.fromkeys(
            reason.strip().lower() for reason in reasons if reason.strip()
        ))
        unsupported = sorted(set(normalized_reasons) - REVIEW_REASONS)
        if unsupported:
            raise ReviewValidationError(
                f"Unsupported flag reason: {unsupported[0]}."
            )
        review["flag_reasons"] = normalized_reasons

    if "status" in payload:
        status = payload["status"]
        if not isinstance(status, str) or status.strip().lower() not in REVIEW_STATUSES:
            raise ReviewValidationError(
                "status must be unreviewed, in_review, or resolved."
            )
        review["status"] = status.strip().lower()

    if "notes" in payload:
        notes = payload["notes"]
        if notes is not None and not isinstance(notes, str):
            raise ReviewValidationError("notes must be a string or null.")
        normalized_notes = notes.strip() if isinstance(notes, str) else ""
        if len(normalized_notes) > MAX_REVIEW_NOTES:
            raise ReviewValidationError(
                f"notes cannot exceed {MAX_REVIEW_NOTES} characters."
            )
        review["notes"] = normalized_notes or None

    if not review["flagged"]:
        review["flag_reasons"] = []
    elif not review["flag_reasons"]:
        raise ReviewValidationError(
            "At least one flag reason is required for a flagged request."
        )

    timestamp = reviewed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    review["reviewed_at"] = timestamp.astimezone(timezone.utc)
    review["reviewed_by"] = {
        "user_id": reviewer.get("user_id"),
        "email": reviewer.get("email"),
    }
    return review
