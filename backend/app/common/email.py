"""Minimal email sender. SMTP when ``PS_SMTP_HOST`` is set (MailHog in development), otherwise logged.

Template-based multi-channel notifications (T5) build on top of :func:`send_email`.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import structlog

from app.core.config import get_settings

log = structlog.get_logger(__name__)

# Tests inspect this outbox when no SMTP host is configured.
OUTBOX: list[EmailMessage] = []


def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if not settings.smtp_host:
        OUTBOX.append(msg)
        log.info("email_not_sent_no_smtp", to=to, subject=subject)
        return
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException):
        # Never fail the user's request (e.g. password reset) because mail is down; it is logged.
        log.exception("email_send_failed", to=to, subject=subject)
