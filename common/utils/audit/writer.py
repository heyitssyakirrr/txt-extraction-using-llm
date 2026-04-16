"""
Writes chat interactions to per-session audit JSON files.
It appends user and assistant messages with timestamps, sources, and metadata.
It is needed for traceability and post-session review.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .constants import logger
from .resolver import audit_dir_for


def write_audit_log(
    code: str,
    username: str,
    session_id: str,
    question: str,
    answer: str,
    sources: list,
    meta: dict,
) -> None:
    log_dir = audit_dir_for(code, username)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{session_id}.json"

    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    user_msg      = {"role": "user",      "content": question, "timestamp": now}
    assistant_msg = {"role": "assistant", "content": answer.strip(),   "timestamp": now,
                     "sources": sources,
                     "meta": {
                         "confidence":  meta.get("confidence", 0.0),
                         "search_time": meta.get("search_time"),
                         "gen_time":    meta.get("gen_time"),
                         "total_time":  meta.get("total_time"),
                     }}

    try:
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {"created_at": now, "messages": []}
            data["messages"].extend([user_msg, assistant_msg])
        else:
            data = {"created_at": now, "messages": [user_msg, assistant_msg]}

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as exc:
        logger.error("Failed to write audit log to %s: %s", log_file, exc)

