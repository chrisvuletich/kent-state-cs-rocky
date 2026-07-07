from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.api_key_generator import generate_api_key_id
from backend.validation import normalize_str, validate_api_key_payload, validate_course_payload, validate_user_payload


def _insert_with_database_id(collection, document: dict[str, Any]) -> str:
    inserted_id = collection.insert_one(document).inserted_id
    database_id = str(inserted_id)
    collection.update_one({"_id": inserted_id}, {"$set": {"id": database_id}})
    return database_id


def _normalize_email(value: Any) -> str:
    return normalize_str(value).lower()


def _map_identity(value: Any, user_id_by_email: dict[str, str]) -> str:
    normalized_value = normalize_str(value)
    if not normalized_value:
        return ""
    return user_id_by_email.get(normalized_value.lower(), normalized_value)


def _prepare_course_payload(raw_course: dict[str, Any], user_id_by_email: dict[str, str]) -> dict[str, Any]:
    payload = dict(raw_course)

    instructor_email = _normalize_email(payload.get("instructor_email") or payload.get("instructorEmail"))
    if instructor_email and instructor_email in user_id_by_email:
        payload["instructor_id"] = user_id_by_email[instructor_email]

    if isinstance(payload.get("instructor_ids"), list) and not normalize_str(payload.get("instructor_id")):
        for candidate in payload.get("instructor_ids", []):
            mapped_candidate = _map_identity(candidate, user_id_by_email)
            if mapped_candidate:
                payload["instructor_id"] = mapped_candidate
                break

    members = payload.get("members") if isinstance(payload.get("members"), list) else []
    if members:
        normalized_members: list[dict[str, Any]] = []
        mapped_student_ids: list[str] = []
        for member in members:
            if not isinstance(member, dict):
                continue
            member_email = _normalize_email(member.get("email"))
            member_id = _map_identity(member.get("id") or member.get("memberId") or member.get("member_id"), user_id_by_email)
            if member_email and not member_id:
                member_id = user_id_by_email.get(member_email, "")
            normalized_member = {
                "id": member_id or None,
                "email": member_email,
                "key_limit": member.get("key_limit") if isinstance(member.get("key_limit"), int) else member.get("keyLimit") if isinstance(member.get("keyLimit"), int) else 1,
            }
            normalized_members.append(normalized_member)
            if member_id:
                mapped_student_ids.append(member_id)
        payload["members"] = normalized_members
        if mapped_student_ids:
            payload["student_ids"] = mapped_student_ids

    if isinstance(payload.get("student_ids"), list):
        normalized_student_ids: list[Any] = []
        for student_id in payload["student_ids"]:
            if isinstance(student_id, str):
                mapped_student_id = _map_identity(student_id, user_id_by_email)
                if mapped_student_id:
                    normalized_student_ids.append(mapped_student_id)
            else:
                normalized_student_ids.append(student_id)
        payload["student_ids"] = normalized_student_ids

    if isinstance(payload.get("ta_ids"), list):
        normalized_ta_ids: list[Any] = []
        for ta_id in payload["ta_ids"]:
            if isinstance(ta_id, str):
                mapped_ta_id = _map_identity(ta_id, user_id_by_email)
                if mapped_ta_id:
                    normalized_ta_ids.append(mapped_ta_id)
            else:
                normalized_ta_ids.append(ta_id)
        payload["ta_ids"] = normalized_ta_ids

    return payload


def _insert_static_collection(collection, rows: list[dict[str, Any]]) -> int:
    collection.delete_many({})
    if rows:
        collection.insert_many(rows)
    return len(rows)


def seed_database(collections, payload: dict[str, Any]) -> dict[str, int]:
    summary = {
        "users_inserted": 0,
        "users_rejected": 0,
        "courses_inserted": 0,
        "courses_rejected": 0,
        "api_keys_inserted": 0,
        "api_keys_rejected": 0,
    }

    collections.users.delete_many({})
    collections.whitelist_users.delete_many({})
    collections.courses.delete_many({})
    collections.api_keys.delete_many({})
    collections.api_history.delete_many({})

    for item in payload.get("users", []):
        cleaned, error = validate_user_payload(item)
        if error:
            summary["users_rejected"] += 1
            continue
        cleaned.pop("id", None)
        cleaned["created_at"] = datetime.now(timezone.utc).isoformat()
        inserted_id = _insert_with_database_id(collections.users, cleaned)
        cleaned["id"] = inserted_id
        summary["users_inserted"] += 1

    user_id_by_email = {
        _normalize_email(user.get("email")): normalize_str(user.get("id") or user.get("_id"))
        for user in collections.users.find()
        if _normalize_email(user.get("email")) and normalize_str(user.get("id") or user.get("_id"))
    }

    for item in payload.get("courses", []):
        course_payload = _prepare_course_payload(item, user_id_by_email)
        cleaned, error = validate_course_payload(course_payload)
        if error:
            summary["courses_rejected"] += 1
            continue
        collections.courses.insert_one(cleaned)
        summary["courses_inserted"] += 1

    for item in payload.get("api_keys", []):
        api_key_payload = dict(item)
        owner_value = normalize_str(api_key_payload.get("owner_id") or api_key_payload.get("u_id"))
        mapped_owner = user_id_by_email.get(owner_value.lower(), owner_value)
        if mapped_owner:
            api_key_payload["owner_id"] = mapped_owner
            api_key_payload["u_id"] = mapped_owner if normalize_str(api_key_payload.get("owner_type")).lower() != "group" else None

        cleaned, error = validate_api_key_payload(api_key_payload)
        if error:
            summary["api_keys_rejected"] += 1
            continue
        cleaned["key_id"] = normalize_str(cleaned.get("key_id")) or generate_api_key_id()
        slot_index = cleaned.get("slot_index") if isinstance(cleaned.get("slot_index"), int) else 1
        if slot_index < 1:
            slot_index = 1
        cleaned["slot_index"] = slot_index
        cleaned["key_name"] = f"key-{slot_index}"
        provided_created = item.get("created") if isinstance(item, dict) else None
        if isinstance(provided_created, str) and provided_created.strip():
            cleaned["created"] = provided_created.strip()
        else:
            cleaned["created"] = datetime.now(timezone.utc).isoformat()
        collections.api_keys.insert_one(cleaned)
        summary["api_keys_inserted"] += 1

    return summary


def seed_static_content(collections, read_seed_json) -> dict[str, int]:
    return {
        "analytics_kpis_inserted": _insert_static_collection(collections.analytics_kpis, read_seed_json("analytics", "kpis.json")),
        "analytics_activity_inserted": _insert_static_collection(collections.analytics_activity, read_seed_json("analytics", "activity.json")),
        "widgets_default_inserted": _insert_static_collection(collections.widgets_default, read_seed_json("widgets", "widgets.json")),
        "help_faq_inserted": _insert_static_collection(collections.help_faq, read_seed_json("help", "faq.json")),
    }
