"""Password policy (docs/06-security.md §1)."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import ValidationFailed

# Small deny-list of very common passwords; extend via a file in production if required.
COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "123456789",
    "1234567890",
    "qwerty123",
    "qwertyuiop",
    "iloveyou",
    "admin123",
    "welcome123",
    "letmein123",
    "changeme",
    "parish123",
    "church123",
    "jesus123",
    "abc123456",
    "111111111",
    "000000000",
}


def password_problems(password: str, *, username: str | None = None, email: str | None = None) -> list[str]:
    settings = get_settings()
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"Must be at least {settings.password_min_length} characters")
    if len(password) > 256:
        problems.append("Must be at most 256 characters")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        problems.append("Is too common")
    for ident in (username, (email or "").split("@")[0] or None):
        if ident and len(ident) >= 3 and ident.lower() in lowered:
            problems.append("Must not contain your username or email")
            break
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 2:
        problems.append("Must mix at least two of: lowercase, uppercase, digits, symbols")
    return problems


def validate_password(
    password: str, *, username: str | None = None, email: str | None = None, field: str = "password"
) -> None:
    problems = password_problems(password, username=username, email=email)
    if problems:
        raise ValidationFailed(
            "Password does not meet the policy",
            code="WEAK_PASSWORD",
            details=[{"field": field, "message": p} for p in problems],
        )
