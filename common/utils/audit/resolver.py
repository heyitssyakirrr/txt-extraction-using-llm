"""
Resolves canonical audit directory paths.
It maps helper codes and usernames to deterministic audit storage locations.
It is needed to keep audit read and write paths aligned.
"""

from __future__ import annotations

from pathlib import Path

from common.utils.config import AUDIT_LOG_DIR
from common.utils.helpers import HELPER_CODES


def audit_dir_for(helper_code: str, username: str | None = None) -> Path:
    """Canonical audit log path resolver.

    Single source of truth for audit log directories used by both the write
    path (writer.py) and the read path (admin_sessions.py).

    Args:
        helper_code: HELPER_CODES key, e.g. "01" for "policy_helper".
        username: When supplied, appends the user subdirectory.

    Returns:
        Resolved Path for the audit log directory.
    """
    helper_name = HELPER_CODES.get(helper_code, f"helper-{helper_code}")
    base = Path(AUDIT_LOG_DIR) / helper_name / "audit_logs"
    return base / username if username else base

