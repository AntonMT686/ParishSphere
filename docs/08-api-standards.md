# 08 — API Standards

## Base

- Base path `/api/v1`; JSON (UTF-8); OpenAPI at `/api/docs` (disabled in production unless `PS_EXPOSE_DOCS=true`).
- Tenant resolved from host subdomain or `X-Parish-Code`; platform APIs under `/api/v1/platform`.
- Auth: `Authorization: Bearer <access>`.

## Resources & methods

| Operation | Method & path | Success |
|---|---|---|
| List | `GET /families?page=1&size=25&sort=-registered_on&status=ACTIVE&q=john` | 200 page |
| Get | `GET /families/{public_id}` | 200 |
| Create | `POST /families` | 201 + body |
| Update (partial) | `PATCH /families/{public_id}` | 200 |
| Soft delete / archive | `DELETE /families/{public_id}` | 204 |
| Commands | `POST /families/{id}/transfer`, `POST /activities/{id}/submit`, `POST /workflow/tasks/{id}/approve` | 200 |
| Export | `GET /families/export?format=xlsx&…filters` | file / 202 job for large |

- IDs in paths are ULID `public_id`s. Response objects expose `id` = public_id.
- Field names snake_case. Dates ISO-8601 (`YYYY-MM-DD`), datetimes UTC with `Z`. Money as string decimal `"1250.00"`.

## Pagination envelope

```json
{ "items": [ … ], "page": 1, "size": 25, "total": 1240, "pages": 50 }
```
`size` max 100. Sorting via `sort=field,-other` against a per-endpoint allow-list.

## Errors

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid input",
             "details": [{"field": "phone", "message": "Invalid phone number"}],
             "trace_id": "01JC…" } }
```

| HTTP | code examples |
|---|---|
| 400 | `BAD_REQUEST` |
| 401 | `NOT_AUTHENTICATED`, `TOKEN_EXPIRED`, `SESSION_EXPIRED`, `INVALID_CREDENTIALS` |
| 403 | `PERMISSION_DENIED`, `TENANT_MISMATCH`, `TENANT_SUSPENDED`, `ACCOUNT_LOCKED` |
| 404 | `NOT_FOUND`, `TENANT_NOT_FOUND` |
| 409 | `CONFLICT`, `DUPLICATE_SUSPECTED`, `INVALID_STATE` |
| 422 | `VALIDATION_ERROR`, `NO_WORKFLOW_CONFIGURED` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_ERROR` |

The frontend maps `code` to translated messages.

## Concurrency

Updatable records include `version` (optimistic lock) where conflicting edits are likely (families, transactions); a stale `version` returns 409 `CONFLICT`.

## Idempotency

`POST` commands that create money records accept `Idempotency-Key` header (phase 2: donations/webhooks mandatory).

## Versioning

Breaking changes → `/api/v2`; additive changes are non-breaking. Deprecated endpoints announced via `Deprecation` header.
