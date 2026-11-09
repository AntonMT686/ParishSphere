# 06 — Security Architecture

## 1. Authentication

| Aspect | Design |
|---|---|
| Password hashing | Argon2id (`argon2-cffi` defaults: t=3, m=64 MiB, p=4); rehash on login when parameters change |
| Password policy | ≥ 10 chars, not equal to username/email, checked against common list |
| Login | `POST /api/v1/auth/login {username, password}` on tenant host (or with `X-Parish-Code`) |
| Access token | JWT HS256 (RS256 optional), 15 min, claims: `sub` (user public_id), `tid` (tenant), `sid` (session), `typ`, `iat`, `exp`, `jti`; held **in memory** on the client |
| Refresh token | 256-bit random, stored **hashed** (SHA-256) in `refresh_tokens`, sent as `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` cookie; **rotated** on every use |
| Reuse detection | Presenting an already-used refresh token revokes the whole session (token theft signal) and is audited |
| CSRF | Refresh/logout endpoints (cookie-authenticated) require `X-CSRF-Token` matching a non-HttpOnly `ps_csrf` cookie (double submit). Other APIs use bearer tokens (not CSRF-prone) |
| Lockout | 5 failed attempts per username → 15 min lock; per-IP throttling via rate limiter; all failures audited |
| Password reset | Single-use token (hashed), 30 min expiry, generic response (no user enumeration), all sessions revoked on reset |
| Platform users | Separate table and login (`/api/v1/platform/auth/*`), `typ=platform` tokens; cannot access tenant routes |
| Family portal (phase 2) | Family code + password/PIN (OTP pluggable), `typ=family` token restricted to portal routes |

## 2. Session & idle timeout (30 minutes)

```mermaid
sequenceDiagram
  participant UI
  participant API
  UI->>API: any request (Bearer access)
  API->>API: load session(sid): revoked? last_activity_at < now-30m → 401 SESSION_EXPIRED
  API->>API: update last_activity_at (throttled to once/min)
  Note over UI: client idle timer (mouse/keyboard/touch)
  UI->>UI: at 28 min idle → modal "Session expires in 2:00 — Continue?"
  UI->>API: Continue → POST /auth/refresh (rotates, touches session)
  UI->>API: no response by 30 min → POST /auth/logout; clear memory/state; redirect /login?reason=timeout
```

- Server is the source of truth: even if the client is closed, refresh after 30 min idle fails.
- Absolute session lifetime: 12 h (configurable).
- Logout revokes the session and its refresh tokens; "logout all devices" revokes all user sessions; admins can revoke any user's sessions.

## 3. Authorization (RBAC + scope)

- Permission codes `module.action`; roles → permissions; users → roles **with scope** (`org_unit_id` or parish-wide).
- FastAPI dependency `require_perm("activity.create")` loads the user's effective permissions (cached per request) and returns a `PermissionScope` (`parish_wide: bool`, `org_unit_ids: set`).
- Repositories apply the scope filter: a Society Secretary listing activities only sees their society's.
- Record-level check for single-record endpoints (`assert_can_access(record.org_unit_id)`), returning **404** (not 403) for out-of-scope records to avoid existence disclosure.
- Sensitive fields gated by separate permissions (`member.view_sensitive`, `sacrament.view`, `finance.view`); response schemas drop fields the caller cannot see.
- Frontend checks are UX only.

## 4. Transport & URL security

- Production: TLS 1.2+ (Nginx), HSTS (1 year, includeSubDomains), HTTP → HTTPS 301, secure cookies only.
- Development: HTTP on localhost allowed (`PS_ENV=development`, `Secure` cookie flag off).
- URLs contain only ULIDs or non-sensitive codes; no names, phone numbers, or amounts in paths/queries for sensitive lookups (use POST search bodies where necessary).

## 5. Input, output & file security

| Threat | Control |
|---|---|
| SQL injection | ORM / bound parameters only; sort fields whitelisted |
| XSS | React escaping; rich text (notices) sanitized server-side (bleach allow-list); CSP `default-src 'self'` |
| Mass assignment | Explicit Pydantic input schemas per operation |
| File upload | Extension allow-list, magic-byte MIME check, size limit (25 MB default), random storage key, no execution, `Content-Disposition: attachment`, optional ClamAV scan hook |
| Rate limiting | Nginx `limit_req` on `/auth/*`; app-level limiter (Redis) on login/reset |
| Clickjacking | `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'` |
| Headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` |
| Errors | Centralized handler; no stack traces to clients; `trace_id` for support |

## 6. Data protection

- Tenant isolation: database per parish + per-tenant DB user + token tenant binding (see 03).
- Secrets via environment / secret manager; never in code or repo. `.env.example` only.
- Tenant DB passwords encrypted with Fernet (`PS_SECRET_ENCRYPTION_KEY`).
- MySQL at-rest encryption (InnoDB tablespace encryption / encrypted volumes); encrypted backups.
- Payment data: never stored; only gateway references (phase 2), webhook signatures verified.

## 7. Audit logging

Events: login success/failure, logout, session revocation, CRUD on business records (old/new values with sensitive fields masked), approvals/rejections, financial transactions, document upload/download, notice publication, role/permission changes, workflow configuration changes, settings changes.

- Written in the same transaction as the business change (no lost audit on commit, no orphan audit on rollback).
- Login failures written in a separate transaction (so they persist).
- Audit table append-only; production DB user lacks UPDATE/DELETE on it.
- Searchable audit viewer for Parish Admin/Priest; export restricted.
