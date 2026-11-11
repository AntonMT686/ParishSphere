"""Object storage for documents, statements and exports.

* ``LocalStorage`` – filesystem (development/tests). Downloads use short-lived signed tokens served by
  ``GET /api/v1/files/download``.
* ``S3Storage`` – any S3-compatible service (S3, R2, a self-hosted S3 server, …). Downloads use
  presigned URLs.

Keys are always ``{tenant_code}/{category}/{yyyy}/{mm}/{ulid}{ext}``: the original filename is metadata
only, and every key is namespaced by parish so one parish can never address another's objects.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import filetype
import jwt

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.ids import new_public_id

# extension → acceptable detected MIME types (magic bytes), and the canonical content type.
ALLOWED_TYPES: dict[str, tuple[set[str], str]] = {
    "pdf": ({"application/pdf"}, "application/pdf"),
    "jpg": ({"image/jpeg"}, "image/jpeg"),
    "jpeg": ({"image/jpeg"}, "image/jpeg"),
    "png": ({"image/png"}, "image/png"),
    "docx": (
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "xlsx": (
        {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "doc": ({"application/x-ole-storage", "application/msword"}, "application/msword"),
    "xls": ({"application/x-ole-storage", "application/vnd.ms-excel"}, "application/vnd.ms-excel"),
}
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_SAFE_CATEGORY = re.compile(r"^[a-z0-9_-]{1,40}$")


@dataclass(frozen=True)
class ValidatedFile:
    extension: str
    content_type: str
    size: int
    sha256: str


def validate_upload(filename: str, data: bytes, allowed: set[str] | None = None) -> ValidatedFile:
    """Check extension allow-list, size and that the content really is that type (magic bytes)."""
    settings = get_settings()
    ext = PurePosixPath(filename.lower()).suffix.lstrip(".")
    allowed_exts = allowed or set(ALLOWED_TYPES)
    if ext not in allowed_exts or ext not in ALLOWED_TYPES:
        raise ValidationFailed(
            f"File type .{ext or '?'} is not allowed",
            code="INVALID_FILE_TYPE",
            details=[{"field": "file", "message": f"Allowed: {', '.join(sorted(allowed_exts))}"}],
        )
    size = len(data)
    if size == 0:
        raise ValidationFailed("The file is empty", code="EMPTY_FILE")
    if size > settings.max_upload_mb * 1024 * 1024:
        raise ValidationFailed(f"The file exceeds {settings.max_upload_mb} MB", code="FILE_TOO_LARGE")
    detected = (
        "application/x-ole-storage" if data[:8] == _OLE_MAGIC else (filetype.guess_mime(data[:8192]) or "")
    )
    accepted, canonical = ALLOWED_TYPES[ext]
    if detected not in accepted:
        raise ValidationFailed(
            "The file content does not match its extension",
            code="INVALID_FILE_TYPE",
            details=[
                {"field": "file", "message": f".{ext} expected, content looks like {detected or 'unknown'}"}
            ],
        )
    return ValidatedFile(ext, canonical, size, hashlib.sha256(data).hexdigest())


def build_key(tenant_code: str, category: str, extension: str, when: datetime | None = None) -> str:
    if not _SAFE_CATEGORY.match(category):
        raise ValueError(f"Invalid storage category {category!r}")
    when = when or datetime.now(UTC)
    ext = f".{extension.lstrip('.')}" if extension else ""
    return f"{tenant_code.lower()}/{category}/{when:%Y}/{when:%m}/{new_public_id()}{ext}"


def _check_key(key: str) -> None:
    if ".." in key or key.startswith("/") or "\\" in key:
        raise ValueError(f"Unsafe storage key {key!r}")


def content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:150] or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def download_url(
        self, key: str, *, filename: str, content_type: str, tenant_public_id: str, ttl: int | None = None
    ) -> str: ...


class LocalStorage(Storage):
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        _check_key(key)
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Key escapes storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def download_url(
        self, key: str, *, filename: str, content_type: str, tenant_public_id: str, ttl: int | None = None
    ) -> str:
        token = sign_download(key, filename, content_type, tenant_public_id, ttl)
        return f"/api/v1/files/download?token={token}"


class S3Storage(Storage):
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        s = get_settings()
        self.bucket = s.s3_bucket

        def client(endpoint: str | None):  # type: ignore[no-untyped-def]
            return boto3.client(
                "s3",
                endpoint_url=endpoint,
                region_name=s.s3_region,
                aws_access_key_id=s.s3_access_key.get_secret_value() if s.s3_access_key else None,
                aws_secret_access_key=s.s3_secret_key.get_secret_value() if s.s3_secret_key else None,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )

        self.client = client(s.s3_endpoint_url)
        # Presigned URLs embed the host in the signature, so sign with the browser-facing endpoint.
        self.presign_client = client(s.s3_public_endpoint_url) if s.s3_public_endpoint_url else self.client
        if s.s3_auto_create_bucket:
            self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            kwargs: dict[str, Any] = {"Bucket": self.bucket}
            region = get_settings().s3_region
            if region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            self.client.create_bucket(**kwargs)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _check_key(key)
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256"
        )

    def get(self, key: str) -> bytes:
        _check_key(key)
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()  # type: ignore[no-any-return]

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def download_url(
        self, key: str, *, filename: str, content_type: str, tenant_public_id: str, ttl: int | None = None
    ) -> str:
        return self.presign_client.generate_presigned_url(  # type: ignore[no-any-return]
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": content_disposition(filename),
            },
            ExpiresIn=ttl or get_settings().download_url_ttl_seconds,
        )


# ----------------------------------------------------------------------------- signed local downloads
def sign_download(
    key: str, filename: str, content_type: str, tenant_public_id: str, ttl: int | None = None
) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "typ": "download",
        "key": key,
        "fn": filename,
        "ct": content_type,
        "tid": tenant_public_id,
        "iat": now,
        "exp": now + timedelta(seconds=ttl or s.download_url_ttl_seconds),
    }
    return jwt.encode(payload, s.secret_key.get_secret_value(), algorithm=s.jwt_algorithm)


def verify_download(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        claims = jwt.decode(token, s.secret_key.get_secret_value(), algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        from app.core.errors import NotFound

        raise NotFound("This download link is invalid or has expired", code="DOWNLOAD_LINK_INVALID") from exc
    if claims.get("typ") != "download":
        from app.core.errors import NotFound

        raise NotFound("This download link is invalid or has expired", code="DOWNLOAD_LINK_INVALID")
    return claims


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.storage_backend == "s3" else LocalStorage(s.storage_local_dir)
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None
