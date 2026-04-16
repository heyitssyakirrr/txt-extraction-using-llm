"""
Writes file operation events to system-wide audit JSON files.
It records upload, delete, and assign actions with timestamp, username, and filename.
It is needed for compliance traceability of document lifecycle changes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common.utils.config import AUDIT_LOG_DIR, FILE_AUDIT_FORMAT

logger = logging.getLogger("PBAI.file_audit")

_TZ_MYT = timezone(timedelta(hours=8))


def write_file_audit(username: str, action: str, file: str) -> None:
    """Append a file operation entry to the system-wide audit log.

    The audit file is rotated by day (``YYYY-MM-DD``) or month (``YYYY-MM``)
    depending on ``PBAI_FILE_AUDIT_FORMAT``.  When the current-period file
    already exists the entry is appended; otherwise a new file is created.

    Args:
        username: Identity of the actor performing the operation.
        action:   Operation type — ``"upload"``, ``"delete"``, or ``"assign"``.
        file:     Filename (basename) of the document affected.
    """
    try:
        now = datetime.now(_TZ_MYT)
        if FILE_AUDIT_FORMAT == "month":
            period = now.strftime("%Y%m")
        else:
            period = now.strftime("%Y%m%d")

        audit_dir = Path(AUDIT_LOG_DIR) / "file_operations"
        audit_dir.mkdir(parents=True, exist_ok=True)

        audit_file = audit_dir / f"file_audit_{period}.json"
        entry = {
            "timestamp": now.isoformat(),
            "username": username,
            "action": action,
            "file": file,
        }

        if audit_file.exists():
            with open(audit_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
            data.append(entry)
        else:
            data = [entry]

        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as exc:
        logger.error("Failed to write file audit log: %s", exc)
