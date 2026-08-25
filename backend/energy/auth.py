"""Backend-to-backend Bearer authentication for the Energy API.

The shared secret is read server-side from ENERGY_API_TOKEN. It is NEVER:
  - exposed to the frontend,
  - returned by any endpoint,
  - written to logs.

Contract:
  - Missing Authorization header      -> 401
  - Malformed / non-Bearer scheme      -> 401
  - Wrong token                        -> 401 (constant-time comparison)
  - If ENERGY_API_TOKEN is not set on the server -> 503 (misconfiguration),
    so that data routes are never accidentally left open when auth is expected.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


def _expected_token() -> str:
    return os.environ.get("ENERGY_API_TOKEN", "")


async def require_bearer(authorization: str = Header(default="")) -> None:
    """FastAPI dependency enforcing `Authorization: Bearer <token>`."""
    expected = _expected_token()
    if not expected:
        # Fail closed: do not serve telematics data if auth is misconfigured.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Energy API auth is not configured on the server.",
        )

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # constant-time comparison; never log either value
    if not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
