"""Notices (``/api/v1/notices``) and the public notice board (``/api/v1/public/notices``)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Select, false, or_, select
from sqlalchemy.orm import Session

from app.common.audit import changes, record_audit
from app.common.exports import render_pdf
from app.common.pagination import Page, PageQuery, apply_sort, paginate
from app.common.storage import content_disposition
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.modules.activities.service import parish_now
from app.modules.attachments.service import AttachmentOut, add_attachment, list_attachments, remove_attachment
from app.modules.identity.deps import Auth
from app.modules.notices import service as svc
from app.modules.notices.models import CATEGORIES, Notice
from app.modules.org_units.models import OrgUnit
from app.modules.rbac.service import PermissionScope
from app.modules.workflow.models import WorkflowInstance
from app.tenancy.deps import CurrentTenant, TenantSession

router = APIRouter(prefix="/notices", tags=["notices"])
public_router = APIRouter(prefix="/public/notices", tags=["public"])
MODULE = "notices"
Category = Literal["WEEKLY", "ANNOUNCEMENT", "EVENT", "EMERGENCY", "DIOCESE", "NEWS"]


# ============================================================================ schemas
class NoticeIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    title_local: str | None = Field(default=None, max_length=200)
    category: Category = "ANNOUNCEMENT"
    body: str = Field(min_length=3, max_length=20000)
    body_local: str | None = Field(default=None, max_length=20000)
    org_unit_id: str | None = Field(
        default=None, max_length=26, description="Preparing organisation; omit for the parish office"
    )
    audience_all: bool = True
    audience_org_units: list[str] = Field(default_factory=list, max_length=50)
    is_important: bool = False
    is_public: bool = False
    publish_at: datetime | None = Field(
        default=None, description="Parish local time; default: as soon as approved"
    )
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _check(self) -> NoticeIn:
        for f in ("publish_at", "expires_at"):
            v = getattr(self, f)
            if v is not None:
                setattr(self, f, v.replace(tzinfo=None, second=0, microsecond=0))
        if self.publish_at and self.expires_at and self.expires_at <= self.publish_at:
            raise ValueError("The notice must expire after it is published")
        if not self.audience_all and not self.audience_org_units:
            raise ValueError("Choose the organisations this notice is for")
        return self


class NoticeUnitRef(BaseModel):
    id: str
    name: str


class NoticeActions(BaseModel):
    edit: bool = False
    submit: bool = False
    delete: bool = False
    publish: bool = False
    archive: bool = False


class NoticeListOut(BaseModel):
    id: str
    code: str
    category: str
    title: str
    title_local: str | None
    excerpt: str
    excerpt_local: str | None
    org_unit: NoticeUnitRef | None
    audience_all: bool
    audience: list[NoticeUnitRef]
    is_important: bool
    is_public: bool
    publish_at: datetime
    expires_at: datetime | None
    status: str
    state: str
    attachments: int


class NoticeOut(NoticeListOut):
    body: str
    body_local: str | None
    created_by: str | None
    created_at: datetime
    approved_at: datetime | None
    approval_id: str | None
    can: NoticeActions


class NoticeSubmitIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


# ============================================================================ helpers
def _excerpt(text: str | None, n: int = 220) -> str | None:
    if text is None:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[: n - 1].rstrip() + "…"


def _units(db: Session, ids: list[int]) -> list[NoticeUnitRef]:
    if not ids:
        return []
    rows = db.scalars(select(OrgUnit).where(OrgUnit.id.in_(ids))).all()
    return [NoticeUnitRef(id=u.public_id, name=u.name) for u in sorted(rows, key=lambda u: u.name)]


def _attachment_count(db: Session, n: Notice) -> int:
    from sqlalchemy import func

    from app.modules.attachments.models import Attachment

    return (
        db.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(
                Attachment.entity_type == "NOTICE",
                Attachment.entity_id == n.id,
                Attachment.is_deleted.is_(False),
            )
        )
        or 0
    )


def _list_out(db: Session, n: Notice, now: datetime) -> NoticeListOut:
    unit = db.get(OrgUnit, n.org_unit_id) if n.org_unit_id else None
    return NoticeListOut(
        id=n.public_id,
        code=n.code,
        category=n.category,
        title=n.title,
        title_local=n.title_local,
        excerpt=_excerpt(n.body) or "",
        excerpt_local=_excerpt(n.body_local),
        org_unit=NoticeUnitRef(id=unit.public_id, name=unit.name) if unit else None,
        audience_all=bool(n.audience.get("all", True)),
        audience=_units(db, n.audience.get("org_units") or []),
        is_important=n.is_important,
        is_public=n.is_public,
        publish_at=n.publish_at,
        expires_at=n.expires_at,
        status=n.status,
        state=svc.state(n, now),
        attachments=_attachment_count(db, n),
    )


def _scope(auth: Auth, code: str) -> PermissionScope:
    return auth.permissions.scope(code)


def _is_manager(auth: Auth, n: Notice) -> bool:
    return (
        n.created_by == auth.user.id
        or any(
            _scope(auth, c).allows(n.org_unit_id)
            for c in ("notice.update", "notice.publish", "notice.delete")
        )
        or auth.user.id in _involved(auth, n)
    )


def _involved(auth: Auth, n: Notice) -> set[int]:
    inst = auth.db.scalar(
        select(WorkflowInstance)
        .where(WorkflowInstance.entity_type == "NOTICE", WorkflowInstance.entity_id == n.public_id)
        .order_by(WorkflowInstance.id.desc())
        .limit(1)
    )
    from app.modules.workflow.service import involved_user_ids

    return involved_user_ids(inst) if inst else set()


def _out(db: Session, auth: Auth, n: Notice) -> NoticeOut:
    now = parish_now(db)
    u = _scope(auth, "notice.update").allows(n.org_unit_id)
    pub = _scope(auth, "notice.publish").allows(n.org_unit_id)
    from app.modules.identity.models import User

    creator = db.get(User, n.created_by) if n.created_by else None
    approval = db.scalar(
        select(WorkflowInstance.public_id)
        .where(WorkflowInstance.entity_type == "NOTICE", WorkflowInstance.entity_id == n.public_id)
        .order_by(WorkflowInstance.id.desc())
        .limit(1)
    )
    st = svc.state(n, now)
    return NoticeOut(
        **_list_out(db, n, now).model_dump(),
        body=n.body,
        body_local=n.body_local,
        created_by=creator.full_name if creator else None,
        created_at=n.created_at,
        approved_at=n.approved_at,
        approval_id=approval,
        can=NoticeActions(
            edit=u and n.status in svc.EDITABLE,
            submit=_scope(auth, "notice.submit").allows(n.org_unit_id) and n.status in svc.EDITABLE,
            delete=_scope(auth, "notice.delete").allows(n.org_unit_id) and n.status == "DRAFT",
            publish=pub and st == "SCHEDULED",
            archive=pub and st in ("LIVE", "SCHEDULED", "EXPIRED"),
        ),
    )


def _fields(db: Session, body: NoticeIn) -> dict[str, Any]:
    unit_ids: list[int] = []
    for pid in body.audience_org_units:
        uid = db.scalar(select(OrgUnit.id).where(OrgUnit.public_id == pid, OrgUnit.is_deleted.is_(False)))
        if uid is None:
            raise ValidationFailed(
                details=[{"field": "audience_org_units", "message": "Unknown organisation"}]
            )
        unit_ids.append(uid)
    org = None
    if body.org_unit_id:
        org = db.scalar(select(OrgUnit.id).where(OrgUnit.public_id == body.org_unit_id))
        if org is None:
            raise NotFound("Organisation not found")
    return {
        "title": body.title.strip(),
        "title_local": (body.title_local or "").strip() or None,
        "category": body.category,
        "body": body.body.strip(),
        "body_local": (body.body_local or "").strip() or None,
        "org_unit_id": org,
        "audience": {"all": True}
        if body.audience_all
        else {"all": False, "org_units": sorted(set(unit_ids))},
        "is_important": body.is_important or body.category == "EMERGENCY",
        "is_public": body.is_public and body.audience_all,
        "publish_at": body.publish_at or parish_now(db),
        "expires_at": body.expires_at,
    }


def _get_visible(db: Session, auth: Auth, public_id: str) -> Notice:
    n = svc.get_notice(db, public_id)
    if _is_manager(auth, n):
        return n
    now = parish_now(db)
    if (
        _scope(auth, "notice.view").granted
        and svc.state(n, now) == "LIVE"
        and svc.audience_ok(n, svc.user_unit_ids(db, auth.user.id))
    ):
        return n
    raise NotFound("Notice not found")


def _audit(db: Session, auth: Auth, request: Request | None, action: str, n: Notice, **kw: Any) -> None:
    record_audit(
        db,
        action=action,
        module=MODULE,
        user_id=auth.user.id,
        request=request,
        entity_type="notice",
        entity_id=n.code,
        **kw,
    )


def _board_query(db: Session, auth: Auth, now: datetime, category: str | None, q: str | None) -> Select[Any]:
    stmt = select(Notice).where(svc.live_clause(now))
    if category:
        stmt = stmt.where(Notice.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Notice.title.ilike(like), Notice.body.ilike(like), Notice.title_local.ilike(like))
        )
    return stmt


def _visible_board(db: Session, auth: Auth, rows: list[Notice]) -> list[Notice]:
    units = svc.user_unit_ids(db, auth.user.id)
    return [n for n in rows if svc.audience_ok(n, units) or _is_manager(auth, n)]


# ============================================================================ reader endpoints
@router.get("/board", response_model=Page[NoticeListOut])
def board(
    auth: Auth,
    db: TenantSession,
    params: PageQuery,
    category: Annotated[str | None, Query(max_length=15)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[NoticeListOut]:
    """Live notices for the current user (important first, newest first)."""
    if not _scope(auth, "notice.view").granted:
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.view"}])
    now = parish_now(db)
    rows = _visible_board(
        db,
        auth,
        list(
            db.scalars(
                _board_query(db, auth, now, category, q).order_by(
                    Notice.is_important.desc(), Notice.publish_at.desc(), Notice.id.desc()
                )
            )
        ),
    )
    start = (params.page - 1) * params.size
    page = rows[start : start + params.size]
    return Page[NoticeListOut](
        items=[_list_out(db, n, now) for n in page],
        page=params.page,
        size=params.size,
        total=len(rows),
        pages=(len(rows) + params.size - 1) // params.size if rows else 0,
    )


@router.get("/bulletin.pdf")
def bulletin(
    auth: Auth, db: TenantSession, category: Annotated[str | None, Query(max_length=15)] = None
) -> Response:
    """Printable bulletin of the live notices the user can see (e.g. for the church notice board)."""
    if not _scope(auth, "notice.view").granted:
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.view"}])
    now = parish_now(db)
    rows = _visible_board(
        db,
        auth,
        list(
            db.scalars(
                _board_query(db, auth, now, category, None).order_by(
                    Notice.is_important.desc(), Notice.publish_at.desc()
                )
            )
        ),
    )
    pdf = render_pdf(
        "notices.html",
        {
            "title": "Parish Notices",
            "parish_name": auth.tenant.name,
            "notices": rows,
            "subtitle": now.strftime("%d %B %Y"),
            "generated_by": auth.user.full_name,
        },
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(f"notices-{now:%Y-%m-%d}.pdf"),
            "Cache-Control": "no-store",
        },
    )


# ============================================================================ management
@router.get("", response_model=Page[NoticeListOut])
def manage_list(
    auth: Auth,
    db: TenantSession,
    params: PageQuery,
    state: Annotated[
        str | None,
        Query(
            max_length=60,
            description="DRAFT, IN_REVIEW, REWORK, SCHEDULED, LIVE, EXPIRED, ARCHIVED, REJECTED",
        ),
    ] = None,
    category: Annotated[str | None, Query(max_length=15)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[NoticeListOut]:
    """Every notice the user prepares, reviews or publishes."""
    upd, pub, cre = (
        _scope(auth, "notice.update"),
        _scope(auth, "notice.publish"),
        _scope(auth, "notice.create"),
    )
    if not (upd.granted or pub.granted or cre.granted):
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.create"}])
    stmt = select(Notice).where(
        Notice.is_deleted.is_(False),
        or_(
            upd.filter(Notice.org_unit_id), pub.filter(Notice.org_unit_id), Notice.created_by == auth.user.id
        ),
    )
    if category:
        stmt = stmt.where(Notice.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Notice.title.ilike(like), Notice.code.ilike(like)))
    now = parish_now(db)
    if state:
        conds = []
        for s in state.split(","):
            if s in ("DRAFT", "IN_REVIEW", "REWORK", "ARCHIVED", "REJECTED"):
                conds.append(Notice.status == s)
            elif s == "SCHEDULED":
                conds.append((Notice.status.in_(svc.LIVE_STATUSES)) & (Notice.publish_at > now))
            elif s == "LIVE":
                conds.append(svc.live_clause(now))
            elif s == "EXPIRED":
                conds.append(
                    Notice.status.in_(svc.LIVE_STATUSES)
                    & Notice.expires_at.is_not(None)
                    & (Notice.expires_at <= now)
                )
        stmt = stmt.where(or_(*conds) if conds else false())
    stmt = apply_sort(
        stmt,
        params.sort,
        {"publish_at": Notice.publish_at, "created_at": Notice.created_at, "title": Notice.title},
        [Notice.updated_at.desc(), Notice.id.desc()],
    )
    return paginate(db, stmt, params, lambda n: _list_out(db, n, now))


@router.post("", response_model=NoticeOut, status_code=status.HTTP_201_CREATED)
def create_notice(body: NoticeIn, request: Request, auth: Auth, db: TenantSession) -> NoticeOut:
    data = _fields(db, body)
    if not _scope(auth, "notice.create").allows(data["org_unit_id"]):
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.create"}])
    n = svc.new_notice(db, data, auth.user.id)
    _audit(db, auth, request, "CREATE", n, new={"title": n.title, "category": n.category})
    return _out(db, auth, n)


@router.get("/{notice_id}", response_model=NoticeOut)
def get_notice(notice_id: str, auth: Auth, db: TenantSession) -> NoticeOut:
    return _out(db, auth, _get_visible(db, auth, notice_id))


@router.put("/{notice_id}", response_model=NoticeOut)
def update_notice(
    notice_id: str, body: NoticeIn, request: Request, auth: Auth, db: TenantSession
) -> NoticeOut:
    n = _get_visible(db, auth, notice_id)
    data = _fields(db, body)
    scope = _scope(auth, "notice.update")
    if not (scope.allows(n.org_unit_id) and scope.allows(data["org_unit_id"])):
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.update"}])
    if n.status not in svc.EDITABLE:
        raise Conflict("Only drafts and notices returned for rework can be changed", code="NOT_EDITABLE")
    for k, v in data.items():
        setattr(n, k, v)
    old, new = changes(n, exclude={"audience"})
    n.updated_by = auth.user.id
    _audit(db, auth, request, "UPDATE", n, old=old, new=new)
    return _out(db, auth, n)


@router.delete("/{notice_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_notice(notice_id: str, request: Request, auth: Auth, db: TenantSession) -> None:
    n = _get_visible(db, auth, notice_id)
    if not _scope(auth, "notice.delete").allows(n.org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.delete"}])
    if n.status != "DRAFT":
        raise Conflict("Only drafts can be deleted; archive it instead", code="NOT_EDITABLE")
    n.soft_delete(auth.user.id)
    _audit(db, auth, request, "DELETE", n)


@router.post("/{notice_id}/submit", response_model=NoticeOut)
def submit_notice(notice_id: str, body: NoticeSubmitIn, auth: Auth, db: TenantSession) -> NoticeOut:
    n = _get_visible(db, auth, notice_id)
    if not _scope(auth, "notice.submit").allows(n.org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.submit"}])
    svc.submit(db, auth.tenant, n, auth.user.id, body.comment)
    return _out(db, auth, n)


@router.post("/{notice_id}/publish", response_model=NoticeOut)
def publish_now(notice_id: str, request: Request, auth: Auth, db: TenantSession) -> NoticeOut:
    """Publish an approved, scheduled notice immediately."""
    n = _get_visible(db, auth, notice_id)
    if not _scope(auth, "notice.publish").allows(n.org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.publish"}])
    svc.publish(db, auth.tenant, n)
    _audit(db, auth, request, "PUBLISH", n)
    return _out(db, auth, n)


@router.post("/{notice_id}/archive", response_model=NoticeOut)
def archive_notice(notice_id: str, request: Request, auth: Auth, db: TenantSession) -> NoticeOut:
    n = _get_visible(db, auth, notice_id)
    if not _scope(auth, "notice.publish").allows(n.org_unit_id):
        raise PermissionDenied(details=[{"field": "permission", "message": "notice.publish"}])
    svc.archive(n, auth.user.id)
    _audit(db, auth, request, "ARCHIVE", n)
    return _out(db, auth, n)


@router.get("/{notice_id}/pdf")
def notice_pdf(notice_id: str, auth: Auth, db: TenantSession) -> Response:
    n = _get_visible(db, auth, notice_id)
    pdf = render_pdf(
        "notices.html",
        {
            "title": n.title,
            "parish_name": auth.tenant.name,
            "notices": [n],
            "single": True,
            "generated_by": auth.user.full_name,
        },
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(f"notice-{n.code}.pdf"),
            "Cache-Control": "no-store",
        },
    )


@router.get("/{notice_id}/attachments", response_model=list[AttachmentOut])
def notice_files(notice_id: str, auth: Auth, db: TenantSession) -> list[AttachmentOut]:
    n = _get_visible(db, auth, notice_id)
    return list_attachments(db, auth.tenant, "NOTICE", n.id)


@router.post("/{notice_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def add_notice_file(
    notice_id: str, auth: Auth, db: TenantSession, file: Annotated[UploadFile, File()]
) -> AttachmentOut:
    n = _get_visible(db, auth, notice_id)
    if not (_scope(auth, "notice.update").allows(n.org_unit_id) and n.status in svc.EDITABLE):
        raise PermissionDenied("Files can be added while the notice is a draft or returned for rework")
    return add_attachment(
        db, auth.tenant, "NOTICE", n.id, file.filename or "file", await file.read(), auth.user.id
    )


@router.delete(
    "/{notice_id}/attachments/{file_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def remove_notice_file(notice_id: str, file_id: str, auth: Auth, db: TenantSession) -> None:
    n = _get_visible(db, auth, notice_id)
    if not (_scope(auth, "notice.update").allows(n.org_unit_id) and n.status in svc.EDITABLE):
        raise PermissionDenied("Files can be removed while the notice is a draft or returned for rework")
    remove_attachment(db, "NOTICE", n.id, file_id, auth.user.id)


# ============================================================================ public portal
class PublicNotice(BaseModel):
    id: str
    category: str
    title: str
    title_local: str | None
    body: str
    body_local: str | None
    is_important: bool
    publish_at: datetime
    expires_at: datetime | None
    attachments: list[AttachmentOut]


@public_router.get("", response_model=list[PublicNotice])
def public_notices(
    tenant: CurrentTenant, db: TenantSession, category: Annotated[str | None, Query(max_length=15)] = None
) -> list[PublicNotice]:
    """Live notices marked for the public / member portal (no sign-in)."""
    now = parish_now(db)
    stmt = select(Notice).where(svc.live_clause(now), Notice.is_public.is_(True))
    if category:
        if category not in CATEGORIES:
            raise ValidationFailed(details=[{"field": "category", "message": "Unknown category"}])
        stmt = stmt.where(Notice.category == category)
    rows = db.scalars(stmt.order_by(Notice.is_important.desc(), Notice.publish_at.desc()).limit(50)).all()
    return [
        PublicNotice(
            id=n.public_id,
            category=n.category,
            title=n.title,
            title_local=n.title_local,
            body=n.body,
            body_local=n.body_local,
            is_important=n.is_important,
            publish_at=n.publish_at,
            expires_at=n.expires_at,
            attachments=list_attachments(db, tenant, "NOTICE", n.id),
        )
        for n in rows
    ]
