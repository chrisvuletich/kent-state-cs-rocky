"""Evaluate key access from current course policy, never a copied policy flag.

Course status/limits live on the course document. Key flags describe manual
disabling, account suspension, and revocation. Both services use this module so
the UI and API authorization agree without cross-document synchronization.
"""
from datetime import datetime, timezone


def _identifier(value):
    return str(value or "").strip().lower()


def _limit(value, default):
    return value if type(value) is int and value >= 0 else default


def owner_key_limit(course, owner_type, owner_id, *, admin_owner=False):
    owner_id = _identifier(owner_id)
    if not owner_id:
        return 0
    if owner_type == "group":
        group = next((g for g in course.get("groups", []) if _identifier(g.get("id")) == owner_id), None)
        return _limit(group.get("key_limit"), 1) if group is not None else 0
    if owner_type != "person":
        return 0
    staff = {_identifier(course.get("instructor_id")), _identifier(course.get("instructor_email"))}
    staff.update(_identifier(value) for value in course.get("ta_ids", []))
    staff.update(_identifier(value) for value in course.get("ta_emails", []))
    if owner_id in staff:
        return _limit(course.get("instructor_key_limit"), 2)
    member = next((m for m in course.get("members", []) if owner_id in {
        _identifier(m.get("id")), _identifier(m.get("email")),
    }), None)
    if member is not None:
        return _limit(member.get("key_limit"), 1)
    # Administrators may create a personal course key without roster enrollment.
    return _limit(course.get("instructor_key_limit"), 2) if admin_owner else 0


def key_slot(key):
    slot = key.get("slot_index")
    if type(slot) is int and slot > 0:
        return slot
    name = str(key.get("key_name") or "")
    return int(name[4:]) if name.startswith("key-") and name[4:].isdigit() else 0


def course_key_query(key):
    course_id = key.get("course_id")
    if course_id is not None:
        return {"id": course_id}
    code = str(key.get("c_id") or "").strip()
    return {"code": code} if code else None


def key_is_active(key, courses=None, users=None, *, course=None):
    """Fail closed on missing course policy; storage errors propagate to callers.

    Existing keys disabled for `course`/`limit` are evaluated using current
    policy too. This preserves already-issued keys without a migration. Other
    disable reasons (especially manual/account/membership) never auto-clear.
    """
    if not isinstance(key, dict) or key.get("deleted_at") or key.get("revoked_at"):
        return False
    query = course_key_query(key)
    if key.get("is_active") is False and not (
        query is not None and key.get("disabled_reason") in {"course", "limit"}
    ):
        return False
    expiry = key.get("expire") or key.get("expires_at")
    if expiry is not None and expiry != "":
        try:
            expires_at = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return False
        except (ValueError, TypeError):
            return False
    if query is None:
        return True  # Service and default-user keys have no course policy.
    if course is None and courses is not None:
        course = courses.find_one(query)
    if not course or course.get("is_active", True) is not True:
        return False
    owner_type = _identifier(key.get("owner_type")) or "person"
    owner_id = _identifier(key.get("owner_id"))
    owner = None
    if owner_type == "person" and users is not None:
        owner = users.find_one({"id": owner_id}) or users.find_one({"email": owner_id})
        if owner and owner.get("is_active", True) is not True:
            return False
    limit = owner_key_limit(course, owner_type, owner_id, admin_owner=bool(owner and owner.get("is_admin")))
    slot = key_slot(key)
    return 0 < slot <= limit
