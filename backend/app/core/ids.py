"""Opaque public identifiers (ULID) used in URLs and API payloads."""

from __future__ import annotations

import re

from ulid import ULID

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def new_public_id() -> str:
    return str(ULID())


def is_public_id(value: str) -> bool:
    return bool(_ULID_RE.match(value))
