from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "rocky-backend"
SEED_DATA_DIR = BACKEND_DIR / "seed-data"
FIXTURE_PATH = ROOT / "run-test" / "backend" / "seed_data.json"
USERS_FILE = BACKEND_DIR / "seed-data" / "account" / "users.json"
COURSES_FILE = BACKEND_DIR / "seed-data" / "courses" / "courses.json"
WIDGETS_FILE = BACKEND_DIR / "seed-data" / "widgets" / "widgets.json"
API_HISTORY_FILE = BACKEND_DIR / "seed-data" / "api_history.json"
ALLOWED_THEME_PREFERENCES = {"light", "dark"}

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SEED_DATA_DIR) not in sys.path:
	sys.path.insert(0, str(SEED_DATA_DIR))

from backend.api_key_generator import generate_api_key_id, generate_api_key_pair
from backend.storage import build_in_memory_collections
import main

logger = logging.getLogger("rocky.seed")


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_semester(raw: str) -> tuple[int, str]:
    value = (raw or "").strip()
    if not value:
        return datetime.now(timezone.utc).year, "spring"

    parts = value.split()
    if len(parts) != 2:
        return datetime.now(timezone.utc).year, "spring"

    term = parts[0].strip().lower()
    try:
        year = int(parts[1].strip())
    except ValueError:
        year = datetime.now(timezone.utc).year

    if term not in {"spring", "summer", "fall", "winter"}:
        term = "spring"

    return year, term


def _normalize_widget_list(raw_widgets, fallback_widgets):
    if not isinstance(raw_widgets, list):
        return [item.get("id") for item in fallback_widgets if isinstance(item, dict) and item.get("id")]

    widgets = []
    available_by_id = {
        (item.get("id") or "").strip().lower(): item
        for item in fallback_widgets
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    available_signatures = {
        (
            (item.get("title") or "").strip().lower() if isinstance(item, dict) else "",
            tuple(
                line.strip()
                for line in (item.get("lines") if isinstance(item, dict) and isinstance(item.get("lines"), list) else [])
                if isinstance(line, str) and line.strip()
            ),
        ): item
        for item in fallback_widgets
        if isinstance(item, dict)
    }
    for item in raw_widgets:
        widget_id = ""
        if isinstance(item, str):
            widget_id = item.strip().lower()
        elif isinstance(item, dict):
            widget_id = (item.get("widgetId") or item.get("id") or "").strip().lower() if isinstance(item.get("widgetId") or item.get("id"), str) else ""
        else:
            continue
        canonical_widget = available_by_id.get(widget_id)
        if canonical_widget is None:
            signature = (
                (item.get("title") or "").strip().lower() if isinstance(item.get("title"), str) else "",
                tuple(
                    line.strip()
                    for line in (item.get("lines") if isinstance(item.get("lines"), list) else [])
                    if isinstance(line, str) and line.strip()
                ),
            )
            canonical_widget = available_signatures.get(signature)
        if canonical_widget is not None:
            widgets.append((canonical_widget.get("id") or "").strip().lower())

    return widgets or [item.get("id") for item in fallback_widgets if isinstance(item, dict) and item.get("id")]


def _normalize_user_settings(raw_settings, fallback_widgets):
    theme = "light"
    if isinstance(raw_settings, dict):
        candidate_theme = (raw_settings.get("themePreference") or "").strip().lower()
        if candidate_theme in ALLOWED_THEME_PREFERENCES:
            theme = candidate_theme

    widgets = fallback_widgets
    if isinstance(raw_settings, dict):
        widgets = _normalize_widget_list(raw_settings.get("widgets"), fallback_widgets)

    return {"themePreference": theme, "widgets": widgets}


def seed_from_backend() -> dict[str, int]:
    raw_users = _load_json(USERS_FILE)
    raw_courses = _load_json(COURSES_FILE)
    raw_widgets = _load_json(WIDGETS_FILE)
    raw_api_history = _load_json(API_HISTORY_FILE)

    main.users.delete_many({})
    main.whitelist_users.delete_many({})
    main.courses.delete_many({})
    main.api_keys.delete_many({})
    main.api_history.delete_many({})

    users_inserted = 0
    courses_inserted = 0
    api_keys_inserted = 0
    api_history_inserted = 0
    for raw in raw_users:
        email = (raw.get("email") or "").strip().lower()
        if not email:
            continue

        raw_is_admin = raw.get("is_admin") if raw.get("is_admin") is not None else raw.get("isAdmin")
        is_admin = bool(raw_is_admin)
        raw_role = str(raw.get("role") or "").strip().lower()
        role = raw_role if raw_role in {"student", "instructor", "admin"} else ("admin" if is_admin else "student")
        is_admin = role == "admin"
        raw_is_active = raw.get("is_active") if raw.get("is_active") is not None else raw.get("isActive")
        is_active = True if raw_is_active is None else bool(raw_is_active)

        settings_payload = _normalize_user_settings(raw.get("settings"), raw_widgets)

        user_doc = {
            "first_name": (raw.get("first_name") or "").strip(),
            "last_name": (raw.get("last_name") or "").strip(),
            "email": email,
            "is_admin": is_admin,
            "role": role,
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "settings": settings_payload,
        }
        if not user_doc["first_name"] and not user_doc["last_name"]:
            fallback_name = (raw.get("name") or "Unknown User").strip()
            parts = [part for part in fallback_name.split() if part]
            user_doc["first_name"] = parts[0] if parts else "Unknown"
            user_doc["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else "User"
        inserted_id = main.users.insert_one(user_doc).inserted_id
        main.users.update_one({"_id": inserted_id}, {"$set": {"id": str(inserted_id)}})
        users_inserted += 1

    user_id_by_email = {
        (user.get("email") or "").strip().lower(): (user.get("id") or "").strip()
        for user in main.users.find()
        if (user.get("email") or "").strip() and (user.get("id") or "").strip()
    }

    used_course_ids: set[int] = set()
    used_group_ids: set[str] = set()

    for index, raw in enumerate(raw_courses, start=1):
        semester_raw = (raw.get("semester") or "Spring 2026").strip()
        year, term = _parse_semester(semester_raw)

        members = raw.get("members") if isinstance(raw.get("members"), list) else []
        instructor_id = (raw.get("instructor_id") or "").strip()
        instructor_email = (raw.get("instructor_email") or "").strip().lower()
        instructor_name = (raw.get("instructor") or "").strip()
        student_ids: list[str] = []
        normalized_members = []

        for member in members:
            account_email = (member.get("email") or "").strip().lower()
            if not account_email:
                continue
            member_id = user_id_by_email.get(account_email, "")
            if not member_id:
                continue

            is_instructor_member = (
                bool(instructor_email and account_email == instructor_email)
                or bool(instructor_id and member_id.lower() == instructor_id.lower())
            )
            if is_instructor_member:
                instructor_id = member_id
                instructor_email = account_email
                if not instructor_name:
                    matched_user = main.users.find_one({"id": member_id})
                    if matched_user:
                        first_name = (matched_user.get("first_name") or "").strip()
                        last_name = (matched_user.get("last_name") or "").strip()
                        instructor_name = " ".join(part for part in [first_name, last_name] if part).strip()
                continue

            normalized_members.append(
                {
                    "id": member_id,
                    "email": account_email,
                    "key_limit": 1,
                }
            )
            student_ids.append(member_id)

        if not instructor_id and instructor_email:
            fallback_instructor_id = user_id_by_email.get(instructor_email, "")
            if fallback_instructor_id:
                instructor_id = fallback_instructor_id

        if instructor_id and not instructor_email:
            matched_user = main.users.find_one({"id": instructor_id})
            if matched_user:
                instructor_email = (matched_user.get("email") or "").strip().lower()
                if not instructor_name:
                    first_name = (matched_user.get("first_name") or "").strip()
                    last_name = (matched_user.get("last_name") or "").strip()
                    instructor_name = " ".join(part for part in [first_name, last_name] if part).strip()

        instructor_key_limit = raw.get("instructor_key_limit")
        if not isinstance(instructor_key_limit, int) or instructor_key_limit < 0:
            instructor_key_limit = 2

        member_emails_in_course = {
            (member.get("email") or "").strip().lower()
            for member in normalized_members
            if isinstance(member, dict) and (member.get("email") or "").strip()
        }

        raw_groups = raw.get("groups") if isinstance(raw.get("groups"), list) else []
        normalized_groups = []
        for group in raw_groups:
            if not isinstance(group, dict):
                continue
            raw_group_id = (group.get("id") or "").strip().lower()
            if not raw_group_id:
                continue
            unique_group_id = raw_group_id
            suffix = 2
            while unique_group_id in used_group_ids:
                unique_group_id = f"{raw_group_id}-{suffix}"
                suffix += 1

            member_ids = []
            for group_member in group.get("memberIds", []):
                value = (group_member or "").strip().lower() if isinstance(group_member, str) else ""
                if not value:
                    continue
                if value in member_emails_in_course:
                    member_ids.append(value)

            normalized_groups.append(
                {
                    "id": unique_group_id,
                    "name": (group.get("name") or "").strip(),
                    "memberIds": member_ids,
                    "key_limit": 1,
                }
            )
            used_group_ids.add(unique_group_id)

        requested_course_id = raw.get("id") if isinstance(raw.get("id"), int) else index
        course_id = requested_course_id
        while course_id in used_course_ids:
            course_id += 1
        used_course_ids.add(course_id)

        course_doc = {
            "id": course_id,
            "code": (raw.get("code") or f"TBD {1000 + index}").strip(),
            "name": (raw.get("name") or "Untitled Course").strip(),
            "instructor": instructor_name or "Unknown Instructor",
            "instructor_id": instructor_id or None,
            "instructor_email": instructor_email or None,
            "instructor_key_limit": instructor_key_limit,
            "semester": semester_raw,
            "color": (raw.get("color") or "#1a4a8a").strip(),
            "is_active": True,
            "members": normalized_members,
            "groups": normalized_groups,
            "student_ids": student_ids,
            "semester_obj": {"year": year, "term": term},
        }

        main.courses.insert_one(course_doc)
        courses_inserted += 1

        if instructor_id:
            _, generated_hash = generate_api_key_pair()

            seeded_owner_type = "person"
            seeded_owner_id = instructor_id.lower()
            seeded_group_created_by = None

            if normalized_groups:
                primary_group = normalized_groups[0]
                seeded_owner_type = "group"
                seeded_owner_id = (primary_group.get("id") or "").strip().lower()
                primary_group_member_ids = primary_group.get("memberIds") if isinstance(primary_group.get("memberIds"), list) else []
                if primary_group_member_ids:
                    seeded_group_created_by = (primary_group_member_ids[0] or "").strip().lower() or instructor_id.lower()
                else:
                    seeded_group_created_by = instructor_id.lower()

            key_doc = {
                "key_id": generate_api_key_id(),
                "owner_type": seeded_owner_type,
                "owner_id": seeded_owner_id,
                "group_created_by": seeded_group_created_by,
                "key_name": "key-1",
                "slot_index": 1,
                "course_id": course_doc["id"],
                "hash": generated_hash,
                "is_active": True,
                "expire": None,
                "created": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            }
            main.api_keys.insert_one(key_doc)
            api_keys_inserted += 1

    for raw in raw_api_history:
        history_doc = {
            "u_id": (raw.get("u_id") or "").strip(),
            "c_id": (raw.get("c_id") or "").strip(),
            "course_id": raw.get("course_id"),
            "event_type": (raw.get("event_type") or "request").strip(),
            "group_id": (raw.get("group_id") or None),
            "group_name": (raw.get("group_name") or None),
            "is_group_member": bool(raw.get("is_group_member")),
            "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
            "created": (raw.get("created") or datetime.now(timezone.utc).isoformat()).strip(),
        }
        if history_doc["u_id"] and "@" in history_doc["u_id"]:
            history_doc["u_id"] = user_id_by_email.get(history_doc["u_id"].lower(), "")

        if not history_doc["u_id"] or not history_doc["c_id"]:
            continue
        main.api_history.insert_one(history_doc)
        api_history_inserted += 1

    static_summary = main.seed_static_content()

    return {
        "users_inserted": users_inserted,
        "courses_inserted": courses_inserted,
        "api_keys_inserted": api_keys_inserted,
        "api_history_inserted": api_history_inserted,
        **static_summary,
    }


def use_in_memory_db() -> None:
    """Route backend collections to an isolated in-memory database for tests."""
    test_collections = build_in_memory_collections()
    main.collections = test_collections
    main.users = test_collections.users
    main.whitelist_users = test_collections.whitelist_users
    main.courses = test_collections.courses
    main.api_keys = test_collections.api_keys
    main.api_history = test_collections.api_history
    main.telemetry_interactions = test_collections.telemetry_interactions
    main.telemetry_current = test_collections.telemetry_current
    main.telemetry_hardware = test_collections.telemetry_hardware
    main.analytics_kpis = test_collections.analytics_kpis
    main.analytics_activity = test_collections.analytics_activity
    main.widgets_default = test_collections.widgets_default
    main.help_faq = test_collections.help_faq


def load_seed_fixture(path: Path = FIXTURE_PATH) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def seed_backend_from_fixture(path: Path = FIXTURE_PATH) -> dict[str, int]:
    payload = load_seed_fixture(path)
    return main.seed_database(payload)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = seed_from_backend()
    logger.info("[seed] Seeded backend from backend fixture data: %s", summary)
