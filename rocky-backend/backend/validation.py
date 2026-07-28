from __future__ import annotations

from datetime import datetime
from typing import Any

SEMESTER_YEAR_MIN = 2000
SEMESTER_YEAR_MAX = 2200
ALLOWED_TERMS = {"none", "spring", "summer", "fall"}
COURSE_COLOR_DEFAULT = "#7b2d8b"


def normalize_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def is_valid_email(value: Any) -> bool:
    email = normalize_str(value).lower()
    if not email or " " in email or email.count("@") != 1:
        return False

    local_part, domain_part = email.split("@", 1)
    if not local_part or not domain_part or "." not in domain_part:
        return False
    if local_part.startswith(".") or local_part.endswith("."):
        return False
    if domain_part.startswith(".") or domain_part.endswith("."):
        return False
    return all(label for label in domain_part.split("."))


def semester_display(term: str, year: int) -> str:
    if term == "none":
        return "None"
    return f"{term.capitalize()} {year}"


def parse_semester(value: Any):
    if value is None:
        return {"year": None, "term": "none", "display": None}, None

    if isinstance(value, dict):
        year = value.get("year")
        term = normalize_str(value.get("term")).lower()
        if term not in ALLOWED_TERMS:
            allowed_terms = ", ".join(sorted(ALLOWED_TERMS))
            return None, f"semester.term must be one of: {allowed_terms}."
        if term == "none":
            return {"year": None, "term": "none", "display": None}, None
        if not isinstance(year, int) or year < SEMESTER_YEAR_MIN or year > SEMESTER_YEAR_MAX:
            return None, f"semester.year must be an integer between {SEMESTER_YEAR_MIN} and {SEMESTER_YEAR_MAX}."
        return {"year": year, "term": term, "display": semester_display(term, year)}, None

    if isinstance(value, str):
        parts = value.strip().split()
        if len(parts) == 1 and parts[0].lower() == "none":
            return {"year": None, "term": "none", "display": None}, None
        if len(parts) != 2:
            return None, "semester string must look like 'Fall 2026'."
        term = parts[0].lower()
        try:
            year = int(parts[1])
        except ValueError:
            return None, "semester year in string format must be an integer."
        if term not in ALLOWED_TERMS:
            allowed_terms = ", ".join(sorted(ALLOWED_TERMS))
            return None, f"semester term in string format must be one of: {allowed_terms}."
        if term == "none":
            return {"year": None, "term": "none", "display": None}, None
        if year < SEMESTER_YEAR_MIN or year > SEMESTER_YEAR_MAX:
            return None, f"semester year in string format must be between {SEMESTER_YEAR_MIN} and {SEMESTER_YEAR_MAX}."
        return {"year": year, "term": term, "display": semester_display(term, year)}, None

    return None, "semester must be either an object {year, term} or a string like 'Fall 2026'."


def normalize_course_members(value: Any):
    if value is None:
        return [], [], None
    if not isinstance(value, list):
        return None, None, "members must be a list."

    members = []
    student_ids = []
    for entry in value:
        if not isinstance(entry, dict):
            return None, None, "each member must be an object."

        member_id = normalize_str(entry.get("id") or entry.get("memberId") or entry.get("member_id"))
        account_email = normalize_str(entry.get("email")).lower()
        if not member_id and not account_email:
            return None, None, "each member must include an id or email."
        if account_email and not is_valid_email(account_email):
            return None, None, "member email must be valid when provided."

        key_limit = entry.get("key_limit")
        if key_limit is None:
            key_limit = entry.get("keyLimit")
        if key_limit is None:
            key_limit = 1
        if not isinstance(key_limit, int) or key_limit < 0:
            return None, None, "member key_limit must be an integer >= 0."

        normalized = {
            "id": member_id or None,
            "email": account_email,
            "key_limit": key_limit,
        }
        members.append(normalized)
        if member_id:
            student_ids.append(member_id)

    return members, student_ids, None


def normalize_course_groups(value: Any):
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, "groups must be a list."

    groups = []
    for index, entry in enumerate(value, start=1):
        if not isinstance(entry, dict):
            return None, "each group must be an object."

        group_id = normalize_str(entry.get("id")) or f"group-{index}"
        name = normalize_str(entry.get("name"))
        if not name:
            return None, "each group requires a name."

        member_ids = entry.get("memberIds")
        if not isinstance(member_ids, list):
            return None, "group.memberIds must be a list."

        normalized_ids = []
        for member_id in member_ids:
            member_id_value = normalize_str(member_id)
            if not member_id_value:
                return None, "group.memberIds entries must be non-empty strings."
            normalized_ids.append(member_id_value)

        key_limit = entry.get("key_limit")
        if key_limit is None:
            key_limit = entry.get("keyLimit")
        if key_limit is None:
            key_limit = 1
        if not isinstance(key_limit, int) or key_limit < 0:
            return None, "group key_limit must be an integer >= 0."

        groups.append({"id": group_id, "name": name, "memberIds": normalized_ids, "key_limit": key_limit})

    return groups, None


def validate_user_payload(payload: Any):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."

    first_name = normalize_str(payload.get("first_name") or payload.get("firstName"))
    last_name = normalize_str(payload.get("last_name") or payload.get("lastName"))
    email = normalize_str(payload.get("email")).lower()
    user_id = normalize_str(payload.get("id"))
    raw_is_admin = payload.get("is_admin") if "is_admin" in payload else payload.get("isAdmin")
    if raw_is_admin is None:
        is_admin = False
    elif isinstance(raw_is_admin, bool):
        is_admin = raw_is_admin
    else:
        return None, "is_admin must be a boolean."

    raw_role = normalize_str(payload.get("role")).lower()
    if raw_role and raw_role not in {"student", "instructor", "admin"}:
        return None, "role must be one of: student, instructor, admin."
    role = raw_role or ("admin" if is_admin else "student")
    is_admin = role == "admin"

    raw_is_active = payload.get("is_active") if "is_active" in payload else payload.get("isActive")
    if raw_is_active is None:
        is_active = True
    elif isinstance(raw_is_active, bool):
        is_active = raw_is_active
    else:
        return None, "is_active must be a boolean."

    if not first_name:
        return None, "User first_name is required."
    if not last_name:
        return None, "User last_name is required."
    if not is_valid_email(email):
        return None, "A valid user email is required."
    cleaned = {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "is_admin": is_admin,
        "role": role,
        "is_active": is_active,
    }

    return cleaned, None


def validate_course_payload(payload: Any):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."

    name = normalize_str(payload.get("name"))
    parsed_semester, semester_error = parse_semester(payload.get("semester"))
    if semester_error:
        return None, semester_error

    if not name:
        return None, "Course name is required."

    members, member_students, member_error = normalize_course_members(payload.get("members"))
    if member_error:
        return None, member_error

    groups, groups_error = normalize_course_groups(payload.get("groups"))
    if groups_error:
        return None, groups_error

    member_identifiers = {
        normalize_str(member.get("id")).lower()
        for member in members
        if isinstance(member, dict) and normalize_str(member.get("id"))
    }
    member_identifiers.update(
        normalize_str(member.get("email")).lower()
        for member in members
        if isinstance(member, dict) and normalize_str(member.get("email"))
    )
    for group in groups:
        if not isinstance(group, dict):
            continue
        unknown_member_emails = [
            normalize_str(group_member).lower()
            for group_member in group.get("memberIds", [])
            if normalize_str(group_member).lower() not in member_identifiers
        ]
        if unknown_member_emails:
            return None, "group.memberIds must reference emails in course members."

    instructor_id = normalize_str(payload.get("instructor_id") or payload.get("instructorId"))
    if not instructor_id:
        instructor_ids = payload.get("instructor_ids")
        if isinstance(instructor_ids, list):
            for candidate in instructor_ids:
                candidate_value = normalize_str(candidate)
                if candidate_value:
                    instructor_id = candidate_value
                    break
    if not instructor_id and isinstance(payload.get("members"), list):
        for member in payload.get("members"):
            if not isinstance(member, dict):
                continue
            if normalize_str(member.get("role")).lower() == "instructor":
                instructor_id = normalize_str(member.get("id") or member.get("memberId") or member.get("member_id"))
                if not instructor_id:
                    instructor_id = normalize_str(member.get("email"))
                break
    if not instructor_id:
        return None, "instructor_id is required."

    instructor_email = normalize_str(payload.get("instructor_email") or payload.get("instructorEmail")).lower()
    if instructor_email and not is_valid_email(instructor_email):
        return None, "instructor_email must be valid when provided."

    ta_ids_payload = payload.get("ta_ids")
    if ta_ids_payload is None:
        ta_ids_payload = payload.get("taIds")
    if ta_ids_payload is None:
        ta_ids_payload = []
    if not isinstance(ta_ids_payload, list):
        return None, "ta_ids must be a list of non-empty strings."
    ta_ids = [normalize_str(value) for value in ta_ids_payload if normalize_str(value)]

    raw_is_active = payload.get("is_active") if "is_active" in payload else payload.get("isActive")
    if raw_is_active is None:
        is_active = True
    elif isinstance(raw_is_active, bool):
        is_active = raw_is_active
    else:
        return None, "is_active must be a boolean."

    instructor_key_limit = payload.get("instructor_key_limit")
    if instructor_key_limit is None:
        instructor_key_limit = payload.get("instructorKeyLimit")
    if instructor_key_limit is None:
        instructor_key_limit = 2
    if not isinstance(instructor_key_limit, int) or instructor_key_limit < 0:
        return None, "instructor_key_limit must be an integer >= 0."

    student_ids = payload.get("student_ids")
    if student_ids is None:
        student_ids = member_students
    if not isinstance(student_ids, list) or not all(isinstance(v, str) and v.strip() for v in student_ids):
        return None, "student_ids must be a list of non-empty strings."

    instructor_handout_limit = payload.get("instructor_handout_limit")
    if instructor_handout_limit is None:
        instructor_handout_limit = payload.get("instructorHandoutLimit")
    if instructor_handout_limit is None:
        instructor_handout_limit = 2
    if not isinstance(instructor_handout_limit, int) or instructor_handout_limit < 0:
        return None, "instructor_handout_limit must be an integer >= 0."

    cleaned = {
        "name": name,
        "instructor_id": instructor_id,
        "instructor_email": instructor_email or None,
        "ta_ids": ta_ids,
        "is_active": is_active,
        "student_ids": [v.strip() for v in student_ids],
        "semester": parsed_semester["display"],
        "semester_obj": None if parsed_semester["term"] == "none" else {"year": parsed_semester["year"], "term": parsed_semester["term"]},
        "members": members,
        "groups": groups,
        "color": normalize_str(payload.get("color")) or COURSE_COLOR_DEFAULT,
        "instructor_key_limit": instructor_key_limit,
        "instructor_handout_limit": instructor_handout_limit,
    }

    course_code = normalize_str(payload.get("code"))
    instructor_name = normalize_str(payload.get("instructor"))
    if course_code:
        cleaned["code"] = course_code
    if instructor_name:
        cleaned["instructor"] = instructor_name

    course_id = payload.get("id")
    if isinstance(course_id, int):
        cleaned["id"] = course_id

    return cleaned, None


def validate_api_key_payload(payload: Any):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."

    owner_type = normalize_str(payload.get("owner_type") or "person").lower() or "person"
    owner_id = normalize_str(payload.get("owner_id") or payload.get("u_id")).lower()
    group_id = normalize_str(payload.get("group_id")).lower() if payload.get("group_id") is not None else ""
    course_id = payload.get("course_id")
    c_id = payload.get("c_id")
    key_hash = normalize_str(payload.get("hash"))
    expire = payload.get("expire")
    key_name = normalize_str(payload.get("key_name") or "key-1")[:64].strip() or "key-1"
    key_id = normalize_str(payload.get("key_id"))
    slot_index_raw = payload.get("slot_index")
    try:
        slot_index = int(slot_index_raw)
    except (TypeError, ValueError):
        slot_index = 0
    if slot_index < 1:
        if key_name.startswith("key-"):
            slot_suffix = key_name[4:]
            if slot_suffix.isdigit():
                slot_index = int(slot_suffix)
            else:
                slot_index = 1
        else:
            slot_index = 1

    raw_is_active = payload.get("is_active") if "is_active" in payload else payload.get("isActive")
    if raw_is_active is None:
        is_active = True
    elif isinstance(raw_is_active, bool):
        is_active = raw_is_active
    else:
        return None, "is_active must be a boolean."

    if owner_type not in {"person", "group"}:
        return None, "owner_type must be either person or group."
    if owner_type == "group" and not owner_id:
        owner_id = group_id
    if not owner_id:
        return None, "owner_id is required and must be a non-empty string."
    if not isinstance(course_id, int):
        return None, "course_id is required and must be an integer."
    if not key_hash:
        return None, "hash is required and must be a non-empty string."
    if expire is not None:
        if not isinstance(expire, str):
            return None, "expire must be an ISO datetime string or null."
        try:
            datetime.fromisoformat(expire.replace("Z", "+00:00"))
        except ValueError:
            return None, "expire must be a valid ISO datetime string."

    return {
        "key_id": key_id or None,
        "owner_type": owner_type,
        "owner_id": owner_id,
        "u_id": owner_id if owner_type == "person" else None,
        "group_created_by": normalize_str(payload.get("group_created_by")).lower() or None,
        "key_name": key_name,
        "slot_index": slot_index,
        "course_id": course_id,
        "c_id": normalize_str(c_id) if isinstance(c_id, str) else None,
        "hash": key_hash,
        "is_active": is_active,
        "expire": expire,
    }, None
