import { create } from 'zustand';
import {
  ApiError,
  api,
  configureAuthHandlers,
  readCookie,
  refreshSession,
  setAccessToken,
} from '@/api/client';
import type { Me, TokenOut } from '@/api/types';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous';
export type EndReason = 'timeout' | 'revoked' | 'logout' | null;

interface AuthState {
  status: AuthStatus;
  user: Me | null;
  permissions: Set<string>;
  idleTimeoutSeconds: number;
  endReason: EndReason;
  lastRefreshAt: number;
  bootstrap: () => Promise<void>;
  login: (username: string, password: string) => Promise<Me>;
  logout: (reason?: EndReason, opts?: { everywhere?: boolean; broadcast?: boolean }) => Promise<void>;
  refresh: () => Promise<void>;
  reloadMe: () => Promise<void>;
}

const channel: BroadcastChannel | null =
  typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('ps-auth') : null;

function fromToken(t: TokenOut) {
  setAccessToken(t.access_token, t.expires_in);
  return {
    status: 'authenticated' as const,
    user: t.user,
    permissions: new Set(t.user.permissions ?? []),
    idleTimeoutSeconds: t.idle_timeout_seconds,
    endReason: null,
    lastRefreshAt: Date.now(),
  };
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'loading',
  user: null,
  permissions: new Set(),
  idleTimeoutSeconds: 1800,
  endReason: null,
  lastRefreshAt: 0,

  /** Restore a session after page load using the HttpOnly refresh cookie. */
  bootstrap: async () => {
    // No CSRF cookie ⇒ no refresh cookie either (they are set together): skip the doomed request.
    if (!readCookie('ps_csrf')) {
      set({ status: 'anonymous', user: null, permissions: new Set() });
      return;
    }
    try {
      await refreshSession(); // onRefreshed handler fills the store
    } catch {
      setAccessToken(null);
      set({ status: 'anonymous', user: null, permissions: new Set() });
    }
  },

  login: async (username, password) => {
    const { data } = await api.post<TokenOut>('/auth/login', { username, password });
    set(fromToken(data));
    return data.user;
  },

  refresh: async () => {
    await refreshSession();
  },

  reloadMe: async () => {
    const { data } = await api.get<Me>('/auth/me');
    set({ user: data, permissions: new Set(data.permissions ?? []) });
  },

  logout: async (reason = 'logout', opts = {}) => {
    const { everywhere = false, broadcast = true } = opts;
    try {
      if (get().status === 'authenticated') {
        await api.post(everywhere ? '/auth/logout-all' : '/auth/logout');
      }
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    } finally {
      setAccessToken(null);
      set({ status: 'anonymous', user: null, permissions: new Set(), endReason: reason });
      if (broadcast) channel?.postMessage({ type: 'logout', reason });
    }
  },
}));

configureAuthHandlers({
  onRefreshed: (t) => useAuthStore.setState(fromToken(t)),
  onSessionEnded: (reason) => {
    setAccessToken(null);
    useAuthStore.setState({ status: 'anonymous', user: null, permissions: new Set(), endReason: reason });
  },
});

channel?.addEventListener('message', (ev: MessageEvent<{ type: string; reason?: EndReason }>) => {
  if (ev.data?.type === 'logout') {
    void useAuthStore.getState().logout(ev.data.reason ?? 'logout', { broadcast: false });
  }
});

/* ------------------------------------------------------------------ permission helpers */
export function useCan(): (code: string | string[]) => boolean {
  const permissions = useAuthStore((s) => s.permissions);
  return (code) => (Array.isArray(code) ? code.some((c) => permissions.has(c)) : permissions.has(code));
}
