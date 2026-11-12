"""Store, list and remove attachments. Callers check access to the parent record first."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.storage import build_key, get_storage, validate_upload
from app.core.errors import NotFound, ValidationFailed
from app.db.tenant import TenantDescriptor
from app.modules.attachments.models import Attachment
from app.modules.identity.models import User

ALLOWED = {"pdf", "jpg", "jpeg", "png", "docx", "xlsx", "doc", "xls"}
MAX_PER_RECORD = 20


class AttachmentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    uploaded_by: str | None
    uploaded_at: datetime
    url: str


def _out(db: Session, tenant: TenantDescriptor, a: Attachment) -> AttachmentOut:
    user = db.get(User, a.uploaded_by) if a.uploaded_by else None
    url = get_storage().download_url(
        a.storage_key, filename=a.filename, content_type=a.content_type, tenant_public_id=tenant.public_id
    )
    return AttachmentOut(
        id=a.public_id,
        filename=a.filename,
        content_type=a.content_type,
        size=a.size,
        uploaded_by=user.full_name if user else None,
        uploaded_at=a.uploaded_at,
        url=url,
    )


def _rows(db: Session, entity_type: str, entity_id: int) -> list[Attachment]:
    return list(
        db.scalars(
            select(Attachment)
            .where(
                Attachment.entity_type == entity_type,
                Attachment.entity_id == entity_id,
                Attachment.is_deleted.is_(False),
            )
            .order_by(Attachment.id)
        )
    )


def list_attachments(
    db: Session, tenant: TenantDescriptor, entity_type: str, entity_id: int
) -> list[AttachmentOut]:
    return [_out(db, tenant, a) for a in _rows(db, entity_type, entity_id)]


def add_attachment(
    db: Session,
    tenant: TenantDescriptor,
    entity_type: str,
    entity_id: int,
    filename: str,
    data: bytes,
    actor_id: int,
) -> AttachmentOut:
    if len(_rows(db, entity_type, entity_id)) >= MAX_PER_RECORD:
        raise ValidationFailed(f"At most {MAX_PER_RECORD} files per record", code="TOO_MANY_FILES")
    vf = validate_upload(filename, data, ALLOWED)
    key = build_key(tenant.code, entity_type.lower(), vf.extension)
    get_storage().put(key, data, vf.content_type)
    name = filename.replace("\\", "/").rsplit("/", 1)[-1][:255] or f"file.{vf.extension}"
    a = Attachment(
        entity_type=entity_type,
        entity_id=entity_id,
        filename=name,
        storage_key=key,
        content_type=vf.content_type,
        size=vf.size,
        sha256=vf.sha256,
        uploaded_by=actor_id,
    )
    db.add(a)
    db.flush()
    return _out(db, tenant, a)


def remove_attachment(db: Session, entity_type: str, entity_id: int, public_id: str, actor_id: int) -> None:
    a = db.scalar(
        select(Attachment).where(
            Attachment.public_id == public_id,
            Attachment.entity_type == entity_type,
            Attachment.entity_id == entity_id,
            Attachment.is_deleted.is_(False),
        )
    )
    if a is None:
        raise NotFound("File not found")
    # The stored object is kept (records are evidence); the attachment disappears from the record.
    a.is_deleted, a.deleted_by = True, actor_id
