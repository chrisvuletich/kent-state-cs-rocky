from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request


def _build_user_identity_maps(users_collection, normalize_str):
    users_by_id: dict[str, dict[str, Any]] = {}
    users_by_email: dict[str, dict[str, Any]] = {}
    for user in users_collection.find():
        if not isinstance(user, dict):
            continue
        user_id = normalize_str(user.get("id")).lower()
        user_email = normalize_str(user.get("email")).lower()
        if user_id:
            users_by_id[user_id] = user
        if user_email:
            users_by_email[user_email] = user
    return users_by_id, users_by_email


def _resolve_user_display_name(user: dict[str, Any], normalize_str) -> str:
    if not isinstance(user, dict):
        return ""
    first_name = normalize_str(user.get("first_name"))
    last_name = normalize_str(user.get("last_name"))
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if full_name:
        return full_name
    fallback_name = normalize_str(user.get("name"))
    if fallback_name:
        return fallback_name
    return ""


def _with_resolved_member_names(course: dict[str, Any], users_by_id: dict[str, dict[str, Any]], users_by_email: dict[str, dict[str, Any]], normalize_str):
    result = dict(course)
    members = course.get("members") if isinstance(course.get("members"), list) else []
    resolved_members: list[dict[str, Any]] = []

    for member in members:
        if not isinstance(member, dict):
            continue
        current_member = dict(member)
        existing_name = normalize_str(current_member.get("name"))
        if existing_name:
            resolved_members.append(current_member)
            continue

        member_id = normalize_str(current_member.get("id")).lower()
        member_email = normalize_str(current_member.get("email")).lower()
        matched_user = users_by_id.get(member_id) if member_id else None
        if matched_user is None and member_email:
            matched_user = users_by_email.get(member_email)

        resolved_name = _resolve_user_display_name(matched_user or {}, normalize_str)
        if resolved_name:
            current_member["name"] = resolved_name

        resolved_members.append(current_member)

    result["members"] = resolved_members
    return result


def _course_is_active(course: dict[str, Any]) -> bool:
    return bool(course.get("is_active", True))


def _reject_if_course_closed(course: dict[str, Any]):
    if _course_is_active(course):
        return None
    return jsonify({"error": "Course is closed. Reopen it to make changes."}), 403


def _course_member_aliases(course: dict[str, Any], member_id: str, normalize_str) -> set[str]:
    """Return every stored identifier that refers to one course member."""

    normalized_target = normalize_str(member_id).lower()
    aliases = {normalized_target} if normalized_target else set()
    for member in course.get("members", []):
        if not isinstance(member, dict):
            continue
        member_aliases = {
            normalize_str(member.get("id")).lower(),
            normalize_str(member.get("email")).lower(),
        }
        member_aliases.discard("")
        if normalized_target in member_aliases:
            aliases.update(member_aliases)
    return aliases


def _revoke_course_owner_keys(
    course: dict[str, Any],
    api_keys_collection,
    owner_type: str,
    owner_ids: set[str],
    normalize_str,
) -> int:
    """Irreversibly revoke matching course keys while retaining their audit records."""

    normalized_owner_ids = {
        normalize_str(owner_id).lower()
        for owner_id in owner_ids
        if normalize_str(owner_id)
    }
    if not normalized_owner_ids:
        return 0

    lookup: dict[str, Any] = {
        "owner_type": normalize_str(owner_type).lower(),
        "owner_id": {"$in": sorted(normalized_owner_ids)},
    }
    if isinstance(course.get("id"), int):
        lookup["course_id"] = course["id"]
    else:
        course_code = normalize_str(course.get("code"))
        if not course_code:
            return 0
        lookup["c_id"] = course_code

    revoked_at = datetime.now(timezone.utc).isoformat()
    revoked_count = 0
    for key_entry in api_keys_collection.find(lookup):
        if not isinstance(key_entry, dict):
            continue
        if not key_entry.get("hash") and key_entry.get("deleted_at"):
            continue
        updated_key = dict(key_entry)
        updated_key["hash"] = ""
        updated_key["is_active"] = False
        updated_key["disabled_reason"] = "membership"
        updated_key["deleted_at"] = revoked_at
        api_keys_collection.replace_one({"_id": key_entry.get("_id")}, updated_key)
        revoked_count += 1
    return revoked_count


def _deactivate_overflow_course_keys(course: dict[str, Any], api_keys_collection, owner_type: str, owner_ids: list[str], max_slot_index: int, normalize_str):
    normalized_owner_type = normalize_str(owner_type).lower()
    if normalized_owner_type not in {"person", "group"}:
        return 0

    def normalize_identifier(value: Any) -> str:
        if value is None:
            return ""
        string_value = str(value) if not isinstance(value, str) else value
        return normalize_str(string_value).lower()

    normalized_owner_ids = {
        normalize_identifier(owner_id)
        for owner_id in owner_ids
        if normalize_identifier(owner_id)
    }
    if not normalized_owner_ids:
        return 0

    course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None
    course_code = normalize_str(course.get("code"))
    if course_numeric_id is None and not course_code:
        return 0

    lookup_filter: dict[str, Any] = {
        "owner_type": normalized_owner_type,
        "owner_id": {"$in": sorted(normalized_owner_ids)},
    }
    if course_numeric_id is not None:
        lookup_filter["course_id"] = course_numeric_id
    else:
        lookup_filter["c_id"] = course_code

    updated_count = 0
    for key_entry in api_keys_collection.find(lookup_filter):
        if not isinstance(key_entry, dict):
            continue
        slot_index = key_entry.get("slot_index") if isinstance(key_entry.get("slot_index"), int) else None
        if slot_index is None or slot_index < 1:
            key_name = normalize_str(key_entry.get("key_name"))
            if key_name.startswith("key-") and key_name[4:].isdigit():
                slot_index = int(key_name[4:])
            else:
                continue
        if slot_index <= max_slot_index:
            continue
        if key_entry.get("is_active", True) is False:
            continue

        updated_key = dict(key_entry)
        updated_key["is_active"] = False
        updated_key["disabled_reason"] = "limit"
        api_keys_collection.replace_one({"_id": key_entry.get("_id")}, updated_key)
        updated_count += 1

    return updated_count


def _reconcile_course_key_activity(course: dict[str, Any], api_keys_collection, owner_type: str, owner_ids: list[str], max_slot_index: int, normalize_str):
    normalized_owner_type = normalize_str(owner_type).lower()
    if normalized_owner_type not in {"person", "group"}:
        return 0

    def normalize_identifier(value: Any) -> str:
        if value is None:
            return ""
        string_value = str(value) if not isinstance(value, str) else value
        return normalize_str(string_value).lower()

    normalized_owner_ids = {
        normalize_identifier(owner_id)
        for owner_id in owner_ids
        if normalize_identifier(owner_id)
    }
    if not normalized_owner_ids:
        return 0

    course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None
    course_code = normalize_str(course.get("code"))
    if course_numeric_id is None and not course_code:
        return 0

    lookup_filter: dict[str, Any] = {
        "owner_type": normalized_owner_type,
        "owner_id": {"$in": sorted(normalized_owner_ids)},
    }
    if course_numeric_id is not None:
        lookup_filter["course_id"] = course_numeric_id
    else:
        lookup_filter["c_id"] = course_code

    updated_count = 0
    for key_entry in api_keys_collection.find(lookup_filter):
        if not isinstance(key_entry, dict):
            continue
        slot_index = key_entry.get("slot_index") if isinstance(key_entry.get("slot_index"), int) else None
        if slot_index is None or slot_index < 1:
            key_name = normalize_str(key_entry.get("key_name"))
            if key_name.startswith("key-") and key_name[4:].isdigit():
                slot_index = int(key_name[4:])
            else:
                continue

        should_be_active = (
            slot_index <= max_slot_index
            and key_entry.get("disabled_reason") == "limit"
        )
        is_active = key_entry.get("is_active", True) is not False
        if slot_index <= max_slot_index and not should_be_active:
            continue
        if should_be_active == is_active:
            continue

        updated_key = dict(key_entry)
        updated_key["is_active"] = should_be_active
        if should_be_active:
            updated_key.pop("disabled_reason", None)
        else:
            updated_key["disabled_reason"] = "limit"
        api_keys_collection.replace_one({"_id": key_entry.get("_id")}, updated_key)
        updated_count += 1

    return updated_count


def create_course(deps: dict[str, Any]):
    require_admin = deps["require_admin"]
    validate_course_payload = deps["validate_course_payload"]
    courses = deps["courses"]
    users = deps["users"]
    apply_course_metadata_patch = deps["apply_course_metadata_patch"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    cleaned, error = validate_course_payload(request.get_json(silent=True))
    if error:
        return _bad_request(error)

    if "id" in cleaned:
        if courses.find_one({"id": cleaned["id"]}) is not None:
            return _bad_request("Course id already exists.")
    if "id" not in cleaned:
        existing_ids = [course.get("id", 0) for course in courses.find() if isinstance(course.get("id"), int)]
        cleaned["id"] = (max(existing_ids) if existing_ids else 0) + 1

    try:
        cleaned = apply_course_metadata_patch(
            cleaned,
            users,
            {
                "instructorId": cleaned.get("instructor_id") or "",
                "instructorEmail": cleaned.get("instructor_email") or "",
                "taIds": cleaned.get("ta_ids") or [],
            },
        )
    except ValueError as exc:
        return _bad_request("Unable to process course metadata.")

    courses.insert_one(cleaned)
    deps["record_audit_event"](
        deps,
        "course-created",
        course=cleaned,
        target_type="course",
        target_id=cleaned.get("id"),
        changes={"code": cleaned.get("code"), "name": cleaned.get("name"), "semester": cleaned.get("semester")},
    )
    return jsonify(_serialize_value(cleaned)), 201


def get_courses(deps: dict[str, Any]):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    courses = deps["courses"]
    users = deps["users"]
    _attach_course_key_state = deps["_attach_course_key_state"]
    _serialize_value = deps["_serialize_value"]
    filter_visible_courses = deps["filter_visible_courses"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)
    users_by_id, users_by_email = _build_user_identity_maps(users, normalize_str)
    result = [
        _attach_course_key_state(
            _with_resolved_member_names(_serialize_value(course), users_by_id, users_by_email, normalize_str)
        )
        for course in courses.find()
    ]
    return jsonify(filter_visible_courses(result, requester_id or email, is_admin))


def get_course(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    courses = deps["courses"]
    users = deps["users"]
    get_course_record = deps["get_course_record"]
    _attach_course_key_state = deps["_attach_course_key_state"]
    _serialize_value = deps["_serialize_value"]
    filter_visible_courses = deps["filter_visible_courses"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)
    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    users_by_id, users_by_email = _build_user_identity_maps(users, normalize_str)
    serialized = _attach_course_key_state(
        _with_resolved_member_names(_serialize_value(course), users_by_id, users_by_email, normalize_str)
    )
    visible = filter_visible_courses([serialized], requester_id or email, is_admin)
    if not visible:
        return jsonify({"error": "Not found"}), 404

    return jsonify(visible[0])


def patch_course_metadata(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    can_manage_metadata = deps["can_manage_metadata"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    users = deps["users"]
    apply_course_metadata_patch = deps["apply_course_metadata_patch"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    _, is_admin = identity
    if not can_manage_metadata(is_admin):
        return jsonify({"error": "Admin access is required."}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return _bad_request("Request body must be a non-empty JSON object.")

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    try:
        updated = apply_course_metadata_patch(course, users, data)
    except ValueError as exc:
        return _bad_request("Unable to update course metadata.")

    courses.replace_one({"_id": course["_id"]}, updated)
    deps["record_audit_event"](
        deps,
        "course-metadata-updated",
        course=updated,
        target_type="course",
        target_id=updated.get("id"),
        changes={key: updated.get(key) for key in data},
    )
    return jsonify(_serialize_value(updated))


def update_course_status_route(deps: dict[str, Any], course_id: str):
    require_admin = deps["require_admin"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    set_course_active_state = deps["set_course_active_state"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data.keys()) != {"is_active"}:
        return _bad_request("Only is_active may be updated through this endpoint.")
    if not isinstance(data.get("is_active"), bool):
        return _bad_request("is_active must be a boolean.")

    try:
        updated = set_course_active_state(course, api_keys, bool(data.get("is_active")))
    except ValueError as exc:
        return _bad_request("Unable to update course status.")

    courses.replace_one({"_id": course["_id"]}, updated)
    deps["record_audit_event"](
        deps,
        "course-status-updated",
        course=updated,
        target_type="course",
        target_id=updated.get("id"),
        changes={"is_active": data["is_active"]},
    )
    return jsonify(_serialize_value(updated))


def delete_course(deps: dict[str, Any], course_id: str):
    require_admin = deps["require_admin"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    delete_course_api_keys = deps["delete_course_api_keys"]

    ok, err = require_admin()
    if not ok:
        return jsonify({"error": "Admin access is required."}), 403

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    deleted_keys = delete_course_api_keys(course, api_keys)
    courses.delete_one({"_id": course["_id"]})
    deps["record_audit_event"](
        deps,
        "course-deleted",
        course=course,
        target_type="course",
        target_id=course.get("id"),
        changes={"code": course.get("code"), "name": course.get("name"), "deleted_keys": deleted_keys},
    )
    return jsonify({"message": "Course deleted"})


def add_course_members_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    users = deps["users"]
    can_manage_people = deps["can_manage_people"]
    add_course_members = deps["add_course_members"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    data = request.get_json(silent=True)
    if data is None:
        return _bad_request("Request body is required.")

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    if not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    members_payload = data.get("members") if isinstance(data, dict) else data
    if isinstance(members_payload, dict):
        members_payload = [members_payload]

    try:
        updated = add_course_members(course, users, members_payload, is_admin)
    except ValueError as exc:
        return _bad_request("Unable to add course members.")

    courses.replace_one({"_id": course["_id"]}, updated)
    added_identifiers = [
        (member.get("id") or member.get("email"))
        for member in (members_payload or [])
        if isinstance(member, dict)
    ]
    deps["record_audit_event"](
        deps,
        "course-members-added",
        course=updated,
        target_type="course-members",
        target_id=",".join(str(value) for value in added_identifiers if value),
        changes={"members": added_identifiers},
    )
    return jsonify(_serialize_value(updated))


def remove_course_member_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    can_manage_people = deps["can_manage_people"]
    remove_course_member = deps["remove_course_member"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    target_member_id = normalize_str(data.get("id") or data.get("memberId") or data.get("member_id"))
    if not target_member_id:
        return _bad_request("id is required.")

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    if not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    member_aliases = _course_member_aliases(course, target_member_id, normalize_str)
    affected_group_ids = {
        normalize_str(group.get("id")).lower()
        for group in course.get("groups", [])
        if isinstance(group, dict)
        and not member_aliases.isdisjoint(
            {
                normalize_str(group_member_id).lower()
                for group_member_id in group.get("memberIds", [])
            }
        )
        and normalize_str(group.get("id"))
    }

    try:
        updated = remove_course_member(course, target_member_id, is_admin)
    except ValueError as exc:
        return _bad_request("Unable to remove course member.")

    courses.replace_one({"_id": course["_id"]}, updated)
    revoked_person_keys = _revoke_course_owner_keys(
        course,
        api_keys,
        "person",
        member_aliases,
        normalize_str,
    )
    revoked_group_keys = sum(
        _revoke_course_owner_keys(
            course,
            api_keys,
            "group",
            {group_id},
            normalize_str,
        )
        for group_id in affected_group_ids
    )
    deps["record_audit_event"](
        deps,
        "course-member-removed",
        course=updated,
        target_type="course-member",
        target_id=target_member_id,
        changes={
            "revoked_person_keys": revoked_person_keys,
            "revoked_group_keys": revoked_group_keys,
        },
    )
    return jsonify(_serialize_value(updated))


def create_course_group_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    can_manage_people = deps["can_manage_people"]
    create_course_group = deps["create_course_group"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    if not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    global_group_ids = {
        normalize_str(group.get("id"))
        for candidate_course in courses.find()
        for group in candidate_course.get("groups", [])
        if isinstance(group, dict)
    }
    current_course_group_ids = {
        normalize_str(group.get("id"))
        for group in course.get("groups", [])
        if isinstance(group, dict)
    }
    global_group_ids -= current_course_group_ids

    try:
        updated = create_course_group(course, data.get("name", ""), global_group_ids)
    except ValueError as exc:
        return _bad_request("Unable to create course group.")

    courses.replace_one({"_id": course["_id"]}, updated)
    created_group = updated.get("groups", [])[-1] if updated.get("groups") else {}
    deps["record_audit_event"](
        deps,
        "course-group-created",
        course=updated,
        target_type="group",
        target_id=created_group.get("id"),
        changes={"name": created_group.get("name")},
    )
    return jsonify(_serialize_value(updated))


def add_group_member_route(deps: dict[str, Any], course_id: str, group_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    can_manage_people = deps["can_manage_people"]
    add_group_member = deps["add_group_member"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    if not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    target_member_id = normalize_str(data.get("id") or data.get("memberId") or data.get("member_id"))
    if not target_member_id:
        return _bad_request("id is required.")

    try:
        updated = add_group_member(course, group_id, target_member_id)
    except ValueError as exc:
        return _bad_request("Unable to add group member.")

    courses.replace_one({"_id": course["_id"]}, updated)
    deps["record_audit_event"](
        deps,
        "course-group-member-added",
        course=updated,
        target_type="group",
        target_id=group_id,
        changes={"member_id": target_member_id},
    )
    return jsonify(_serialize_value(updated))


def remove_group_member_route(deps: dict[str, Any], course_id: str, group_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    can_manage_people = deps["can_manage_people"]
    remove_group_member = deps["remove_group_member"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    if not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    target_member_id = normalize_str(data.get("id") or data.get("memberId") or data.get("member_id"))
    if not target_member_id:
        return _bad_request("id is required.")

    member_aliases = _course_member_aliases(course, target_member_id, normalize_str)
    target_group = next(
        (
            group
            for group in course.get("groups", [])
            if isinstance(group, dict)
            and normalize_str(group.get("id")).lower() == normalize_str(group_id).lower()
        ),
        None,
    )
    member_was_in_group = bool(
        target_group
        and not member_aliases.isdisjoint(
            {
                normalize_str(group_member_id).lower()
                for group_member_id in target_group.get("memberIds", [])
            }
        )
    )

    try:
        updated = remove_group_member(course, group_id, target_member_id)
    except ValueError as exc:
        return _bad_request("Unable to remove group member.")

    courses.replace_one({"_id": course["_id"]}, updated)
    revoked_group_keys = (
        _revoke_course_owner_keys(
            course,
            api_keys,
            "group",
            {normalize_str(group_id).lower()},
            normalize_str,
        )
        if member_was_in_group
        else 0
    )
    deps["record_audit_event"](
        deps,
        "course-group-member-removed",
        course=updated,
        target_type="group",
        target_id=group_id,
        changes={
            "member_id": target_member_id,
            "revoked_group_keys": revoked_group_keys,
        },
    )
    return jsonify(_serialize_value(updated))


def update_member_key_limit_route(deps: dict[str, Any], course_id: str, member_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    can_manage_people = deps["can_manage_people"]
    update_course_member_key_limit = deps["update_course_member_key_limit"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response
    if not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    instructor_identifiers = {
        normalize_str(course.get("instructor_id")).lower(),
        normalize_str(course.get("instructor_email")).lower(),
    }
    if normalize_str(member_id).lower() in instructor_identifiers:
        return jsonify({"error": "Instructor key limits are managed separately."}), 403

    target_member = next(
        (
            member
            for member in course.get("members", [])
            if isinstance(member, dict)
            and (
                normalize_str(member.get("id")) == normalize_str(member_id)
                or normalize_str(member.get("email")).lower() == normalize_str(member_id).lower()
            )
        ),
        None,
    )
    if target_member is None:
        return jsonify({"error": "Member not found."}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    key_limit = data.get("keyLimit") if "keyLimit" in data else data.get("key_limit")
    if not isinstance(key_limit, int) or key_limit < 0:
        return _bad_request("keyLimit must be an integer >= 0.")

    try:
        updated = update_course_member_key_limit(course, member_id, key_limit)
    except ValueError as exc:
        return _bad_request("keyLimit cannot exceed the course limit.")

    _deactivate_overflow_course_keys(
        updated,
        api_keys,
        "person",
        [target_member.get("id") or "", target_member.get("email") or ""],
        key_limit,
        normalize_str,
    )
    _reconcile_course_key_activity(
        updated,
        api_keys,
        "person",
        [target_member.get("id") or "", target_member.get("email") or ""],
        key_limit,
        normalize_str,
    )

    courses.replace_one({"_id": course["_id"]}, updated)
    deps["record_audit_event"](
        deps,
        "course-member-key-limit-updated",
        course=updated,
        target_type="course-member",
        target_id=member_id,
        changes={"key_limit": key_limit},
    )
    return jsonify(_serialize_value(updated))


def update_instructor_handout_limit_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    update_course_instructor_handout_limit = deps["update_course_instructor_handout_limit"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    _ = _resolve_requester_user_id(email)

    if not is_admin:
        return jsonify({"error": "Admin access is required."}), 403

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    handout_limit = (
        data.get("instructorHandoutLimit")
        if "instructorHandoutLimit" in data
        else data.get("instructor_handout_limit")
    )
    if not isinstance(handout_limit, int) or handout_limit < 0:
        return _bad_request("instructorHandoutLimit must be an integer >= 0.")

    try:
        updated = update_course_instructor_handout_limit(course, handout_limit)
    except ValueError:
        return _bad_request("Unable to update instructor handout limit.")

    for member in updated.get("members", []):
        if not isinstance(member, dict):
            continue
        member_limit = member.get("key_limit")
        if not isinstance(member_limit, int) or member_limit < 0:
            member_limit = 1
        effective_limit = min(member_limit, handout_limit)
        member["key_limit"] = effective_limit
        _reconcile_course_key_activity(
            updated,
            api_keys,
            "person",
            [member.get("id") or "", member.get("email") or ""],
            effective_limit,
            normalize_str,
        )

    for group in updated.get("groups", []):
        if not isinstance(group, dict):
            continue
        group_limit = group.get("key_limit")
        if not isinstance(group_limit, int) or group_limit < 0:
            group_limit = 1
        effective_limit = min(group_limit, handout_limit)
        group["key_limit"] = effective_limit
        _reconcile_course_key_activity(
            updated,
            api_keys,
            "group",
            [group.get("id") or ""],
            effective_limit,
            normalize_str,
        )

    courses.replace_one({"_id": course["_id"]}, updated)
    deps["record_audit_event"](
        deps,
        "course-instructor-handout-limit-updated",
        course=updated,
        target_type="course",
        target_id=updated.get("id"),
        changes={"instructor_handout_limit": handout_limit},
    )
    return jsonify(_serialize_value(updated))


def update_instructor_key_limit_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    update_course_instructor_key_limit = deps["update_course_instructor_key_limit"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    _ = _resolve_requester_user_id(email)

    if not is_admin:
        return jsonify({"error": "Admin access is required."}), 403

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    key_limit = data.get("instructorKeyLimit") if "instructorKeyLimit" in data else data.get("instructor_key_limit")
    if not isinstance(key_limit, int) or key_limit < 0:
        return _bad_request("instructorKeyLimit must be an integer >= 0.")

    try:
        updated = update_course_instructor_key_limit(course, key_limit)
    except ValueError:
        return _bad_request("Unable to update instructor key limit.")

    _reconcile_course_key_activity(
        updated,
        api_keys,
        "person",
        [course.get("instructor_id") or "", course.get("instructor_email") or ""],
        key_limit,
        normalize_str,
    )

    courses.replace_one({"_id": course["_id"]}, updated)
    deps["record_audit_event"](
        deps,
        "course-instructor-key-limit-updated",
        course=updated,
        target_type="course",
        target_id=updated.get("id"),
        changes={"instructor_key_limit": key_limit},
    )
    return jsonify({"message": "Instructor key limit updated successfully."})


def update_group_key_limit_route(deps: dict[str, Any], course_id: str, group_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    can_manage_people = deps["can_manage_people"]
    update_course_group_key_limit = deps["update_course_group_key_limit"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response
    if not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    key_limit = data.get("keyLimit") if "keyLimit" in data else data.get("key_limit")
    if not isinstance(key_limit, int) or key_limit < 0:
        return _bad_request("keyLimit must be an integer >= 0.")

    try:
        updated = update_course_group_key_limit(course, group_id, key_limit)
    except ValueError as exc:
        return _bad_request("Unable to update group key limit.")

    _deactivate_overflow_course_keys(updated, api_keys, "group", [group_id], key_limit, normalize_str)
    _reconcile_course_key_activity(updated, api_keys, "group", [group_id], key_limit, normalize_str)

    courses.replace_one({"_id": course["_id"]}, updated)
    deps["record_audit_event"](
        deps,
        "course-group-key-limit-updated",
        course=updated,
        target_type="group",
        target_id=group_id,
        changes={"key_limit": key_limit},
    )
    return jsonify(_serialize_value(updated))


def list_course_api_keys_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    can_request_api_key = deps["can_request_api_key"]
    can_manage_people = deps["can_manage_people"]
    _iter_course_api_keys = deps["_iter_course_api_keys"]
    _serialize_api_key_summary = deps["_serialize_api_key_summary"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404
    if not can_request_api_key(course, requester_id or email, is_admin):
        return jsonify({"error": "Course access is required."}), 403
    can_manage_course_people = can_manage_people(course, requester_id or email, is_admin)

    normalized_requester = normalize_str(requester_id or email).lower()
    requester_group_ids = {
        normalize_str(group.get("id")).lower()
        for group in course.get("groups", [])
        if isinstance(group, dict)
        and (
            normalized_requester in {normalize_str(member_id).lower() for member_id in group.get("memberIds", [])}
            or normalize_str(email).lower() in {normalize_str(member_id).lower() for member_id in group.get("memberIds", [])}
        )
    }

    result: list[dict[str, Any]] = []
    for entry in _iter_course_api_keys(course):
        owner_type = normalize_str(entry.get("owner_type")).lower() or "person"
        owner_id = normalize_str(entry.get("owner_id")).lower()
        if not is_admin and not can_manage_course_people:
            if owner_type == "person" and owner_id != normalized_requester:
                continue
            if owner_type == "group" and owner_id not in requester_group_ids:
                continue
        result.append(_serialize_api_key_summary(entry))

    result.sort(key=lambda item: normalize_str(item.get("key_name")))
    return jsonify(_serialize_value(result))


def regenerate_course_api_key_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    can_request_api_key = deps["can_request_api_key"]
    can_manage_people = deps["can_manage_people"]
    _get_owner_key_limit = deps["_get_owner_key_limit"]
    _iter_course_api_keys = deps["_iter_course_api_keys"]
    _parse_iso_datetime = deps["_parse_iso_datetime"]
    regenerate_course_api_key = deps["regenerate_course_api_key"]
    resolve_course_key_owner = deps["resolve_course_key_owner"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]
    _resolve_user_record = deps["_resolve_user_record"]
    _is_user_active = deps["_is_user_active"]
    API_KEY_REGENERATION_COOLDOWN = deps["API_KEY_REGENERATION_COOLDOWN"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity

    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    requester_id = _resolve_requester_user_id(email)
    if not can_request_api_key(course, requester_id or email, is_admin):
        return jsonify({"error": "Course access is required."}), 403

    owner_type = normalize_str(data.get("ownerType") or data.get("owner_type")).lower() or "person"
    owner_id = normalize_str(data.get("ownerId") or data.get("owner_id") or data.get("groupId") or data.get("group_id"))

    normalized_requester = normalize_str(requester_id or email).lower()
    can_manage_course_people = can_manage_people(course, requester_id or email, is_admin)

    if not is_admin and not can_manage_course_people:
        if owner_type == "group":
            return jsonify({"error": "Instructor, teaching assistant, or admin access is required for group keys."}), 403
        else:
            owner_type = "person"
            owner_id = normalized_requester
    elif owner_type == "group":
        target_group_id = owner_id
        target_group = next(
            (
                group
                for group in course.get("groups", [])
                if isinstance(group, dict) and normalize_str(group.get("id")).lower() == normalize_str(target_group_id).lower()
            ),
            None,
        )
        if target_group is None:
            return _bad_request("groupId is required for group keys.")
        owner_id = normalize_str(target_group.get("id"))
        owner_type = "group"
    else:
        owner_type = "person"
        owner_id = normalize_str(owner_id or normalized_requester)

    owner_id = normalize_str(owner_id or normalized_requester).lower()
    admin_self_owner = False
    try:
        resolved_owner = resolve_course_key_owner(course, owner_type, owner_id)
    except ValueError as exc:
        if is_admin and owner_type == "person" and owner_id == normalized_requester:
            resolved_owner = {"owner_type": "person", "owner_id": normalized_requester}
            admin_self_owner = True
        else:
            return _bad_request(str(exc))
    owner_type = resolved_owner["owner_type"]
    owner_id = resolved_owner["owner_id"]

    if owner_type == "person":
        owner_record = _resolve_user_record(owner_id, owner_id)
        if owner_record is not None and not _is_user_active(owner_record):
            return jsonify({
                "error": {
                    "message": "API keys cannot be generated for an inactive account.",
                    "type": "permission_error",
                    "code": "account_inactive",
                }
            }), 403

    key_name = normalize_str(data.get("keyName") or data.get("key_name") or "key-1")[:64].strip() or "key-1"
    slot_index_raw = data.get("slotIndex") or data.get("slot_index")
    slot_index_provided = slot_index_raw is not None and slot_index_raw != ""
    try:
        slot_index = int(slot_index_raw)
    except (TypeError, ValueError):
        slot_index = 0
    if slot_index < 1:
        slot_index = 1

    owner_key_limit = _get_owner_key_limit(course, owner_type, owner_id)
    if admin_self_owner and owner_key_limit == 0:
        configured_admin_limit = course.get("instructor_key_limit")
        owner_key_limit = configured_admin_limit if isinstance(configured_admin_limit, int) and configured_admin_limit >= 0 else 2
    if slot_index > owner_key_limit:
        return _bad_request(
            f"Key slot {slot_index} exceeds this owner's limit ({owner_key_limit})."
        )

    owner_keys = [
        entry
        for entry in _iter_course_api_keys(course)
        if normalize_str(entry.get("owner_type")).lower() == owner_type
        and normalize_str(entry.get("owner_id")).lower() == owner_id
    ]
    target_key = next(
        (
            entry
            for entry in owner_keys
            if (
                slot_index_provided
                and isinstance(entry.get("slot_index"), int)
                and entry.get("slot_index") == slot_index
            )
            or (
                not slot_index_provided
                and normalize_str(entry.get("key_name")) == key_name
            )
        ),
        None,
    )

    is_handout_action = owner_type == "group" or (
        owner_type == "person"
        and owner_id not in {normalized_requester, normalize_str(email).lower()}
    )
    target_key_created_at = _parse_iso_datetime(target_key.get("created")) if isinstance(target_key, dict) else None
    if target_key_created_at is not None and datetime.now(timezone.utc) - target_key_created_at < API_KEY_REGENERATION_COOLDOWN:
        remaining = API_KEY_REGENERATION_COOLDOWN - (datetime.now(timezone.utc) - target_key_created_at)
        minutes = max(1, int(remaining.total_seconds() // 60) + (1 if remaining.total_seconds() % 60 else 0))
        return jsonify({"error": f"Please wait {minutes} minute(s) before generating another key."}), 429

    ownership = {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "key_name": key_name,
        "slot_index": slot_index,
        "group_created_by": normalized_requester if is_handout_action else None,
    }

    try:
        key_doc = regenerate_course_api_key(
            course,
            api_keys,
            requester_id or email,
            ownership,
        )
    except ValueError as exc:
        return _bad_request("Unable to generate API key.")

    deps["record_audit_event"](
        deps,
        "generate-key",
        course=course,
        target_type=owner_type,
        target_id=owner_id,
        metadata={
            "owner_type": owner_type,
            "owner_id": owner_id,
            "key_name": key_name,
            "slot_index": slot_index,
        },
    )

    return jsonify(_serialize_value(key_doc))


def delete_course_api_key_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    can_manage_api_keys = deps["can_manage_api_keys"]
    can_manage_people = deps["can_manage_people"]
    delete_course_api_keys = deps["delete_course_api_keys"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    _serialize_api_key_summary = deps["_serialize_api_key_summary"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    owner_type = normalize_str(data.get("ownerType") or data.get("owner_type")).lower() or "person"
    owner_id = normalize_str(data.get("ownerId") or data.get("owner_id") or data.get("groupId") or data.get("group_id")).lower()
    key_name = normalize_str(data.get("keyName") or data.get("key_name") or "key-1")[:64].strip() or "key-1"
    slot_index_raw = data.get("slotIndex") or data.get("slot_index")
    slot_index_provided = slot_index_raw is not None and slot_index_raw != ""
    try:
        slot_index = int(slot_index_raw)
    except (TypeError, ValueError):
        slot_index = 0

    if owner_type in {"person", "group"} and owner_id:
        requester_id = _resolve_requester_user_id(email)

        if not is_admin and not can_manage_people(course, requester_id or email, is_admin):
            if owner_type == "person":
                normalized_requester = normalize_str(requester_id or email).lower()
                if owner_id != normalized_requester and owner_id != normalize_str(email).lower():
                    return jsonify({"error": "You may only delete your own keys."}), 403
            elif owner_type == "group":
                return jsonify({"error": "Instructor, teaching assistant, or admin access is required for group keys."}), 403

        course_numeric_id = course.get("id") if isinstance(course.get("id"), int) else None
        lookup_filter: dict[str, Any] = {
            "owner_type": owner_type,
            "owner_id": owner_id,
        }
        if slot_index_provided:
            lookup_filter["slot_index"] = slot_index
        else:
            lookup_filter["key_name"] = key_name
        if course_numeric_id is not None:
            lookup_filter["course_id"] = course_numeric_id
        else:
            lookup_filter["c_id"] = normalize_str(course.get("code"))

        existing_key = api_keys.find_one(lookup_filter)
        if existing_key is None and not slot_index_provided:
            fallback_lookup = dict(lookup_filter)
            fallback_lookup.pop("slot_index", None)
            fallback_lookup["key_name"] = key_name
            existing_key = api_keys.find_one(fallback_lookup)
        if existing_key is None:
            return jsonify({"error": "API key not found"}), 404

        if not is_admin and not can_manage_people(course, requester_id or email, is_admin):
            existing_owner_type = normalize_str(existing_key.get("owner_type")).lower() or "person"
            existing_owner_id = normalize_str(existing_key.get("owner_id")).lower()
            if existing_owner_type == "person":
                normalized_requester = normalize_str(requester_id or email).lower()
                if existing_owner_id != normalized_requester and existing_owner_id != normalize_str(email).lower():
                    return jsonify({"error": "You may only delete your own keys."}), 403
            elif existing_owner_type == "group":
                return jsonify({"error": "Instructor, teaching assistant, or admin access is required for group keys."}), 403

        updated_key = dict(existing_key)
        updated_key["hash"] = ""
        updated_key["is_active"] = False
        updated_key["deleted_at"] = datetime.now(timezone.utc).isoformat()
        api_keys.replace_one({"_id": existing_key.get("_id")}, updated_key)

        deps["record_audit_event"](
            deps,
            "delete-key",
            course=course,
            target_type=owner_type,
            target_id=owner_id,
            metadata={
                "owner_type": owner_type,
                "owner_id": owner_id,
                "key_name": key_name,
                "slot_index": slot_index if slot_index > 0 else existing_key.get("slot_index"),
            },
        )
        return jsonify(
            _serialize_value(
                {
                    "message": "API key hash removed",
                    "deleted": 1,
                    "key": _serialize_api_key_summary(updated_key),
                }
            )
        )

    if not can_manage_api_keys(is_admin):
        return jsonify({"error": "Admin access is required."}), 403

    try:
        deleted_count = delete_course_api_keys(course, api_keys)
    except ValueError as exc:
        return _bad_request("Unable to delete API keys.")

    deps["record_audit_event"](
        deps,
        "course-api-keys-deleted",
        course=course,
        target_type="course",
        target_id=course.get("id"),
        changes={"deleted": deleted_count},
    )
    return jsonify({"message": "API keys deleted", "deleted": deleted_count})


def update_course_api_key_status_route(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_keys = deps["api_keys"]
    can_manage_people = deps["can_manage_people"]
    set_course_api_key_active_state = deps["set_course_api_key_active_state"]
    _bad_request = deps["_bad_request"]
    _serialize_value = deps["_serialize_value"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    closed_response = _reject_if_course_closed(course)
    if closed_response is not None:
        return closed_response

    if not is_admin and not can_manage_people(course, requester_id or email, is_admin):
        return jsonify({"error": "Instructor or admin access is required."}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request("Request body must be a JSON object.")

    owner_type = normalize_str(data.get("ownerType") or data.get("owner_type")).lower() or "person"
    owner_id = normalize_str(data.get("ownerId") or data.get("owner_id") or data.get("groupId") or data.get("group_id")).lower()
    key_name = normalize_str(data.get("keyName") or data.get("key_name") or "key-1")[:64].strip() or "key-1"
    slot_index_raw = data.get("slotIndex") or data.get("slot_index")
    try:
        slot_index = int(slot_index_raw)
    except (TypeError, ValueError):
        slot_index = 0
    if slot_index < 1:
        slot_index = 1

    raw_is_active = data.get("isActive") if "isActive" in data else data.get("is_active")
    if not isinstance(raw_is_active, bool):
        return _bad_request("isActive must be a boolean.")
    if raw_is_active:
        owner_limit = deps["_get_owner_key_limit"](course, owner_type, owner_id)
        if slot_index > owner_limit:
            return _bad_request(
                f"Key slot {slot_index} exceeds this owner's limit ({owner_limit})."
            )

    try:
        updated_key = set_course_api_key_active_state(
            course,
            api_keys,
            owner_type,
            owner_id,
            key_name,
            slot_index,
            bool(raw_is_active),
        )
    except ValueError as exc:
        if str(exc) == "API key not found.":
            return jsonify({"error": "API key not found."}), 404
        return _bad_request("Unable to update API key status.")

    deps["record_audit_event"](
        deps,
        "course-api-key-status-updated",
        course=course,
        target_type=owner_type,
        target_id=owner_id,
        changes={
            "key_name": key_name,
            "slot_index": slot_index,
            "is_active": bool(raw_is_active),
        },
    )
    return jsonify({"message": "API key status updated successfully."})


def get_course_api_history(deps: dict[str, Any], course_id: str):
    require_requester_identity = deps["require_requester_identity"]
    _resolve_requester_user_id = deps["_resolve_requester_user_id"]
    get_course_record = deps["get_course_record"]
    courses = deps["courses"]
    api_history = deps["api_history"]
    filter_visible_courses = deps["filter_visible_courses"]
    _serialize_value = deps["_serialize_value"]
    can_manage_people = deps["can_manage_people"]
    normalize_str = deps["normalize_str"]

    identity = require_requester_identity()
    if identity[0] is None:
        return jsonify({"error": "Authentication headers are required."}), 401
    email, is_admin = identity
    requester_id = _resolve_requester_user_id(email)

    course = get_course_record(courses, course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    visible = filter_visible_courses([_serialize_value(course)], requester_id or email, is_admin)
    if not visible:
        return jsonify({"error": "Not found"}), 404

    query = {"c_id": normalize_str(course.get("code"))}
    if not can_manage_people(course, requester_id or email, is_admin):
        query["u_id"] = _resolve_requester_user_id(email)

    rows = [_serialize_value(item) for item in api_history.find(query)]
    return jsonify(rows)
