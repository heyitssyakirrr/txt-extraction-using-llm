"""
Loads, resolves, and manages AD group-based access control via group_access.json.
It maps AD group CNs to helper access and admin status.
It is needed for the AD-driven access control mode.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger("group_access")


def load_group_access(path: Path, *, silent: bool = False) -> dict:
    """Read and parse group_access.json from disk."""
    if not path.exists():
        logger.warning("group_access.json not found at %s, starting with empty config", path)
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        logger.warning("group_access.json is empty at %s, starting with empty config", path)
        return {}
    data = json.loads(text)
    if not silent:
        logger.info("Loaded group_access.json: %d group(s)", len(data))
    return data


def collect_access_to_groups(group_access: dict) -> list[str]:
    """Return a sorted list of all unique access_to values across all CN entries."""
    result: set[str] = set()
    for config in group_access.values():
        result.update(config.get("access_to", []))
    return sorted(result)


def resolve_user_access(
    user_cns: list[str],
    group_access: dict,
) -> tuple[list[str], list[str], list[str], bool, bool, list[str]]:
    """Resolve a user's effective access from their AD group CNs.

    Returns:
        (matched_groups, union_helpers, union_access_to, is_admin, is_auditor, unknown_cns)
    """
    matched_groups: list[str] = []
    helpers: set[str] = set()
    access_to: set[str] = set()
    is_admin = False
    is_auditor = False
    unknown_cns: list[str] = []

    for cn in user_cns:
        config = group_access.get(cn)
        if config is None:
            unknown_cns.append(cn)
            continue
        matched_groups.append(cn)
        helpers.update(config.get("helpers", []))
        access_to.update(config.get("access_to", []))
        if config.get("is_admin", False):
            is_admin = True
        if config.get("is_auditor", False):
            is_auditor = True

    return matched_groups, sorted(helpers), sorted(access_to), is_admin, is_auditor, unknown_cns


def load_master_users(path: Path) -> list[str]:
    """Read master_users.json from disk. Returns a list of usernames."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    return data if isinstance(data, list) else []


def save_master_users(path: Path, users: list[str]) -> None:
    """Write the master users list to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(set(users)), indent=2), encoding="utf-8")
    logger.info("Saved master_users.json: %d user(s)", len(users))


def reload_group_access(
    app_state: object,
    path: Path,
    lock: threading.Lock | None = None,
) -> dict:
    """Re-read group_access.json from disk and swap into app_state under lock.

    Returns the newly loaded dict.
    """
    new_data = load_group_access(path)
    the_lock = lock or getattr(app_state, "group_access_lock", None)
    if the_lock:
        with the_lock:
            app_state.group_access = new_data  # type: ignore[attr-defined]
    else:
        app_state.group_access = new_data  # type: ignore[attr-defined]
    logger.info("Reloaded group_access: %d group(s)", len(new_data))
    return new_data
