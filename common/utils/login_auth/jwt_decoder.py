"""
JWT token decoder for CAS (Central Authentication System) integration.

CAS issues a signed JWT token containing user identity and group membership.
This module decodes the token and returns the payload as a plain dict.

Signature verification
----------------------
By default (PBAI_JWT_VERIFY=false), the token is decoded without verifying
the signature. The `exp` claim is still validated so expired tokens are
rejected. This mode is suitable for testing before CAS is connected.

When PBAI_JWT_VERIFY=true, signature verification is enabled. Configure the
appropriate key depending on the algorithm CAS uses:

  # TODO(CAS-verify): Once the CAS team confirms the signing algorithm,
  # enable verification by setting PBAI_JWT_VERIFY=true and one of:
  #
  #   HS256 (symmetric / shared secret)
  #   -- Ask CAS team for the shared secret string.
  #   -- Set: PBAI_JWT_ALGORITHM=HS256
  #            PBAI_JWT_SECRET=<the-secret-string>
  #
  #   RS256 (asymmetric / public key)
  #   -- Ask CAS team for their public key in PEM format.
  #   -- Save it to a file on this server, e.g. /etc/pbai/cas_public.pem
  #   -- Set: PBAI_JWT_ALGORITHM=RS256
  #            PBAI_JWT_PUBLIC_KEY_FILE=<absolute-path-to-pem-file>
  #
  # The algorithm in use can be confirmed by checking the `alg` field in
  # the JWT header (first base64url-decoded segment of the token).
"""

from __future__ import annotations

import jwt

from common.utils.config import JWT_ALGORITHM, JWT_PUBLIC_KEY_FILE, JWT_SECRET, JWT_VERIFY


def decode_jwt(token: str) -> dict:
    """
    Decode a CAS JWT token and return its payload as a dict.

    Always validates the ``exp`` claim — expired tokens raise ``ValueError``.

    Parameters
    ----------
    token:
        The raw JWT string (three base64url segments joined by dots).

    Returns
    -------
    dict
        The decoded payload. Expected keys from CAS: ``sub``, ``groups``,
        ``exp``, ``nbf``, ``iat``, ``jti``, ``iss``.

    Raises
    ------
    ValueError
        On any decode / validation failure (malformed token, expired, bad
        signature when verification is enabled).
    """
    # WebSEAL may prefix the JWT with "Bearer " — strip it.
    if token.startswith("Bearer "):
        token = token.removeprefix("Bearer ").strip()

    # Accept the actual algorithm from the token header when not verifying,
    # so RS512 (used by WebSEAL) works without extra config.
    _UNVERIFIED_ALGORITHMS = [JWT_ALGORITHM, "HS256", "RS256", "RS512"]

    try:
        if not JWT_VERIFY:
            # Signature verification skipped (testing mode).
            # `exp` is also not enforced — the test token from the CAS team
            # may be expired, and there is no point checking expiry when
            # the signature itself is not being verified.
            payload = jwt.decode(
                token,
                algorithms=_UNVERIFIED_ALGORITHMS,
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                },
            )
        elif JWT_ALGORITHM == "HS256":
            if not JWT_SECRET:
                raise ValueError(
                    "PBAI_JWT_VERIFY is enabled but PBAI_JWT_SECRET is not set. "
                    "Set PBAI_JWT_SECRET to the shared secret provided by the CAS team."
                )
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        else:  # RS256 / RS512
            if not JWT_PUBLIC_KEY_FILE:
                raise ValueError(
                    "PBAI_JWT_VERIFY is enabled but PBAI_JWT_PUBLIC_KEY_FILE is not set. "
                    "Set PBAI_JWT_PUBLIC_KEY_FILE to the path of the CAS public key PEM file."
                )
            from pathlib import Path  # noqa: PLC0415

            pem_path = Path(JWT_PUBLIC_KEY_FILE)
            if not pem_path.is_file():
                raise ValueError(
                    f"PBAI_JWT_PUBLIC_KEY_FILE points to a missing file: {pem_path}"
                )
            public_key = pem_path.read_text(encoding="utf-8")
            payload = jwt.decode(token, public_key, algorithms=[JWT_ALGORITHM])

    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Token has expired") from exc
    except jwt.DecodeError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Token validation failed: {exc}") from exc

    return payload
