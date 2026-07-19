from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from uuid import uuid4

API_KEY_PREFIX = "sk_kent_"
API_KEY_ID_PREFIX = "akid_"
HIDDEN_API_KEY_PREFIX = "sk_kent_hidden_"
HIDDEN_API_KEY_CONTEXT = "rocky:user-default-api-key:v1:"


def generate_api_key_id() -> str:
    """Return a non-secret public identifier for an API key record."""
    return f"{API_KEY_ID_PREFIX}{uuid4().hex}"


def generate_api_key_pair() -> tuple[str, str]:
    """Return (plaintext_key, sha256_hash)."""
    plaintext_key = f"{API_KEY_PREFIX}{secrets.token_hex(32)}"
    return plaintext_key, hash_api_key(plaintext_key)


def hash_api_key(plaintext_key: str) -> str:
    normalized_key = plaintext_key.strip() if isinstance(plaintext_key, str) else ""
    if not normalized_key:
        return ""
    return hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()


def _hidden_api_key_secret(secret: str | None = None) -> str:
    configured_secret = secret
    if configured_secret is None:
        configured_secret = os.getenv("ROCKY_HIDDEN_API_KEY_SECRET") or os.getenv("ROCKY_CHAT_API_KEY") or ""
    return configured_secret.strip()


def derive_hidden_api_key(owner_id: str, secret: str | None = None) -> str:
    normalized_owner_id = owner_id.strip().lower() if isinstance(owner_id, str) else ""
    if not normalized_owner_id:
        raise ValueError("owner_id is required for hidden API key derivation.")

    configured_secret = _hidden_api_key_secret(secret)
    if not configured_secret:
        raise RuntimeError("ROCKY_HIDDEN_API_KEY_SECRET or ROCKY_CHAT_API_KEY is required.")

    digest = hmac.new(
        configured_secret.encode("utf-8"),
        f"{HIDDEN_API_KEY_CONTEXT}{normalized_owner_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{HIDDEN_API_KEY_PREFIX}{digest}"


def generate_hidden_api_key_pair(owner_id: str, secret: str | None = None) -> tuple[str, str]:
    plaintext_key = derive_hidden_api_key(owner_id, secret)
    return plaintext_key, hash_api_key(plaintext_key)
