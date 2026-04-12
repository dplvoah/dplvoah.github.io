"""Identity-based permission utilities for memory read/write/update."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
PERMISSIONS_PATH: Final[Path] = ROOT_DIR / "ai_context" / "memory_permissions.yaml"

DEFAULT_PERMISSION: Final[dict[str, bool]] = {
    "personalized_read": False,
    "memory_write": False,
    "memory_update": False,
}
DEFAULT_UNAUTHORIZED_BEHAVIOR: Final[dict[str, str]] = {
    "discussion_reply": "skip",
    "blog_comment": "skip",
    "ai_post": "allow_generic",
}


@dataclass(frozen=True)
class IdentityPermission:
    """Permission flags for one identity account."""

    personalized_read: bool
    memory_write: bool
    memory_update: bool


class MemoryAccessError(Exception):
    """Raised when memory permission config is invalid."""


def normalize_account(account: str) -> str:
    """Normalize account id for case-insensitive lookup."""
    return str(account).strip().lower()


def to_identity_permission(raw: dict[str, Any]) -> IdentityPermission:
    """Convert mapping to typed permission object."""
    return IdentityPermission(
        personalized_read=bool(raw.get("personalized_read", False)),
        memory_write=bool(raw.get("memory_write", False)),
        memory_update=bool(raw.get("memory_update", False)),
    )


@lru_cache(maxsize=1)
def load_permission_config() -> dict[str, Any]:
    """
    Load permission YAML config.

    Returns:
        Parsed mapping.

    Raises:
        MemoryAccessError: If config is missing or malformed.
    """
    if not PERMISSIONS_PATH.exists() or not PERMISSIONS_PATH.is_file():
        raise MemoryAccessError(f"Missing memory permissions file: {PERMISSIONS_PATH}")

    try:
        raw = yaml.safe_load(PERMISSIONS_PATH.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise MemoryAccessError(
            f"Failed to read memory permissions file: {PERMISSIONS_PATH}"
        ) from exc
    except yaml.YAMLError as exc:
        raise MemoryAccessError(
            f"Invalid YAML in memory permissions file: {PERMISSIONS_PATH}"
        ) from exc

    if not isinstance(raw, dict):
        raise MemoryAccessError("Memory permissions root must be a mapping.")

    identities = raw.get("identities") or {}
    if identities and not isinstance(identities, dict):
        raise MemoryAccessError("'identities' must be a mapping.")

    defaults = raw.get("defaults") or {}
    if defaults and not isinstance(defaults, dict):
        raise MemoryAccessError("'defaults' must be a mapping.")

    unauthorized_behavior = raw.get("unauthorized_behavior") or {}
    if unauthorized_behavior and not isinstance(unauthorized_behavior, dict):
        raise MemoryAccessError("'unauthorized_behavior' must be a mapping.")

    normalized_identities: dict[str, IdentityPermission] = {}
    for key, value in identities.items():
        if not isinstance(key, str) or not key.strip():
            raise MemoryAccessError("Identity account keys must be non-empty strings.")
        if not isinstance(value, dict):
            raise MemoryAccessError(
                f"Identity '{key}' permissions must be a mapping."
            )
        normalized_identities[normalize_account(key)] = to_identity_permission(value)

    default_permission = to_identity_permission({**DEFAULT_PERMISSION, **defaults})
    normalized_behavior = {
        str(key).strip(): str(value).strip()
        for key, value in {
            **DEFAULT_UNAUTHORIZED_BEHAVIOR,
            **unauthorized_behavior,
        }.items()
        if str(key).strip()
    }

    return {
        "identities": normalized_identities,
        "default_permission": default_permission,
        "unauthorized_behavior": normalized_behavior,
    }


def get_identity_permission(account: str) -> IdentityPermission:
    """
    Resolve permission flags for an account.

    Args:
        account: Account/login identifier.

    Returns:
        Identity permission object (default deny when missing).
    """
    config = load_permission_config()
    normalized = normalize_account(account)
    if not normalized:
        return config["default_permission"]
    return config["identities"].get(normalized, config["default_permission"])


def can_personalized_read(account: str) -> bool:
    """Whether account can trigger personalized memory read."""
    return get_identity_permission(account).personalized_read


def can_memory_write(account: str) -> bool:
    """Whether account can trigger stable-memory writes."""
    return get_identity_permission(account).memory_write


def can_memory_update(account: str) -> bool:
    """Whether account can trigger automatic memory updates."""
    return get_identity_permission(account).memory_update


def unauthorized_behavior_for_channel(channel: str) -> str:
    """
    Return behavior policy for unauthorized identity in one channel.

    Known behavior values are policy-defined (e.g. skip / allow_generic).
    """
    config = load_permission_config()
    normalized_channel = str(channel).strip()
    if not normalized_channel:
        return "skip"
    return str(config["unauthorized_behavior"].get(normalized_channel, "skip")).strip()

