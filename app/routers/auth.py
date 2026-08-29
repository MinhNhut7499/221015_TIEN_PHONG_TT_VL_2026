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
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_active_user, get_current_user_payload
from app.models.orm_models import Role, User
from app.security.security import (
    TokenError,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    hash_password,
    verify_email_verification_token,
    verify_password,
    verify_password_reset_token,
)
from app.services import account_service, login_session_service, wallet_service
from app.services.email_service import (
    send_password_reset_email,
    send_verification_email,
)
from app.services.system_log_service import LEVEL_INFO, LEVEL_WARNING, log_event

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


class LoginSessionRequest(BaseModel):
    """Request body to register a pending hybrid-app login session."""

    session_id: str


class LoginSessionAck(BaseModel):
    """Acknowledgement that a pending login session was registered."""

    ok: bool = True


class LoginSessionStatusResponse(BaseModel):
    """Poll result for a hybrid-app login session.

    ``status`` is ``pending`` | ``completed`` | ``expired``. The JWT pair is
    present only on the (single) ``completed`` read.
    """

    status: str
    access_token: str | None = None
    refresh_token: str | None = None


class MeResponse(BaseModel):
    """Current user's profile, sourced from the Users table."""

    name: str
    email: str
    picture: str | None = None
    role: str
    # Billing snapshot (token wallet) so the frontend can show balance + tier.
    token_balance: int = 0
    plan_code: str | None = None
    plan_expires_at: datetime | None = None


class AccountDeletionResponse(BaseModel):
    """Result of a self-service account deletion."""

    deleted: bool


class MessageResponse(BaseModel):
    """A generic, non-revealing message response."""

    message: str


class RegisterRequest(BaseModel):
    """Request body for email/password account registration."""

    email: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def email_must_look_valid(cls, value: str) -> str:
        """Trim and require a minimally valid email address."""
        value = value.strip()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Email không hợp lệ")
        return value


class EmailLoginRequest(BaseModel):
    """Request body for email/password login."""

    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    """Request body to start a password-reset flow."""

    email: str


class ResetPasswordRequest(BaseModel):
    """Request body to complete a password reset."""

    token: str
    new_password: str = Field(min_length=8)


class VerifyEmailRequest(BaseModel):
    """Request body to complete email verification (finish registration)."""

    token: str


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
    user_id, role_name, is_active = await _upsert_user(db, google_user)
    await _assert_active_or_block(db, google_user.email, is_active)
    await log_event(db, LEVEL_INFO, f"Login successful: {google_user.email} ({role_name})")
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
    user_id, role_name, is_active = await _upsert_user(db, google_user)
    await _assert_active_or_block(db, google_user.email, is_active)
    await log_event(db, LEVEL_INFO, f"Login successful: {google_user.email} ({role_name})")
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


# ── Hybrid mobile app login (Cloud-Sync Polling) ──────────────────────────────

@router.post(
    "/login-session",
    response_model=LoginSessionAck,
    summary="Register a pending hybrid-app login session",
    description=(
        "Called by the web (running inside the mobile app's WebView) to register "
        "a client-generated session id before the app opens Google login. The "
        "web then polls GET /auth/login-session/{session_id} for the token."
    ),
)
async def create_login_session(
    body: LoginSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginSessionAck:
    """Register (or reset) a pending login session keyed by a UUID v4."""
    _require_valid_session_id(body.session_id)
    await login_session_service.create_session(db, body.session_id)
    return LoginSessionAck()


@router.get(
    "/login-session/{session_id}",
    response_model=LoginSessionStatusResponse,
    summary="Poll a hybrid-app login session for its token",
    description=(
        "Returns 'pending' until the app completes Google login, then 'completed' "
        "with the JWT pair exactly once (the session is consumed on read), then "
        "'expired' afterwards or once the TTL elapses."
    ),
)
async def poll_login_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> LoginSessionStatusResponse:
    """Return the session status, claiming the JWT pair on the first completed read."""
    _require_valid_session_id(session_id)
    result = await login_session_service.poll_session(db, session_id)
    return LoginSessionStatusResponse(**result)


@router.get(
    "/google/login/flutter",
    summary="Initiate Google OAuth login for the mobile app",
    description=(
        "Opened by the Flutter app in a Chrome Custom Tab. Redirects to Google's "
        "consent screen, carrying the session id in the OAuth 'state' so the "
        "callback can store the token against it."
    ),
    status_code=status.HTTP_302_FOUND,
)
async def google_login_flutter(session_id: str) -> RedirectResponse:
    """Redirect the app's browser tab to Google's consent screen."""
    _require_valid_session_id(session_id)
    params: Dict[str, str] = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_FLUTTER_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": session_id,
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{_GOOGLE_AUTH_URL}?{query_string}")


@router.get(
    "/google/callback/flutter",
    response_class=HTMLResponse,
    summary="Handle the mobile app's Google OAuth callback",
    description=(
        "Google redirects here after the app's consent. Verifies the session, "
        "exchanges the code, stores the JWT pair against the session, and returns "
        "a simple HTML page telling the user to close the tab."
    ),
)
async def google_callback_flutter(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Complete the app login by storing the token against the polling session.

    The session in ``state`` is verified (valid UUID v4 + still pending) BEFORE
    the Google code is exchanged, so an unsolicited callback cannot create stray
    accounts. The JWT pair is written only into the still-pending session
    (compare-and-set); tokens are never logged.
    """
    if not _is_valid_session_id(state) or not await login_session_service.session_is_pending(
        db, state
    ):
        return _flutter_result_page(
            "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng thử lại.",
            ok=False,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    google_user = await _exchange_code_for_user_info(
        code, redirect_uri=settings.GOOGLE_FLUTTER_REDIRECT_URI
    )
    user_id, role_name, is_active = await _upsert_user(db, google_user)
    await _assert_active_or_block(db, google_user.email, is_active)
    token_payload: Dict[str, Any] = {
        "sub": user_id,
        "email": google_user.email,
        "name": google_user.name,
        "role": role_name,
    }
    stored = await login_session_service.complete_session(
        db,
        state,
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
        user_id=user_id,
    )
    if not stored:
        return _flutter_result_page(
            "Phiên đăng nhập đã hết hạn. Vui lòng thử lại.", ok=False
        )
    await log_event(
        db, LEVEL_INFO, f"Flutter login successful: {google_user.email} ({role_name})"
    )
    return _flutter_result_page(
        "Đăng nhập thành công! Bạn có thể đóng tab này.", ok=True
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
    wallet = await wallet_service.get_wallet(db, user_id)
    return MeResponse(
        name=user.Name,
        email=user.Email,
        picture=user.Picture,
        role=role_name,
        token_balance=wallet.token_balance if wallet else int(user.TokenBalance or 0),
        plan_code=wallet.current_plan_code if wallet else None,
        plan_expires_at=wallet.plan_expires_at if wallet else user.PlanExpiresAt,
    )


@router.delete(
    "/account",
    response_model=AccountDeletionResponse,
    summary="Delete the authenticated user's own account and data",
    description=(
        "Permanently deletes the caller's projects, uploaded images, analysis "
        "history and personal data, then anonymises the account (PII is scrubbed; "
        "anonymised financial records are retained for accounting). Irreversible. "
        "Requires a valid JWT Bearer token for an active account."
    ),
)
async def delete_my_account(
    payload: Dict[str, Any] = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccountDeletionResponse:
    """Delete the caller's own account; business logic lives in account_service."""
    user_id = payload.get("sub", "")
    result = await account_service.delete_own_account(db, user_id)
    return AccountDeletionResponse(deleted=result.deleted)


# ── Email / password endpoints ───────────────────────────────────────────────

@router.post(
    "/register",
    response_model=MessageResponse,
    summary="Start email/password registration (sends a verification email)",
    description=(
        "Does NOT create the account immediately. Sends a verification link to "
        "the email; the account is created only when the user clicks it "
        "(POST /auth/verify-email), proving the email is real and reachable. "
        "Returns the same generic message whether or not the email is already "
        "in use (no account enumeration)."
    ),
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Begin registration by emailing a verification link (no DB write yet)."""
    generic = MessageResponse(
        message="Vui lòng kiểm tra email để xác minh và hoàn tất đăng ký."
    )
    email = body.email
    result = await db.execute(select(User).where(User.Email == email))
    user = result.scalar_one_or_none()
    # An email that already has a password account cannot re-register. Stay
    # generic (no enumeration); the real owner can use login / forgot-password.
    if user is not None and user.PasswordHash:
        await log_event(db, LEVEL_INFO, f"Registration attempt for existing account: {email}")
        return generic

    token = create_email_verification_token(email, body.name.strip(), hash_password(body.password))
    verify_link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-email?token={token}"
    sent = await send_verification_email(email, verify_link)
    level = LEVEL_INFO if sent else LEVEL_WARNING
    await log_event(db, level, f"Verification email requested: {email} (email sent: {sent})")
    return generic


@router.post(
    "/verify-email",
    response_model=TokenResponse,
    summary="Complete registration by verifying the email",
    description=(
        "Validates the verification token, creates (or attaches a password to) "
        "the account, and returns a JWT access/refresh pair (auto-login)."
    ),
)
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Create the account from a verified email-verification token."""
    try:
        pending = verify_email_verification_token(body.token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Liên kết xác minh không hợp lệ hoặc đã hết hạn.",
        ) from exc

    email = pending["email"]
    now = datetime.now(timezone.utc)
    result = await db.execute(select(User).where(User.Email == email))
    user = result.scalar_one_or_none()

    if user is not None and user.PasswordHash:
        # Already fully registered (e.g. link used twice) — verify by logging in.
        role = await db.get(Role, user.RoleId)
        role_name = role.RoleName if role is not None else "user"
    elif user is not None:
        # Existing Google-only account → attach the verified password (merge).
        user.PasswordHash = pending["password_hash"]
        user.UpdatedAt = now
        role = await db.get(Role, user.RoleId)
        role_name = role.RoleName if role is not None else "user"
    else:
        role_name = "admin" if email.lower() in settings.admin_emails_list else "user"
        role = await _resolve_role(db, role_name)
        user = User(
            UserId=str(uuid4()),
            Email=email,
            Name=pending["name"],
            Picture=None,
            GoogleSub=None,
            PasswordHash=pending["password_hash"],
            IsActive=True,
            RoleId=role.RoleId,
            CreatedAt=now,
            UpdatedAt=now,
        )
        db.add(user)
        await db.flush()
        # One-time signup bonus through the ledger (idempotent per user id).
        await wallet_service.grant_signup_bonus(db, user.UserId)

    await db.flush()
    await _assert_active_or_block(db, email, user.IsActive)
    await log_event(db, LEVEL_INFO, f"Registration verified: {email} ({role_name})")
    token_payload: Dict[str, Any] = {
        "sub": user.UserId,
        "email": email,
        "name": user.Name,
        "role": role_name,
    }
    return TokenResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
    description="Verifies an email/password pair and returns a JWT access/refresh pair.",
)
async def email_login(
    body: EmailLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate an email/password user and issue an application JWT pair."""
    result = await db.execute(
        select(User, Role.RoleName)
        .join(Role, User.RoleId == Role.RoleId)
        .where(User.Email == body.email.strip())
    )
    row = result.first()
    # Generic 401 in every failure case so the response never reveals whether the
    # email exists or which check failed.
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không đúng.",
        )
    user, role_name = row
    if not user.PasswordHash or not verify_password(body.password, user.PasswordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không đúng.",
        )
    await _assert_active_or_block(db, user.Email, user.IsActive)
    await log_event(db, LEVEL_INFO, f"Login successful: {user.Email} ({role_name})")
    token_payload: Dict[str, Any] = {
        "sub": user.UserId,
        "email": user.Email,
        "name": user.Name,
        "role": role_name,
    }
    return TokenResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request a password-reset link",
    description=(
        "Sends a password-reset link to the email if it belongs to an "
        "email/password account. Always returns the same message regardless of "
        "whether the email exists (no account enumeration)."
    ),
)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Email a password-reset link (best-effort, non-revealing)."""
    generic = MessageResponse(
        message="Nếu email tồn tại, chúng tôi đã gửi liên kết đặt lại mật khẩu."
    )
    email = body.email.strip()
    result = await db.execute(select(User).where(User.Email == email))
    user = result.scalar_one_or_none()
    # Only accounts with a password (i.e. not Google-only) can reset a password.
    if user is None or not user.PasswordHash:
        return generic

    token = create_password_reset_token(user.UserId)
    reset_link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={token}"
    sent = await send_password_reset_email(user.Email, reset_link)
    level = LEVEL_INFO if sent else LEVEL_WARNING
    await log_event(db, level, f"Password reset requested: {email} (email sent: {sent})")
    return generic


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Complete a password reset",
    description="Validates the reset token and sets a new password.",
)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Set a new password using a valid reset token."""
    try:
        user_id = verify_password_reset_token(body.token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Liên kết đặt lại không hợp lệ hoặc đã hết hạn.",
        ) from exc

    result = await db.execute(select(User).where(User.UserId == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Liên kết đặt lại không hợp lệ hoặc đã hết hạn.",
        )
    user.PasswordHash = hash_password(body.new_password)
    user.UpdatedAt = datetime.now(timezone.utc)
    await db.flush()
    await log_event(db, LEVEL_INFO, f"Password reset completed: {user.Email}")
    return MessageResponse(message="Đặt lại mật khẩu thành công.")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _is_valid_session_id(value: str) -> bool:
    """Return True if *value* is a valid UUID version 4 string."""
    try:
        return UUID(value).version == 4
    except (ValueError, AttributeError, TypeError):
        return False


def _require_valid_session_id(value: str) -> None:
    """Raise HTTP 400 if *value* is not a UUID v4 (anti brute-force / garbage)."""
    if not _is_valid_session_id(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id phải là một UUID v4 hợp lệ.",
        )


def _flutter_result_page(
    message: str, ok: bool, status_code: int = status.HTTP_200_OK
) -> HTMLResponse:
    """Return a minimal self-contained HTML page shown in the app's login tab."""
    colour = "#16a34a" if ok else "#dc2626"
    symbol = "&#10003;" if ok else "&#10007;"
    html = (
        "<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>ArchiAI</title></head>"
        "<body style=\"font-family:system-ui,sans-serif;display:flex;align-items:center;"
        "justify-content:center;min-height:100vh;margin:0;background:#0b0e14;color:#e5e7eb\">"
        "<div style=\"text-align:center;padding:24px;max-width:360px\">"
        f"<div style=\"font-size:48px;margin-bottom:12px;color:{colour}\">{symbol}</div>"
        f"<p style=\"font-size:16px;line-height:1.5\">{message}</p>"
        "</div></body></html>"
    )
    return HTMLResponse(content=html, status_code=status_code)


async def _resolve_role(db: AsyncSession, role_name: str) -> Role:
    """Return the Role row for *role_name* or raise 503 if it is not seeded."""
    try:
        role_result = await db.execute(select(Role).where(Role.RoleName == role_name))
        return role_result.scalar_one()
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Role configuration missing — seed Roles table before login",
        ) from exc


async def _assert_active_or_block(db: AsyncSession, email: str, is_active: bool) -> None:
    """Block login for a deactivated account, recording the attempt.

    Raises:
        HTTPException 403: If ``is_active`` is False.
    """
    if is_active:
        return
    await log_event(db, LEVEL_WARNING, f"Login blocked - account deactivated: {email}")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tài khoản đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên.",
    )


async def _upsert_user(
    db: AsyncSession, google_user: GoogleUserInfo
) -> Tuple[str, str, bool]:
    """Find-or-create a User row for the given Google profile.

    Lookup order: by GoogleSub, then by Email (covers users created before
    the GoogleSub column was populated). The role is determined from
    ``settings.admin_emails_list``; the matching ``Role`` row supplies the FK.

    Returns:
        ``(user_id, role_name, is_active)`` — the database UUID, the resolved
        role, and whether the account is currently active.

    Raises:
        HTTPException 503: If the Roles table is missing the expected entry.
    """
    role_name = "admin" if google_user.email.lower() in settings.admin_emails_list else "user"
    role = await _resolve_role(db, role_name)

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
        await db.flush()
        # One-time signup bonus through the ledger (idempotent per user id).
        await wallet_service.grant_signup_bonus(db, user.UserId)
    else:
        user.Name = google_user.name
        user.Picture = google_user.picture or user.Picture
        user.GoogleSub = google_user.sub
        user.UpdatedAt = now

    await db.flush()
    return user.UserId, role_name, user.IsActive


async def _exchange_code_for_user_info(
    code: str, redirect_uri: str | None = None
) -> GoogleUserInfo:
    """Exchange an authorization code for a GoogleUserInfo object.

    Steps:
        1. POST the code to Google's token endpoint to get a Google access token.
        2. Use that access token to GET the user's profile from Google's userinfo endpoint.

    Args:
        code: The one-time authorization code from Google.
        redirect_uri: The redirect URI to send during the exchange — it must
            match the one used to obtain the code. Defaults to the web flow's
            ``settings.GOOGLE_REDIRECT_URI``; the flutter flow passes its own.

    Raises:
        HTTPException 400: On any failure from Google's APIs.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        google_access_token = await _fetch_google_access_token(client, code, redirect_uri)
        return await _fetch_google_user_info(client, google_access_token)


async def _fetch_google_access_token(
    client: httpx.AsyncClient, code: str, redirect_uri: str | None = None
) -> str:
    """POST to Google's token endpoint and return the access_token string."""
    response = await client.post(
        _GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
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
