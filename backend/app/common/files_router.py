"""Signed download endpoint for the local storage backend (S3 uses presigned URLs instead)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.common.storage import LocalStorage, content_disposition, get_storage, verify_download
from app.core.errors import NotFound
from app.tenancy.deps import CurrentTenant

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/download")
def download(tenant: CurrentTenant, token: Annotated[str, Query(min_length=20, max_length=4096)]) -> Response:
    """Serve a file for a short-lived token issued after an authorization check (no bearer needed)."""
    claims = verify_download(token)
    key: str = claims["key"]
    # The token is bound to the parish it was issued for and may only address that parish's objects.
    if claims.get("tid") != tenant.public_id or not key.startswith(f"{tenant.code.lower()}/"):
        raise NotFound("This download link is invalid or has expired", code="DOWNLOAD_LINK_INVALID")
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not storage.exists(key):
        raise NotFound()
    return Response(
        content=storage.get(key),
        media_type=claims["ct"],
        headers={
            "Content-Disposition": content_disposition(claims["fn"]),
            "Cache-Control": "private, no-store",
        },
    )
