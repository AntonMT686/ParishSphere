import axios, { AxiosError } from 'axios';
import { parishCodeHeader } from '@/lib/tenant';

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

let accessToken: string | null = null;

/** Access tokens live in memory only (never localStorage) – see docs/06-security.md. */
export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export const api = axios.create({ baseURL: '/api/v1', withCredentials: true, timeout: 30_000 });

api.interceptors.request.use((config) => {
  const code = parishCodeHeader();
  if (code) config.headers.set('X-Parish-Code', code);
  if (accessToken) config.headers.set('Authorization', `Bearer ${accessToken}`);
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err: AxiosError<ApiErrorBody>) => {
    const body = err.response?.data?.error;
    if (body) {
      return Promise.reject(
        new ApiError(err.response!.status, body.code, body.message, body.details, body.trace_id),
      );
    }
    return Promise.reject(new ApiError(err.response?.status ?? 0, 'NETWORK_ERROR', err.message));
  },
);
