from __future__ import annotations

from typing import Any
import os
import secrets

from flask import request


INTERNAL_PROXY_HEADER = "X-Rocky-Internal-Secret"


def has_trusted_proxy() -> bool:
    configured = os.getenv("ROCKY_INTERNAL_PROXY_SECRET", "").strip()
    if not configured:
        return os.getenv("ROCKY_APP_ENV", "development").strip().lower() != "production"
    provided = request.headers.get(INTERNAL_PROXY_HEADER, "")
    return secrets.compare_digest(provided, configured)


def require_internal_proxy() -> tuple[bool, tuple[dict[str, Any], int] | None]:
    if not has_trusted_proxy():
        return False, ({"error": "Trusted proxy access is required."}, 403)
    return True, None


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_requester() -> tuple[str | None, bool]:
    if not has_trusted_proxy():
        return None, False
    email = request.headers.get("X-Rocky-User-Email", "").strip().lower() or None
    is_admin = _parse_bool(request.headers.get("X-Rocky-User-Is-Admin"))
    return email, is_admin


def require_admin() -> tuple[bool, tuple[dict[str, Any], int] | None]:
    email, is_admin = get_requester()
    if not is_admin:
        return False, ({"error": "Admin access is required."}, 403)
    if not email:
        return False, ({"error": "Authentication headers are required."}, 401)
    return True, None


def require_requester_identity() -> tuple[str, bool] | tuple[None, tuple[dict[str, Any], int]]:
    email, is_admin = get_requester()
    if not email:
        return None, ({"error": "Authentication headers are required."}, 401)
    return email, is_admin


def authorize_scope(email: str, is_admin: bool, scope: str, user_id: str | None = None) -> tuple[bool, tuple[dict[str, Any], int] | None]:
    if is_admin:
        return True, None

    allowed_scopes = {f"email:{email}"}
    if user_id:
        allowed_scopes.add(f"id:{user_id.strip().lower()}")

    if scope not in allowed_scopes:
        return False, ({"error": "You may only access your own settings."}, 403)

    return True, None


def filter_courses_for_requester(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    email, is_admin = get_requester()
    if is_admin:
        return courses

    if not email:
        return []

    filtered = []
    for course in courses:
        member_emails = {
            (member.get("email") or "").strip().lower()
            for member in course.get("members", [])
            if isinstance(member, dict)
        }
        if email in member_emails:
            filtered.append(course)
    return filtered
