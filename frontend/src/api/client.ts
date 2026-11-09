import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { parishCodeHeader } from '@/lib/tenant';
import type { TokenOut } from './types';

export interface ApiErrorBody {
  error: { code: string; message: string; details: { field: string; message: string }[]; trace_id?: string };
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: { field: string; message: string }[] = [],
    public readonly traceId?: string,
  ) {
    super(message);
  }
}

export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  total: number;
  pages: number;
}

/* ------------------------------------------------------------------ token state (memory only) */
let accessToken: string | null = null;
let accessExpiresAt = 0;

/** Access tokens live in memory only (never localStorage) – see docs/06-security.md. */
export function setAccessToken(token: string | null, expiresInSeconds = 0): void {
  accessToken = token;
  accessExpiresAt = token ? Date.now() + expiresInSeconds * 1000 : 0;
}

export function accessTokenExpiresAt(): number {
  return accessExpiresAt;
}

export function hasAccessToken(): boolean {
  return accessToken !== null;
}

export function readCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

/* ------------------------------------------------------------------ auth hooks (set by the auth store) */
type SessionEndReason = 'timeout' | 'revoked' | 'logout';
interface AuthHandlers {
  onRefreshed: (t: TokenOut) => void;
  onSessionEnded: (reason: SessionEndReason) => void;
}
let handlers: AuthHandlers = { onRefreshed: () => {}, onSessionEnded: () => {} };

export function configureAuthHandlers(h: AuthHandlers): void {
  handlers = h;
}

/* ------------------------------------------------------------------ axios instance */
export const api = axios.create({ baseURL: '/api/v1', withCredentials: true, timeout: 30_000 });

api.interceptors.request.use((config) => {
  const code = parishCodeHeader();
  if (code) config.headers.set('X-Parish-Code', code);
  if (accessToken && !config.headers.has('Authorization')) config.headers.set('Authorization', `Bearer ${accessToken}`);
  const csrf = readCookie('ps_csrf');
  if (csrf && config.method && config.method.toLowerCase() !== 'get') config.headers.set('X-CSRF-Token', csrf);
  return config;
});

function toApiError(err: AxiosError<ApiErrorBody>): ApiError {
  const body = err.response?.data?.error;
  if (body) return new ApiError(err.response!.status, body.code, body.message, body.details, body.trace_id);
  return new ApiError(err.response?.status ?? 0, 'NETWORK_ERROR', err.message);
}

const SESSION_ENDED = new Set(['SESSION_EXPIRED', 'SESSION_REVOKED', 'REFRESH_TOKEN_REUSED', 'INVALID_REFRESH_TOKEN']);
const AUTH_URLS = ['/auth/login', '/auth/refresh', '/auth/logout'];

/* ------------------------------------------------------------------ refresh (single flight, cross-tab lock) */
let inFlight: Promise<TokenOut> | null = null;

async function doRefresh(): Promise<TokenOut> {
  const { data } = await api.post<TokenOut>('/auth/refresh', null, { headers: { Authorization: '' } });
  setAccessToken(data.access_token, data.expires_in);
  handlers.onRefreshed(data);
  return data;
}

/**
 * Rotate the refresh token. Concurrent callers share one request; across browser tabs the Web Locks
 * API serialises refreshes so two tabs never present the same (single-use) refresh token.
 */
export function refreshSession(): Promise<TokenOut> {
  if (!inFlight) {
    const run = () => doRefresh();
    const locked =
      typeof navigator !== 'undefined' && 'locks' in navigator && navigator.locks
        ? navigator.locks.request('ps-auth-refresh', run)
        : run();
    inFlight = (locked as Promise<TokenOut>).finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

api.interceptors.response.use(
  (r) => r,
  async (err: AxiosError<ApiErrorBody>) => {
    const apiErr = toApiError(err);
    const config = err.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const isAuthUrl = AUTH_URLS.some((u) => config?.url?.endsWith(u));
    if (apiErr.status === 401 && config && !isAuthUrl && !config._retried && apiErr.code === 'TOKEN_EXPIRED') {
      try {
        await refreshSession();
        config._retried = true;
        config.headers.delete('Authorization');
        return api.request(config as AxiosRequestConfig);
      } catch (refreshErr) {
        return Promise.reject(refreshErr);
      }
    }
    if (apiErr.status === 401 && SESSION_ENDED.has(apiErr.code)) {
      setAccessToken(null);
      handlers.onSessionEnded(apiErr.code === 'SESSION_EXPIRED' ? 'timeout' : 'revoked');
    }
    return Promise.reject(apiErr);
  },
);

/* ------------------------------------------------------------------ downloads */
function filenameFrom(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (star?.[1]) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain?.[1] ?? fallback;
}

/** Download an authenticated file (exports) and hand it to the browser. */
export async function downloadFile(url: string, params?: Record<string, unknown>, fallbackName = 'download') {
  const res = await api.get<Blob>(url, { params, responseType: 'blob' });
  const name = filenameFrom(res.headers['content-disposition'] as string | undefined, fallbackName);
  const href = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
  return name;
}
