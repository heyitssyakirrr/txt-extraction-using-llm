"""
Implements authentication-related HTTP endpoints.
It validates credentials or tokens, manages session flow, and returns auth-scoped responses.
It is needed to secure access and connect frontend login behavior to backend state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from common.state import AppState, get_pbai_state
from common.utils.group_access import resolve_user_access
from common.utils.login_auth.jwt_decoder import decode_jwt

router = APIRouter(include_in_schema=False)
logger = logging.getLogger("common.auth")

_CROSSROAD_DIR = Path(__file__).resolve().parent.parent / "frontend" / "login_crossroad"
_ACCESS_CONTROL_DIR = Path(__file__).resolve().parent.parent / "frontend" / "access_control"

class _LoginRequest(BaseModel):
    token: str | None = None

@router.post("/api/auth-mode")
def auth_mode():
    """Returns the active authentication mode so the frontend can render the correct login form."""
    return {"mode": "cas"}

@router.post("/", response_class=FileResponse)
def login_page():
    return FileResponse(_CROSSROAD_DIR / "login.html", headers={"Cache-Control": "no-cache"})

@router.post("/crossroad", response_class=FileResponse)
def crossroad_page():
    return FileResponse(_CROSSROAD_DIR / "crossroad.html", headers={"Cache-Control": "no-cache"})

@router.post("/access-control", response_class=FileResponse)
def access_control_page():
    return FileResponse(_ACCESS_CONTROL_DIR / "index.html", headers={"Cache-Control": "no-cache"})

@router.post("/login")
def login(req: _LoginRequest, pbai: AppState = Depends(get_pbai_state)):
    if not req.token:
        raise HTTPException(status_code=422, detail="Token is required")
    return _login_cas(req.token.strip(), pbai)


def _login_cas(jwt_token: str, pbai: AppState) -> dict:
    try:
        payload = decode_jwt(jwt_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    username = payload.get("sub")
    user_cns = payload.get("groups")

    if not username:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    # CAS may emit groups as a comma-separated string instead of a list
    if isinstance(user_cns, str):
        user_cns = [g.strip() for g in user_cns.split(",") if g.strip()]
    if not isinstance(user_cns, list):
        raise HTTPException(status_code=401, detail="Token missing or invalid 'groups' claim")

    with pbai.group_access_lock:
        ga_snapshot = dict(pbai.group_access)

    matched_groups, helpers, access_to, is_admin, is_auditor, unknown_cns = resolve_user_access(user_cns, ga_snapshot)

    with pbai.master_users_lock:
        is_master_override = username in pbai.master_users
    if is_master_override:
        if "master" not in matched_groups:
            matched_groups = list(matched_groups) + ["master"]
        is_admin = True

    role = "Admin" if is_admin else "user"
    session_token = pbai.store.create(username, groups=matched_groups, role=role, helpers=helpers, access_to=access_to, is_auditor=is_auditor)
    logger.info("Login (CAS): %s (role=%s, groups=%s, access_to=%s, unknown_cns=%s)", username, role, matched_groups, access_to, unknown_cns)
    return {"token": session_token, "username": username, "role": role, "groups": matched_groups, "access_to": access_to, "is_auditor": is_auditor}


@router.post("/logout")
def logout(authorization: str = Header(...), pbai: AppState = Depends(get_pbai_state)):
    if authorization.startswith("Bearer "):
        pbai.store.delete(authorization.removeprefix("Bearer ").strip())
    return {"message": "Logged out"}


@router.post("/api/cas-session")
def cas_session(
    request: Request,
    iv_jwt: str = Header(default=""),
    iv_user: str = Header(default=""),
    iv_groups: str = Header(default=""),
    authorization: str = Header(default=""),
    pbai: AppState = Depends(get_pbai_state),
):
    """Create (or reuse) a session from WebSEAL-injected headers.

    Supports three modes (tried in order):
      1. Existing valid session token in ``Authorization: Bearer ...``
      2. ``iv-jwt`` header containing a signed JWT with sub+groups claims
      3. ``iv-user`` + ``iv-groups`` headers injected by WebSEAL junction
    """
    # Peek at the incoming CAS identity to detect user switches.
    # If the existing session belongs to a different user, skip the fast path
    # and create a fresh session for the new CAS user.
    incoming_username: str | None = None
    if iv_jwt:
        try:
            incoming_username = decode_jwt(iv_jwt).get("sub")
        except ValueError:
            pass  # will fail properly in Mode A below
    elif iv_user:
        incoming_username = iv_user.strip() or None

    # --- fast path: caller already has a valid session for the same user ---
    if authorization.startswith("Bearer "):
        existing_token = authorization.removeprefix("Bearer ").strip()
        session_data = pbai.store.get_session_data(existing_token)
        if session_data and (
            incoming_username is None
            or session_data["username"] == incoming_username
        ):
            return {
                "token":      existing_token,
                "username":   session_data["username"],
                "role":       session_data["role"],
                "groups":     session_data["groups"],
                "access_to":  session_data.get("access_to", []),
                "is_auditor": session_data.get("is_auditor", False),
            }
        if session_data and incoming_username and session_data["username"] != incoming_username:
            logger.info(
                "CAS user switch detected: existing session for %s, new CAS user %s — creating new session",
                session_data["username"], incoming_username,
            )

    # --- Mode A: decode iv-jwt (CAS JWT) ----------------------------------
    if iv_jwt:
        try:
            payload = decode_jwt(iv_jwt)
        except ValueError as exc:
            logger.warning("CAS auto-session: iv-jwt decode failed: %s", exc)
            raise HTTPException(status_code=401, detail=str(exc))

        username = payload.get("sub")
        user_cns = payload.get("groups")

        if not username:
            raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
        # CAS may emit groups as a comma-separated string instead of a list
        if isinstance(user_cns, str):
            user_cns = [g.strip() for g in user_cns.split(",") if g.strip()]
        if not isinstance(user_cns, list):
            raise HTTPException(status_code=401, detail="Token missing or invalid 'groups' claim")

    # --- Mode B: iv-user + iv-groups headers from WebSEAL -----------------
    elif iv_user:
        username = iv_user.strip()
        # iv-groups is typically comma-separated or double-quoted CSV
        raw_groups = iv_groups.strip().strip('"')
        user_cns = [g.strip() for g in raw_groups.split(",") if g.strip()] if raw_groups else []
        logger.info("CAS auto-session via iv-user=%s, iv-groups=%s", username, user_cns)
    else:
        # Log all headers to help diagnose what WebSEAL sends
        hdr_names = sorted(request.headers.keys())
        logger.warning(
            "CAS auto-session: no iv-jwt or iv-user header found. "
            "Available headers: %s",
            hdr_names,
        )
        raise HTTPException(
            status_code=401,
            detail="No iv-jwt or iv-user header present. "
                   f"Headers received: {hdr_names}",
        )

    with pbai.group_access_lock:
        ga_snapshot = dict(pbai.group_access)

    matched_groups, helpers, access_to, is_admin, is_auditor, unknown_cns = resolve_user_access(user_cns, ga_snapshot)

    with pbai.master_users_lock:
        is_master_override = username in pbai.master_users
    if is_master_override:
        if "master" not in matched_groups:
            matched_groups = list(matched_groups) + ["master"]
        is_admin = True

    role = "Admin" if is_admin else "user"
    session_token = pbai.store.create(
        username, groups=matched_groups, role=role,
        helpers=helpers, access_to=access_to, is_auditor=is_auditor,
    )
    logger.info(
        "CAS auto-session: %s (role=%s, groups=%s, access_to=%s, unknown_cns=%s)",
        username, role, matched_groups, access_to, unknown_cns,
    )
    return {
        "token":      session_token,
        "username":   username,
        "role":       role,
        "groups":     matched_groups,
        "access_to":  access_to,
        "is_auditor": is_auditor,
        "cas_jwt":    iv_jwt,
    }


@router.post("/api/debug-headers")
def debug_headers(request: Request):
    """Return all request headers. Use this to see what WebSEAL injects.

    Send a POST request to /api/debug-headers after CAS authentication.
    WARNING: Remove or guard this endpoint before going to production.
    """
    return {
        "headers": dict(request.headers),
        "url":     str(request.url),
        "note":    "Look for iv-user, iv-groups, iv-jwt, iv-creds, or similar WebSEAL headers.",
    }


@router.post("/api/helpers")
def get_helpers(
    authorization: str = Header(...),
    iv_jwt: str = Header(default=""),
    pbai: AppState = Depends(get_pbai_state),
):
    if iv_jwt:
        try:
            payload = decode_jwt(iv_jwt)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        user_cns = payload.get("groups")
        if isinstance(user_cns, str):
            user_cns = [g.strip() for g in user_cns.split(",") if g.strip()]
        if not isinstance(user_cns, list):
            raise HTTPException(status_code=401, detail="Token missing or invalid 'groups' claim")
        with pbai.group_access_lock:
            ga_snapshot = dict(pbai.group_access)
        _, helpers, _, _, _, _ = resolve_user_access(user_cns, ga_snapshot)
        accessible_ids = set(helpers)
    else:
        token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else authorization
        session_data = pbai.store.get_session_data(token)
        if not session_data:
            raise HTTPException(status_code=401, detail="Session expired or invalid token")
        accessible_ids = set(session_data.get("helpers", []))

    from common.utils.helpers import HELPERS
    return [h for h in HELPERS if h["id"] in accessible_ids]
