"""Authentication router.

Implements the Google OAuth 2.0 authorization-code flow and issues
JWT access/refresh token pairs for use by the React frontend.

Flow:
    1. Frontend redirects user to GET /auth/google/login
    2. Google redirects back to GET /auth/google/callback?code=...
    3. Backend exchanges the code for a Google access token
    4. Backend fetches the user's Google profile
    5. Backend upserts the user into the database and issues its own JWT pair
"""
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user_payload
from app.models.orm_models import Role, User
from app.security.security import create_access_token, create_refresh_token

router = APIRouter()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


# ── Response / payload models ──────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """JWT token pair returned after successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class GoogleUserInfo(BaseModel):
    """Minimal Google profile fields needed to identify the user."""

    sub: str
    email: str
    name: str
    picture: str


class GoogleIDTokenRequest(BaseModel):
    """Request body for ID-token based login from @react-oauth/google."""

    credential: str


class MeResponse(BaseModel):
    """Current user's profile, sourced from the Users table."""

    name: str
    email: str
    picture: str | None = None
    role: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/google/login",
    summary="Initiate Google OAuth login",
    description="Redirects the browser to Google's consent screen.",
    status_code=status.HTTP_302_FOUND,
)
async def google_login() -> RedirectResponse:
    """Build the Google authorization URL and redirect the user to it."""
    params: Dict[str, str] = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{_GOOGLE_AUTH_URL}?{query_string}")


@router.get(
    "/google/callback",
    response_model=TokenResponse,
    summary="Handle Google OAuth callback",
    description=(
        "Receives the authorization code from Google, exchanges it for "
        "user profile data, and returns a JWT access/refresh token pair."
    ),
)
async def google_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange the Google authorization *code* for an application JWT pair.

    Args:
        code: The one-time authorization code provided by Google in the redirect.
        db: Async database session used to upsert the authenticated user.

    Returns:
        A TokenResponse containing the access token and refresh token.

    Raises:
        HTTPException 400: If Google rejects the code exchange or user-info fetch.
        HTTPException 503: If the Roles table has not been seeded.
    """
    google_user = await _exchange_code_for_user_info(code)
    user_id, role_name = await _upsert_user(db, google_user)
    token_payload: Dict[str, Any] = {
        "sub": user_id,
        "email": google_user.email,
        "name": google_user.name,
        "role": role_name,
    }
    return TokenResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
    )


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Exchange Google ID token for application JWT",
    description=(
        "Accepts a Google ID token issued by @react-oauth/google, verifies it "
        "against Google's tokeninfo endpoint, and returns a JWT access/refresh pair."
    ),
)
async def google_id_token_login(
    body: GoogleIDTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Verify a Google ID token and issue an application JWT pair.

    Args:
        body: Contains the Google ID token from the @react-oauth/google button.
        db: Async database session used to upsert the authenticated user.

    Returns:
        A TokenResponse containing the access token and refresh token.

    Raises:
        HTTPException 401: If the ID token is invalid or audience does not match.
        HTTPException 503: If the Roles table has not been seeded.
    """
    google_user = await _verify_google_id_token(body.credential)
    user_id, role_name = await _upsert_user(db, google_user)
    token_payload: Dict[str, Any] = {
        "sub": user_id,
        "email": google_user.email,
        "name": google_user.name,
        "role": role_name,
    }
    return TokenResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
    )


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get the authenticated user's profile",
    description=(
        "Returns the calling user's name, email, avatar, and role from the "
        "Users table. Requires a valid JWT Bearer token."
    ),
)
async def get_me(
    payload: Dict[str, Any] = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Return the current user's profile from the database.

    Args:
        payload: Decoded JWT payload (provides ``sub`` = user UUID).
        db: Async database session.

    Returns:
        MeResponse with name, email, picture, role.

    Raises:
        HTTPException 404: If no user matches the token's subject.
    """
    user_id = payload.get("sub", "")
    result = await db.execute(
        select(User, Role.RoleName)
        .join(Role, User.RoleId == Role.RoleId)
        .where(User.UserId == user_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user, role_name = row
    return MeResponse(
        name=user.Name,
        email=user.Email,
        picture=user.Picture,
        role=role_name,
    )


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _upsert_user(
    db: AsyncSession, google_user: GoogleUserInfo
) -> Tuple[str, str]:
    """Find-or-create a User row for the given Google profile.

    Lookup order: by GoogleSub, then by Email (covers users created before
    the GoogleSub column was populated). The role is determined from
    ``settings.admin_emails_list``; the matching ``Role`` row supplies the FK.

    Returns:
        ``(user_id, role_name)`` — the database UUID and the resolved role.

    Raises:
        HTTPException 503: If the Roles table is missing the expected entry.
    """
    role_name = "admin" if google_user.email.lower() in settings.admin_emails_list else "user"
    try:
        role_result = await db.execute(select(Role).where(Role.RoleName == role_name))
        role = role_result.scalar_one()
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Role configuration missing — seed Roles table before login",
        ) from exc

    user_result = await db.execute(select(User).where(User.GoogleSub == google_user.sub))
    user = user_result.scalar_one_or_none()
    if user is None:
        user_result = await db.execute(select(User).where(User.Email == google_user.email))
        user = user_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            UserId=str(uuid4()),
            Email=google_user.email,
            Name=google_user.name,
            Picture=google_user.picture or None,
            GoogleSub=google_user.sub,
            IsActive=True,
            RoleId=role.RoleId,
            CreatedAt=now,
            UpdatedAt=now,
        )
        db.add(user)
    else:
        user.Name = google_user.name
        user.Picture = google_user.picture or user.Picture
        user.GoogleSub = google_user.sub
        user.UpdatedAt = now

    await db.flush()
    return user.UserId, role_name


async def _exchange_code_for_user_info(code: str) -> GoogleUserInfo:
    """Exchange an authorization code for a GoogleUserInfo object.

    Steps:
        1. POST the code to Google's token endpoint to get a Google access token.
        2. Use that access token to GET the user's profile from Google's userinfo endpoint.

    Raises:
        HTTPException 400: On any failure from Google's APIs.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        google_access_token = await _fetch_google_access_token(client, code)
        return await _fetch_google_user_info(client, google_access_token)


async def _fetch_google_access_token(client: httpx.AsyncClient, code: str) -> str:
    """POST to Google's token endpoint and return the access_token string."""
    response = await client.post(
        _GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        },
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code with Google",
        )
    token_data: Dict[str, Any] = response.json()
    access_token: str = token_data.get("access_token", "")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token response did not include an access_token",
        )
    return access_token


async def _fetch_google_user_info(client: httpx.AsyncClient, access_token: str) -> GoogleUserInfo:
    """GET the user's Google profile using *access_token*."""
    response = await client.get(
        _GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to retrieve user profile from Google",
        )
    return GoogleUserInfo(**response.json())


async def _verify_google_id_token(id_token: str) -> GoogleUserInfo:
    """Verify a Google ID token via Google's tokeninfo endpoint.

    Args:
        id_token: The Google-issued ID token string from @react-oauth/google.

    Returns:
        A GoogleUserInfo populated from the verified token claims.

    Raises:
        HTTPException 401: If the token is invalid or audience does not match.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            _GOOGLE_TOKENINFO_URL,
            params={"id_token": id_token},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token verification failed",
        )
    claims: Dict[str, Any] = response.json()
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token audience mismatch",
        )
    return GoogleUserInfo(
        sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name", claims["email"]),
        picture=claims.get("picture", ""),
    )
