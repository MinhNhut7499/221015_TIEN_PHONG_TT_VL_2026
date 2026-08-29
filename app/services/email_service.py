"""Outbound email via SMTP.

A single system "outbox" account (configured in ``.env``) sends transactional
emails — currently only password-reset links — to any user. Sending is
best-effort: if SMTP is not configured or the send fails, the error is logged
and swallowed so the calling request never breaks (and never leaks whether an
email address exists).
"""
import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


def _build_message(to_email: str, subject: str, text_body: str) -> EmailMessage:
    """Build a plain-text email from the configured outbox."""
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM or settings.SMTP_USER
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)
    return message


async def _send(message: EmailMessage, to_email: str, kind: str) -> bool:
    """Send *message* over SMTP. Best-effort: never raises.

    A missing SMTP_HOST disables sending (returns False after a warning).
    """
    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP not configured (SMTP_HOST empty) — skipping %s email to %s",
            kind, to_email,
        )
        return False
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_USE_TLS,
        )
        return True
    except (aiosmtplib.SMTPException, OSError) as exc:
        logger.warning("Failed to send %s email to %s: %s", kind, to_email, exc)
        return False


async def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Send a password-reset email. Returns True on success, False otherwise."""
    minutes = settings.PASSWORD_RESET_EXPIRE_MINUTES
    text_body = (
        "Xin chào,\n\n"
        "Bạn (hoặc ai đó) đã yêu cầu đặt lại mật khẩu cho tài khoản ArchiAI.\n"
        f"Nhấn vào liên kết dưới đây để đặt lại (hết hạn sau {minutes} phút):\n\n"
        f"{reset_link}\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này.\n\n"
        "---\n"
        "Hello,\n\n"
        "A password reset was requested for your ArchiAI account.\n"
        f"Use the link below to reset it (expires in {minutes} minutes):\n\n"
        f"{reset_link}\n\n"
        "If you did not request this, you can safely ignore this email.\n"
    )
    message = _build_message(
        to_email, "ArchiAI — Đặt lại mật khẩu / Reset your password", text_body
    )
    return await _send(message, to_email, "password-reset")


async def send_verification_email(to_email: str, verify_link: str) -> bool:
    """Send an account-verification email. Returns True on success, False otherwise."""
    hours = max(1, settings.EMAIL_VERIFY_EXPIRE_MINUTES // 60)
    text_body = (
        "Xin chào,\n\n"
        "Cảm ơn bạn đã đăng ký tài khoản ArchiAI.\n"
        f"Nhấn vào liên kết dưới đây để xác minh email và kích hoạt tài khoản "
        f"(hết hạn sau {hours} giờ):\n\n"
        f"{verify_link}\n\n"
        "Nếu bạn không đăng ký, hãy bỏ qua email này.\n\n"
        "---\n"
        "Hello,\n\n"
        "Thanks for signing up for ArchiAI.\n"
        f"Click the link below to verify your email and activate your account "
        f"(expires in {hours} hours):\n\n"
        f"{verify_link}\n\n"
        "If you did not sign up, you can safely ignore this email.\n"
    )
    message = _build_message(
        to_email, "ArchiAI — Xác minh tài khoản / Verify your account", text_body
    )
    return await _send(message, to_email, "verification")
