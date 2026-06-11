"""FastAPI dependencies."""
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from src.models.config import Settings, load_settings
from src.models.responses import ValidatedJWTUser

security = HTTPBearer(auto_error=False)


async def get_tsxv50_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> None:
    """Validate static Bearer token for machine-to-machine TSXV50 endpoints."""
    settings = load_settings()
    if not credentials or credentials.credentials != settings.tsxv50_api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_settings() -> Settings:
    """Get cached settings."""
    return load_settings()


async def get_validated_jwt_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> ValidatedJWTUser:
    """Validate JWT via JWKS and return user_id. No company lookup."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    settings = load_settings()
    jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    try:
        jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=600)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})

        return ValidatedJWTUser(user_id=user_id)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
