"""Supabase access-token validation for FastAPI routes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str
    name: str


_bearer = HTTPBearer(auto_error=False)


def _supabase_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _supabase_publishable_key() -> str:
    return os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()


@lru_cache(maxsize=4)
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")


def _user_from_payload(payload: dict[str, Any]) -> AuthenticatedUser:
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication token has no user identity.")
    metadata = payload.get("user_metadata") if isinstance(payload.get("user_metadata"), dict) else {}
    email = str(payload.get("email") or "").strip()
    name = str(metadata.get("full_name") or metadata.get("name") or email).strip()
    return AuthenticatedUser(id=user_id, email=email, name=name)


def _validate_with_supabase_userinfo(token: str, supabase_url: str) -> AuthenticatedUser:
    publishable_key = _supabase_publishable_key()
    if not publishable_key:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    try:
        response = requests.get(
            f"{supabase_url}/auth/v1/user",
            headers={"apikey": publishable_key, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    payload = response.json()
    payload["sub"] = payload.get("id") or payload.get("sub")
    payload["user_metadata"] = payload.get("user_metadata") or payload.get("raw_user_meta_data") or {}
    return _user_from_payload(payload)


def validate_access_token(token: str) -> AuthenticatedUser:
    supabase_url = _supabase_url()
    if not supabase_url:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    try:
        signing_key = _jwks_client(supabase_url).get_signing_key_from_jwt(token)
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            issuer=f"{supabase_url}/auth/v1",
        )
    except jwt.PyJWTError:
        return _validate_with_supabase_userinfo(token, supabase_url)
    return _user_from_payload(payload)


def optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser | None:
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer authentication is required.")
    return validate_access_token(credentials.credentials)


def require_user(user: Annotated[AuthenticatedUser | None, Depends(optional_user)]) -> AuthenticatedUser:
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user
