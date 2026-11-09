/**
 * Client-side tenant identification. The backend is the authority (it resolves the parish from the
 * Host subdomain or the X-Parish-Code header); the client only decides whether it must send the header.
 */
const RESERVED = new Set(['www', 'app', 'api', 'admin', 'platform']);
const STORAGE_KEY = 'ps.parishCode';

/** Returns the parish subdomain when served from `<parish>.<base-domain>`, otherwise null. */
export function subdomainFromHost(hostname: string): string | null {
  const parts = hostname.toLowerCase().split('.');
  // stmarys.localhost → 2 parts; stmarys.parishsphere.app → 3 parts
  const isLocal = parts[parts.length - 1] === 'localhost';
  const minParts = isLocal ? 2 : 3;
  if (parts.length < minParts) return null;
  if (isLocal && parts.length === 2 && parts[0] === 'parishsphere') return null;
  const sub = parts[0] ?? '';
  if (!sub || RESERVED.has(sub) || /^\d+$/.test(sub)) return null;
  return sub;
}

export function getStoredParishCode(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredParishCode(code: string | null): void {
  try {
    if (code) window.localStorage.setItem(STORAGE_KEY, code.toUpperCase());
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable – header falls back to env default */
  }
}

/** Parish code to send as X-Parish-Code when no subdomain identifies the parish. */
export function parishCodeHeader(hostname = window.location.hostname): string | null {
  if (subdomainFromHost(hostname)) return null;
  return getStoredParishCode() ?? (import.meta.env.VITE_DEFAULT_PARISH_CODE as string | undefined) ?? null;
}
