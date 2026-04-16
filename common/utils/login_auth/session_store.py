"""
Implements in-memory session token storage with expiry.
It creates, validates, refreshes, and deletes sessions under thread-safe locking.
It is needed for authenticated API access flow.
"""

from __future__ import annotations

import secrets
import threading
import time

class SessionStore:

    def __init__(self, timeout: int = 1800) -> None:
        self._timeout = timeout
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(
        self,
        username: str,
        groups: list[str] | None = None,
        role: str = "user",
        helpers: list[str] | None = None,
        access_to: list[str] | None = None,
        is_auditor: bool = False,
    ) -> str:
        token = secrets.token_hex(32)
        with self._lock:
            self._sessions[token] = {
                "username": username,
                "groups": groups or [],
                "role": role,
                "helpers": helpers or [],
                "access_to": access_to or [],
                "is_auditor": is_auditor,
                "expires_at": time.time() + self._timeout,
            }
        return token

    def validate(self, token: str) -> str | None:
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            if time.time() > session["expires_at"]:
                del self._sessions[token]
                return None
            session["expires_at"] = time.time() + self._timeout
            return session["username"]

    def get_session_data(self, token: str) -> dict | None:
        """Return the full session dict (username, groups, role, helpers) or None."""
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            if time.time() > session["expires_at"]:
                del self._sessions[token]
                return None
            session["expires_at"] = time.time() + self._timeout
            return dict(session)

    def delete(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)
