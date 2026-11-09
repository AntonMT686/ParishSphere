# 12 — Common Platform Services (developer guide)

Shared services every module uses (T5). All live in `backend/app/common/` or `backend/app/modules/notifications/`.

## Business codes — `app/common/sequences.py`

```python
code = next_code(db, "FAMILY")                    # FAM000123
code = next_code(db, "TRANSACTION", txn.txn_date) # TXN-2026-000045 (restarts every year)
preview = peek_code(db, "FAMILY")                 # for form previews, not reserved
```

Sequences (`FAMILY`, `MEMBER`, `ACTIVITY`, `MEETING`, `ACTION_ITEM`, `TRANSACTION`, `NOTICE`) are seeded per parish with a prefix, padding and format (`{prefix}{number}` or `{prefix}-{year}-{number}`). The base row is locked `FOR UPDATE`, so concurrent requests never get the same code. Call it inside the transaction that inserts the record.

## Audit — `app/common/audit.py`

```python
old, new = changes(family)        # pending column changes, before flush
record_audit(db, action="UPDATE", module="families", user_id=auth.user.id, request=request,
             entity_type="family", entity_id=family.public_id, old=old, new=new)
```

Write audit rows in the same transaction as the change. Keys containing password/token/secret/pin are masked. Viewer: `GET /api/v1/audit-logs` (filters `user`, `action`, `module`, `entity_type`, `entity_id`, `date_from`, `date_to`, `q`; `audit.view`), and `GET /api/v1/audit-logs/export?format=xlsx|csv|pdf` (`audit.export`; the export itself is audited).

## File storage — `app/common/storage.py`

```python
info = validate_upload(upload.filename, data)         # extension allow-list + magic bytes + size
key = build_key(tenant.code, "documents", info.extension)   # stmarys/documents/2026/11/<ulid>.pdf
get_storage().put(key, data, info.content_type)
url = get_storage().download_url(key, filename=original, content_type=info.content_type,
                                 tenant_public_id=tenant.public_id)     # 5-minute link
```

- Backends: `PS_STORAGE_BACKEND=local` (files under `PS_STORAGE_LOCAL_DIR`, served via signed `GET /api/v1/files/download?token=…`) or `s3` (MinIO/S3 presigned URLs, SSE enabled; `PS_S3_PUBLIC_ENDPOINT_URL` signs links with the browser-facing host).
- Allowed: pdf, doc, docx, xls, xlsx, jpg, jpeg, png (max `PS_MAX_UPLOAD_MB`, default 25). Content must match the extension.
- Keys are prefixed with the parish code. Local download tokens are bound to the parish and refused on any other parish host. Issue a download URL only after the record-level permission check, and audit it.

## Exports — `app/common/exports.py`

```python
return export_table(rows, [Column("code", "Family ID"), Column("members", "Members", numeric=True)],
                    format, title="Family register", filename="family-register",
                    parish_name=auth.tenant.name, generated_by=auth.user.full_name)
```

- CSV is UTF-8 with a BOM, so Excel shows Tamil correctly. XLSX has a bold frozen header, autofilter and number formats. PDF is generated with WeasyPrint from `app/templates/pdf/table.html`: Tamil-capable fonts, page numbers, landscape when there are more than 6 columns.
- Spreadsheet cells starting with `= + - @` are stored as text, which prevents formula injection.
- Synchronous exports are capped at `PS_MAX_EXPORT_ROWS` (10 000). Larger ones belong in a background job.
- `render_pdf("template.html", context)` renders custom documents such as statements and receipts from `app/templates/pdf/`.

## Notifications — `app/modules/notifications/`

```python
emit(db, auth.tenant, "approval.pending", recipients,          # users or user ids
     {"entity_label": "Activity", "title": a.title, "stage": "Parish Priest", "submitted_by": name},
     link=f"/activities/{a.public_id}", entity_type="activity", entity_id=a.public_id,
     exclude_user_id=auth.user.id)
recipients = users_with_permission(db, "activity.approve", org_unit_id)   # app/modules/rbac/service.py
```

- Events and default English/Tamil templates are defined in `catalog.py`. Parishes can override any template per channel and language (`PUT/DELETE /api/v1/notifications/templates/{event}/{channel}/{lang}`, `settings.update`). Templates use Jinja2 in a sandbox.
- Channels: `IN_APP` (always available) and `EMAIL`. Each event has default channels. Users can change them via `GET/PUT /api/v1/notifications/preferences`. SMS and WhatsApp come with a provider integration in phase 2.
- **Transactional:** in-app rows and `outbound_messages` are written in the caller's transaction. Email is delivered only **after commit**, by the Celery task `send_outbound` (retried with exponential backoff, up to 5 times) when Redis is configured, otherwise in-process. A rollback sends nothing. Delivery is idempotent.
- Inbox: `GET /api/v1/notifications?unread_only=`, `GET /unread-count`, `POST /{id}/read`, `POST /read-all`. Broadcast: `POST /api/v1/notifications/broadcast` (`settings.update`) sends a general message to all users or to the given roles.
