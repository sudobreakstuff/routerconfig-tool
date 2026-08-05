"""API authentication for RouterConfig Pro.

Generates and stores a per-install bearer token in the RC data directory
(RC_DATA_DIR or ~/.routerconfig). Every protected endpoint requires it via the
`require_token` dependency. The token is delivered to the renderer only through
the Electron preload/IPC bridge so it never lives in the browser.
"""
import hashlib
import os
import secrets
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

DATA_DIR = Path(os.environ.get("RC_DATA_DIR", Path.home() / ".routerconfig"))
TOKEN_PATH = DATA_DIR / "api_token.txt"

_bearer = HTTPBearer(auto_error=False)


def get_api_token() -> str:
    """Return the instance token, generating one on first use."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(token)
    return token


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """FastAPI dependency enforcing the bearer token on protected routes."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if not secrets.compare_digest(credentials.credentials, get_api_token()):
        raise HTTPException(status_code=401, detail="Invalid API token")