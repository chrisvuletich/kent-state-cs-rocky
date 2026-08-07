from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.api_key_generator import generate_api_key_id, generate_api_key_pair
from backend.validation import is_valid_email, normalize_str, parse_semester

GROUP_ID_RE = re.compile(r"[^a-z0-9]+")


def _normalize_identifier_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = normalize_str(value).lower()
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


def _member_email(member: dict[str, Any]) -> str:
    return normalize_str(member.get("email")).lower()


def _member_identifier(member: dict[str, Any]) -> str:
    member_id = normalize_str(member.get("id")).lower()
    if member_id:
        return member_id
    return _member_email(member)


def _member_matches_identifier(member: dict[str, Any], identifier: str) -> bool:
    normalized_identifier = normalize_str(identifier).lower()
    if not normalized_identifier:
        return False
    return _member_identifier(member) == normalized_identifier or _member_email(member) == normalized_identifier


def course_matches_identifier(course: dict[str, Any], identifier: str) -> bool:
    if str(course.get("id")) == identifier:
        return True

    course_object_id = course.get("_id")
    return str(course_object_id) == identifier


def get_course_record(courses_collection, course_id: str):
    try:
        course = courses_collection.find_one({"_id": ObjectId(course_id)})
        if course:
            return course
    except (InvalidId, TypeError):
        pass

    for candidate in courses_collection.find():
        if course_matches_identifier(candidate, course_id):
            return candidate

    return None


def _set_course_member_lists(course: dict[str, Any]) -> None:
    members = course.get("members", []) if isinstance(course.get("members"), list) else []
    student_ids = []
    normalized_members = []

    for member in members:
        if not isinstance(member, dict):
            continue

        member_id = normalize_str(member.get("id"))
        email = _member_email(member)
        if member_id and email and member_id.lower() == email:
            member_id = ""
        name = normalize_str(member.get("name")) or None
        key_limit = member.get("key_limit")
        if not isinstance(key_limit, int) or key_limit < 0:
            key_limit = 1
        normalized = {
            "id": member_id or None,
            "email": email or None,
            "name": name,
            "key_limit": key_limit,
        }
        normalized_members.append(normalized)
        if member_id:
            student_ids.append(member_id)

    course["members"] = normalized_members
    course["student_ids"] = student_ids

    course["instructor_id"] = normalize_str(course.get("instructor_id")) or None
    instructor_email = normalize_str(course.get("instructor_email")).lower()
    course["instructor_email"] = instructor_email or None
    instructor_name = normalize_str(course.get("instructor"))
    course["instructor"] = instructor_name or "Unknown Instructor"
    course["ta_ids"] = _normalize_identifier_list(course.get("ta_ids"))
    course["ta_emails"] = _normalize_identifier_list(course.get("ta_emails"))

    instructor_identifiers = {
        normalize_str(course.get("instructor_id")).lower(),
        normalize_str(course.get("instructor_email")).lower(),
    }
    instructor_identifiers.discard("")
    course["ta_ids"] = [identifier for identifier in course["ta_ids"] if identifier not in instructor_identifiers]
    course["ta_emails"] = [identifier for identifier in course["ta_emails"] if identifier not in instructor_identifiers]

    instructor_key_limit = course.get("instructor_key_limit")
    if not isinstance(instructor_key_limit, int) or instructor_key_limit < 0:
        course["instructor_key_limit"] = 2

    course_handout_limit = course.get("instructor_handout_limit")
    if not isinstance(course_handout_limit, int) or course_handout_limit < 0:
        course["instructor_handout_limit"] = 2

    if not isinstance(course.get("is_active"), bool):
        course["is_active"] = True


def _lookup_user(users_collection, identifier: str):
    normalized_identifier = normalize_str(identifier)
    if not normalized_identifier:
        return None
    user = users_collection.find_one({"id": normalized_identifier})
    if user:
        return user
    normalized_identifier_lower = normalized_identifier.lower()
    for candidate in users_collection.find():
        if not isinstance(candidate, dict):
            continue
        candidate_id = normalize_str(candidate.get("id")).lower()
        if candidate_id and candidate_id == normalized_identifier_lower:
            return candidate
    if is_valid_email(normalized_identifier):
        return users_collection.find_one({"email": normalized_identifier.lower()})
    return None


def _is_course_admin(is_admin: bool) -> bool:
    return bool(is_admin)


def _is_course_instructor(course: dict[str, Any], requester_identifier: str) -> bool:
    normalized_identifier = requester_identifier.lower()
    if not normalized_identifier:
        return False
    instructor_identifiers = {
        normalize_str(course.get("instructor_id")).lower(),
        normalize_str(course.get("instructor_email")).lower(),
    }
    instructor_identifiers.discard("")
    return normalized_identifier in instructor_identifiers


def _is_course_ta(course: dict[str, Any], requester_identifier: str) -> bool:
    normalized_identifier = requester_identifier.lower()
    if not normalized_identifier:
        return False

    ta_identifiers = set(_normalize_identifier_list(course.get("ta_ids")))
    ta_identifiers.update(_normalize_identifier_list(course.get("ta_emails")))
    return normalized_identifier in ta_identifiers


def can_manage_people(course: dict[str, Any], requester_identifier: str, requester_is_admin: bool) -> bool:
    return _is_course_admin(requester_is_admin) or _is_course_instructor(course, requester_identifier) or _is_course_ta(course, requester_identifier)


def can_manage_metadata(requester_is_admin: bool) -> bool:
    return _is_course_admin(requester_is_admin)


def can_manage_api_keys(requester_is_admin: bool) -> bool:
    return _is_course_admin(requester_is_admin)


def can_request_api_key(course: dict[str, Any], requester_identifier: str, requester_is_admin: bool) -> bool:
    return _is_course_admin(requester_is_admin) or course_is_visible_to_requester(course, requester_identifier, requester_is_admin)


def course_is_visible_to_requester(course: dict[str, Any], requester_identifier: str, requester_is_admin: bool) -> bool:
    if _is_course_admin(requester_is_admin):
        return True
    return _is_course_instructor(course, requester_identifier) or _is_course_ta(course, requester_identifier) or any(
        _member_matches_identifier(member, requester_identifier)
        for member in course.get("members", [])
        if isinstance(member, dict)
    )


def filter_visible_courses(courses: list[dict[str, Any]], requester_identifier: str | None, requester_is_admin: bool) -> list[dict[str, Any]]:
    if requester_is_admin:
        return courses
    if not requester_identifier:
        return []
    return [course for course in courses if course_is_visible_to_requester(course, requester_identifier, requester_is_admin)]


def apply_course_metadata_patch(course: dict[str, Any], users_collection, payload: dict[str, Any]) -> dict[str, Any]:
    name = payload.get("name")
    code = payload.get("code")
    has_semester = "semester" in payload
    semester = payload.get("semester")
    color = payload.get("color")
    instructor_id = normalize_str(payload.get("instructorId") or payload.get("instructor_id"))
    instructor_email = normalize_str(payload.get("instructorEmail")).lower()
    ta_ids_payload = payload.get("taIds")
    if ta_ids_payload is None:
        ta_ids_payload = payload.get("ta_ids")

    if name is not None:
        course["name"] = normalize_str(name) or course.get("name", "Untitled Course")
    if code is not None:
        course["code"] = normalize_str(code) or course.get("code", "TBD 0000")
    if has_semester:
        parsed_semester, semester_error = parse_semester(semester)
        if semester_error:
            raise ValueError(semester_error)
        course["semester"] = parsed_semester["display"]
        course["semester_obj"] = None if parsed_semester["term"] == "none" else {"year": parsed_semester["year"], "term": parsed_semester["term"]}
    if color is not None:
        course["color"] = normalize_str(color) or course.get("color", "#1a4a8a")

    if instructor_id or instructor_email:
        identifier = instructor_id or instructor_email
        if identifier:
            user = _lookup_user(users_collection, identifier)
            if not user:
                raise ValueError("Instructor id must match an existing user.")
            instructor_name = f"{normalize_str(user.get('first_name'))} {normalize_str(user.get('last_name'))}".strip() or "Unknown Instructor"
            resolved_email = normalize_str(user.get("email")).lower()
            resolved_id = normalize_str(user.get("id"))
            course["instructor"] = instructor_name
            course["instructor_id"] = resolved_id or None
            course["instructor_email"] = resolved_email or None

    if ta_ids_payload is not None:
        if not isinstance(ta_ids_payload, list):
            raise ValueError("taIds must be a list.")

        resolved_ta_ids: list[str] = []
        resolved_ta_emails: list[str] = []
        seen_ta_ids: set[str] = set()
        seen_ta_emails: set[str] = set()
        for ta_identifier in ta_ids_payload:
            normalized_ta_identifier = normalize_str(ta_identifier)
            if not normalized_ta_identifier:
                continue

            ta_user = _lookup_user(users_collection, normalized_ta_identifier)
            if not ta_user:
                raise ValueError("Each teacher assistant must match an existing user.")

            resolved_ta_id = normalize_str(ta_user.get("id")).lower()
            resolved_ta_email = normalize_str(ta_user.get("email")).lower()

            if resolved_ta_id and resolved_ta_id not in seen_ta_ids:
                seen_ta_ids.add(resolved_ta_id)
                resolved_ta_ids.append(resolved_ta_id)
            if resolved_ta_email and resolved_ta_email not in seen_ta_emails:
                seen_ta_emails.add(resolved_ta_email)
                resolved_ta_emails.append(resolved_ta_email)

        course["ta_ids"] = resolved_ta_ids
        course["ta_emails"] = resolved_ta_emails

    _set_course_member_lists(course)
    return course


def add_course_members(course: dict[str, Any], users_collection, payload: Any, requester_is_admin: bool) -> dict[str, Any]:
    if isinstance(payload, dict) and "members" in payload:
        members_payload = payload.get("members")
    else:
        members_payload = payload

    if isinstance(members_payload, dict):
        members_payload = [members_payload]

    if not isinstance(members_payload, list):
        raise ValueError("members must be a list or member object.")

    existing_members: dict[str, dict[str, Any]] = {}
    for member in course.get("members", []):
        if not isinstance(member, dict):
            continue
        member_key = _member_email(member) or _member_identifier(member)
        if member_key:
            existing_members[member_key] = dict(member)

    for entry in members_payload:
        if not isinstance(entry, dict):
            raise ValueError("each member must be an object.")

        member_id = normalize_str(entry.get("id") or entry.get("memberId") or entry.get("member_id"))
        member_email = normalize_str(entry.get("email")).lower()
        if member_id and is_valid_email(member_id) and not member_email:
            member_email = member_id.lower()
            member_id = ""
        if not member_email and not member_id:
            raise ValueError("each member requires an email.")

        lookup_identifier = member_id or member_email
        user = _lookup_user(users_collection, lookup_identifier)
        if user:
            resolved_id = normalize_str(user.get("id")) or None
            resolved_email = normalize_str(user.get("email")).lower()
            name = f"{normalize_str(user.get('first_name'))} {normalize_str(user.get('last_name'))}".strip() or None
        else:
            if not is_valid_email(member_email or member_id):
                raise ValueError(f"Unknown user: {lookup_identifier}")

            resolved_email = (member_email or member_id).lower()
            resolved_id = None
            name = None

        member_key = resolved_email or resolved_id or lookup_identifier.lower()
        existing_member = existing_members.get(member_key, {})
        existing_members[member_key] = {
            "id": resolved_id if resolved_id else normalize_str(existing_member.get("id")) or None,
            "email": resolved_email,
            "name": name if name is not None else normalize_str(existing_member.get("name")) or None,
            "key_limit": existing_member.get("key_limit") if isinstance(existing_member.get("key_limit"), int) and existing_member.get("key_limit") > 0 else 1,
        }

    course["members"] = list(existing_members.values())
    _set_course_member_lists(course)
    return course


def reconcile_course_members_for_user(courses_collection, user_record: dict[str, Any]) -> int:
    user_email = normalize_str(user_record.get("email")).lower()
    user_id = normalize_str(user_record.get("id"))
    first_name = normalize_str(user_record.get("first_name"))
    last_name = normalize_str(user_record.get("last_name"))
    display_name = f"{first_name} {last_name}".strip() or None

    if not user_email:
        return 0

    updated_courses = 0
    for course in courses_collection.find():
        if not isinstance(course, dict):
            continue

        members = course.get("members")
        if not isinstance(members, list):
            continue

        changed = False
        for member in members:
            if not isinstance(member, dict):
                continue

            member_email = _member_email(member)
            member_id = normalize_str(member.get("id"))
            matches_user = member_email == user_email or (user_id and member_id == user_id)
            if not matches_user:
                continue

            if normalize_str(member.get("email")).lower() != user_email:
                member["email"] = user_email
                changed = True
            if user_id and member_id != user_id:
                member["id"] = user_id
                changed = True
            if display_name and normalize_str(member.get("name")) != display_name:
                member["name"] = display_name
                changed = True

        if changed:
            _set_course_member_lists(course)
            if "_id" in course:
                courses_collection.replace_one({"_id": course["_id"]}, course)
            elif isinstance(course.get("id"), int):
                courses_collection.replace_one({"id": course.get("id")}, course)
            updated_courses += 1

    return updated_courses


def remove_course_member(course: dict[str, Any], member_id: str, requester_is_admin: bool) -> dict[str, Any]:
    normalized_member_id = normalize_str(member_id)
    if not normalized_member_id:
        raise ValueError("id must be valid.")

    removed_member = next(
        (
            member
            for member in course.get("members", [])
            if isinstance(member, dict) and _member_matches_identifier(member, normalized_member_id)
        ),
        None,
    )

    course["members"] = [
        member
        for member in course.get("members", [])
        if not (isinstance(member, dict) and _member_matches_identifier(member, normalized_member_id))
    ]

    removed_member_email = _member_email(removed_member) if isinstance(removed_member, dict) else ""

    for group in course.get("groups", []):
        if not isinstance(group, dict):
            continue
        member_ids = [
            group_member_id
            for group_member_id in group.get("memberIds", [])
            if normalize_str(group_member_id).lower() not in {normalized_member_id.lower(), removed_member_email}
        ]
        group["memberIds"] = member_ids

    _set_course_member_lists(course)
    return course


def create_course_group(course: dict[str, Any], name: str, global_existing_ids: set[str] | None = None) -> dict[str, Any]:
    group_name = normalize_str(name)
    if not group_name:
        raise ValueError("group name is required.")

    safe_slug = GROUP_ID_RE.sub("-", group_name.lower()).strip("-") or "group"
    existing_ids = {
        normalize_str(group.get("id"))
        for group in course.get("groups", [])
        if isinstance(group, dict)
    }
    if isinstance(global_existing_ids, set):
        existing_ids = existing_ids | {normalize_str(value) for value in global_existing_ids}
    suffix = 1
    group_id = f"{safe_slug}-{suffix}"
    while group_id in existing_ids:
        suffix += 1
        group_id = f"{safe_slug}-{suffix}"

    course.setdefault("groups", [])
    course["groups"].append({"id": group_id, "name": group_name, "memberIds": [], "key_limit": 1})
    return course


def update_course_member_key_limit(course: dict[str, Any], member_id: str, key_limit: int) -> dict[str, Any]:
    normalized_member_id = normalize_str(member_id)
    if not normalized_member_id:
        raise ValueError("member id is required.")
    if not isinstance(key_limit, int) or key_limit < 0:
        raise ValueError("key_limit must be an integer >= 0.")

    student_key_limit = course.get("instructor_handout_limit")
    if not isinstance(student_key_limit, int) or student_key_limit < 0:
        student_key_limit = 2
    if key_limit > student_key_limit:
        raise ValueError("key_limit cannot exceed instructor_handout_limit.")

    updated = False
    for member in course.get("members", []):
        if isinstance(member, dict) and _member_matches_identifier(member, normalized_member_id):
            member["key_limit"] = key_limit
            updated = True
            break
    if not updated:
        raise ValueError("Member not found.")

    _set_course_member_lists(course)
    return course


def update_course_instructor_handout_limit(course: dict[str, Any], handout_limit: int) -> dict[str, Any]:
    if not isinstance(handout_limit, int) or handout_limit < 0:
        raise ValueError("instructor_handout_limit must be an integer >= 0.")

    course["instructor_handout_limit"] = handout_limit
    for member in course.get("members", []):
        if not isinstance(member, dict):
            continue
        current_limit = member.get("key_limit")
        if isinstance(current_limit, int) and current_limit >= 0:
            member["key_limit"] = min(current_limit, handout_limit)
    for group in course.get("groups", []):
        if not isinstance(group, dict):
            continue
        current_limit = group.get("key_limit")
        if isinstance(current_limit, int) and current_limit >= 0:
            group["key_limit"] = min(current_limit, handout_limit)
    _set_course_member_lists(course)
    return course


def update_course_instructor_key_limit(course: dict[str, Any], key_limit: int) -> dict[str, Any]:
    if not isinstance(key_limit, int) or key_limit < 0:
        raise ValueError("instructor_key_limit must be an integer >= 0.")

    course["instructor_key_limit"] = key_limit
    _set_course_member_lists(course)
    return course


def update_course_group_key_limit(course: dict[str, Any], group_id: str, key_limit: int) -> dict[str, Any]:
    normalized_group_id = normalize_str(group_id)
    if not normalized_group_id:
        raise ValueError("groupId is required.")
    if not isinstance(key_limit, int) or key_limit < 0:
        raise ValueError("key_limit must be an integer >= 0.")

    student_key_limit = course.get("instructor_handout_limit")
    if not isinstance(student_key_limit, int) or student_key_limit < 0:
        student_key_limit = 2
    if key_limit > student_key_limit:
        raise ValueError("key_limit cannot exceed instructor_handout_limit.")

    target_group = next(
        (group for group in course.get("groups", []) if isinstance(group, dict) and normalize_str(group.get("id")) == normalized_group_id),
        None,
    )
    if not target_group:
        raise ValueError("Group not found.")

    target_group["key_limit"] = key_limit
    return course


def add_group_member(course: dict[str, Any], group_id: str, member_id: str) -> dict[str, Any]:
    normalized_group_id = normalize_str(group_id)
    normalized_member_id = normalize_str(member_id).lower()
    if not normalized_group_id:
        raise ValueError("groupId is required.")
    if not normalized_member_id:
        raise ValueError("id must be valid.")

    group = next((group for group in course.get("groups", []) if isinstance(group, dict) and normalize_str(group.get("id")) == normalized_group_id), None)
    if not group:
        raise ValueError("Group not found.")

    target_member = next(
        (
            member
            for member in course.get("members", [])
            if isinstance(member, dict) and _member_matches_identifier(member, normalized_member_id)
        ),
        None,
    )
    target_email = _member_email(target_member) if isinstance(target_member, dict) else ""
    if not target_email:
        raise ValueError("Member must belong to the course.")

    member_ids = [normalize_str(group_member_id) for group_member_id in group.get("memberIds", [])]
    if target_email not in member_ids:
        member_ids.append(target_email)
    group["memberIds"] = member_ids
    return course


def remove_group_member(course: dict[str, Any], group_id: str, member_id: str) -> dict[str, Any]:
    normalized_group_id = normalize_str(group_id)
    normalized_member_id = normalize_str(member_id).lower()
    if not normalized_group_id:
        raise ValueError("groupId is required.")
    if not normalized_member_id:
        raise ValueError("id must be valid.")

    group = next((group for group in course.get("groups", []) if isinstance(group, dict) and normalize_str(group.get("id")) == normalized_group_id), None)
    if not group:
        raise ValueError("Group not found.")

    target_member = next(
        (
            member
            for member in course.get("members", [])
            if isinstance(member, dict) and _member_matches_identifier(member, normalized_member_id)
        ),
        None,
    )
    target_email = _member_email(target_member) if isinstance(target_member, dict) else normalized_member_id

    group["memberIds"] = [
        group_member_id
        for group_member_id in group.get("memberIds", [])
        if normalize_str(group_member_id).lower() != target_email
    ]
    return course


def regenerate_course_api_key(
    course: dict[str, Any],
    api_keys_collection,
    requester_identifier: str,
    ownership: dict[str, Any] | None = None,
) -> dict[str, Any]:
    course_code = normalize_str(course.get("code"))
    if not course_code:
        raise ValueError("Course code is required for API key management.")

    course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None

    normalized_requester = normalize_str(requester_identifier).lower()
    ownership_payload = ownership if isinstance(ownership, dict) else {}
    owner_type = normalize_str(ownership_payload.get("owner_type") or ownership_payload.get("subject_type")).lower() or "person"
    if owner_type not in {"person", "group"}:
        raise ValueError("owner_type must be either 'person' or 'group'.")

    owner_id = normalize_str(ownership_payload.get("owner_id") or ownership_payload.get("subject_id")).lower()
    key_name = normalize_str(ownership_payload.get("key_name") or ownership_payload.get("name") or "key-1")
    key_name = key_name[:64].strip() or "key-1"
    slot_index_raw = ownership_payload.get("slot_index")
    try:
        slot_index = int(slot_index_raw)
    except (TypeError, ValueError):
        slot_index = 0
    if slot_index < 1:
        slot_index = 1
    if owner_type == "group":
        if not owner_id:
            raise ValueError("group owner requires owner_id.")
    else:
        owner_id = owner_id or normalized_requester

    generated_key, generated_hash = generate_api_key_pair()

    created_by = normalize_str(ownership_payload.get("group_created_by") or ownership_payload.get("created_by")).lower()
    if not created_by and owner_type == "group":
        created_by = normalized_requester

    key_doc = {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "group_created_by": created_by or None,
        "key_name": key_name,
        "course_id": course_numeric_id,
        "hash": generated_hash,
        "is_active": True,
        "expire": None,
        "created": datetime.now(timezone.utc).isoformat(),
    }

    if course_numeric_id is None:
        key_doc["c_id"] = course_code

    lookup_filter: dict[str, Any] = {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "slot_index": slot_index,
    }
    if course_numeric_id is not None:
        lookup_filter["course_id"] = course_numeric_id
    else:
        lookup_filter["c_id"] = course_code

    existing = api_keys_collection.find_one(lookup_filter)
    if existing is None:
        existing = api_keys_collection.find_one(
            {
                **{k: v for k, v in lookup_filter.items() if k != "slot_index"},
                "key_name": key_name,
            }
        )

    existing_key_id = existing.get("key_id") if isinstance(existing, dict) else None
    key_id = normalize_str(existing_key_id) or generate_api_key_id()

    key_doc["slot_index"] = slot_index
    key_doc["key_id"] = key_id

    if existing is None:
        try:
            api_keys_collection.insert_one(key_doc)
        except DuplicateKeyError:
            existing = api_keys_collection.find_one(lookup_filter)
            if existing is None:
                existing = api_keys_collection.find_one(
                    {
                        **{k: v for k, v in lookup_filter.items() if k != "slot_index"},
                        "key_name": key_name,
                    }
                )
            if existing is None:
                raise
            existing_key_id = normalize_str(existing.get("key_id"))
            if existing_key_id:
                key_doc["key_id"] = existing_key_id
            key_doc["_id"] = existing.get("_id")
            api_keys_collection.replace_one({"_id": existing.get("_id")}, key_doc)
    else:
        key_doc["_id"] = existing.get("_id")
        api_keys_collection.replace_one({"_id": existing.get("_id")}, key_doc)

    return {
        "api_key": generated_key,
        "key_id": key_doc["key_id"],
        "owner_type": key_doc["owner_type"],
        "owner_id": key_doc["owner_id"],
        "group_created_by": key_doc["group_created_by"],
        "key_name": key_doc["key_name"],
        "slot_index": key_doc.get("slot_index"),
        "course_id": key_doc["course_id"],
        "created": key_doc["created"],
    }


def delete_course_api_keys(course: dict[str, Any], api_keys_collection) -> int:
    course_code = normalize_str(course.get("code"))
    if not course_code:
        raise ValueError("Course code is required for API key management.")

    deleted_count = 0
    course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None
    if course_numeric_id is not None:
        deleted_by_course_id = api_keys_collection.delete_many({"course_id": course_numeric_id})
        deleted_count += int(getattr(deleted_by_course_id, "deleted_count", 0))

    deleted_by_course_code = api_keys_collection.delete_many({"c_id": course_code})
    deleted_count += int(getattr(deleted_by_course_code, "deleted_count", 0))
    return deleted_count


def set_course_active_state(course: dict[str, Any], api_keys_collection, is_active: bool) -> dict[str, Any]:
    if not isinstance(is_active, bool):
        raise ValueError("is_active must be a boolean.")

    course["is_active"] = is_active

    course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None
    course_code = normalize_str(course.get("code"))
    key_filters: list[dict[str, Any]] = []
    if course_numeric_id is not None:
        key_filters.append({"course_id": course_numeric_id})
    if course_code:
        key_filters.append({"c_id": course_code})

    seen_ids: set[Any] = set()
    for lookup in key_filters:
        for key_entry in api_keys_collection.find(lookup):
            if not isinstance(key_entry, dict):
                continue
            key_entry_id = key_entry.get("_id")
            if key_entry_id in seen_ids:
                continue
            seen_ids.add(key_entry_id)
            updated_entry = dict(key_entry)
            if is_active:
                if updated_entry.get("disabled_reason") != "course":
                    continue
                updated_entry["is_active"] = True
                updated_entry.pop("disabled_reason", None)
            elif updated_entry.get("is_active", True) is not False:
                updated_entry["is_active"] = False
                updated_entry["disabled_reason"] = "course"
            else:
                continue
            api_keys_collection.replace_one({"_id": key_entry_id}, updated_entry)

    return course


def set_course_api_key_active_state(
    course: dict[str, Any],
    api_keys_collection,
    owner_type: str,
    owner_id: str,
    key_name: str,
    slot_index: int,
    is_active: bool,
) -> dict[str, Any]:
    normalized_owner_type = normalize_str(owner_type).lower() or "person"
    if normalized_owner_type not in {"person", "group"}:
        raise ValueError("owner_type must be either 'person' or 'group'.")

    normalized_owner_id = normalize_str(owner_id).lower()
    if not normalized_owner_id:
        raise ValueError("owner_id is required.")

    normalized_key_name = normalize_str(key_name)[:64].strip() or "key-1"
    if not isinstance(slot_index, int) or slot_index < 1:
        slot_index = 1
    if not isinstance(is_active, bool):
        raise ValueError("is_active must be a boolean.")

    course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None
    course_code = normalize_str(course.get("code"))
    if course_numeric_id is None and not course_code:
        raise ValueError("Course code is required for API key management.")

    lookup_filter: dict[str, Any] = {
        "owner_type": normalized_owner_type,
        "owner_id": normalized_owner_id,
        "slot_index": slot_index,
    }
    if course_numeric_id is not None:
        lookup_filter["course_id"] = course_numeric_id
    else:
        lookup_filter["c_id"] = course_code

    target_key = api_keys_collection.find_one(lookup_filter)
    if target_key is None:
        fallback_filter = dict(lookup_filter)
        fallback_filter.pop("slot_index", None)
        fallback_filter["key_name"] = normalized_key_name
        target_key = api_keys_collection.find_one(fallback_filter)
    if target_key is None:
        raise ValueError("API key not found.")

    updated_key = dict(target_key)
    updated_key["is_active"] = is_active
    if is_active:
        updated_key.pop("disabled_reason", None)
    else:
        updated_key["disabled_reason"] = "manual"
    api_keys_collection.replace_one({"_id": target_key.get("_id")}, updated_key)
    return updated_key
