"""
Defines shared mutable application state container types.
It declares state fields and dependency helpers for request-time state access.
It is needed to coordinate indexes, sessions, and access maps safely.
"""

from __future__ import annotations

import dataclasses
import threading
from typing import cast

from fastapi import Request

from common.utils.config import MASTER_USERS_FILE, SESSION_TIMEOUT
from common.utils.group_access import load_master_users
from common.utils.login_auth.login_auth import SessionStore


@dataclasses.dataclass
class AppState:
    """Explicit container for all shared mutable app state.

    Stored on app.state.pbai in main.py during lifespan.
    Route handlers access it via Depends(get_pbai_state).
    Non-request code (e.g. index_manager) receives it as an explicit parameter.
    """
    indexes: dict = dataclasses.field(default_factory=dict)
    index_lock: threading.RLock = dataclasses.field(default_factory=threading.RLock)
    group_access: dict = dataclasses.field(default_factory=dict)
    group_access_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    master_users: list = dataclasses.field(
        default_factory=lambda: load_master_users(MASTER_USERS_FILE)
    )
    master_users_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    store: SessionStore = dataclasses.field(
        default_factory=lambda: SessionStore(timeout=SESSION_TIMEOUT)
    )


# Single process-wide instance - exposed via app.state.pbai in main.py
_app_state = AppState()


def get_pbai_state(request: Request) -> AppState:
    """FastAPI dependency: retrieve the shared AppState from the request."""
    return cast(AppState, request.app.state.pbai)
