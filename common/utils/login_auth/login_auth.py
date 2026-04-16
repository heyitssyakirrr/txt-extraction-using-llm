"""
Implements top-level login authentication adapter behavior.
It delegates session management through the session store.
It is needed to keep route handlers independent from auth provider details.
"""

from __future__ import annotations

from .session_store import SessionStore

__all__ = [
    "SessionStore",
]
