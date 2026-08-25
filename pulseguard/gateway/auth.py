import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from pulseguard.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    # secrets.compare_digest, not `!=` — a plain string comparison short-circuits
    # on the first mismatched byte, letting an attacker recover the key one
    # character at a time from response-time differences.
    if not api_key or not secrets.compare_digest(api_key, settings.pulseguard_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
