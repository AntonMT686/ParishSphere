import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { ForbiddenPage } from '@/features/ForbiddenPage';
import { useAuthStore, useCan } from './authStore';

export function LoadingScreen() {
  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }} role="progressbar" aria-busy>
      <CircularProgress />
    </Box>
  );
}

/** Signed-in area: redirects to /login (remembering the page) or to the forced password change. */
export function RequireAuth() {
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const endReason = useAuthStore((s) => s.endReason);
  const location = useLocation();
  if (status === 'loading') return <LoadingScreen />;
  if (status === 'anonymous') {
    const params = new URLSearchParams();
    const from = location.pathname + location.search;
    if (from !== '/') params.set('from', from);
    if (endReason === 'timeout' || endReason === 'revoked') params.set('reason', endReason);
    const qs = params.toString();
    return <Navigate to={`/login${qs ? `?${qs}` : ''}`} replace />;
  }
  if (user?.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

/** Pages for signed-out users only (login, forgot password). */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();
  if (status === 'loading') return <LoadingScreen />;
  if (status === 'authenticated') {
    const from = new URLSearchParams(location.search).get('from');
    return <Navigate to={from && from.startsWith('/') && !from.startsWith('//') ? from : '/'} replace />;
  }
  return <>{children}</>;
}

/** UX-only route guard; the backend enforces every permission independently. */
export function RequirePermission({ anyOf, children }: { anyOf: string | string[]; children: ReactNode }) {
  const can = useCan();
  return can(anyOf) ? <>{children}</> : <ForbiddenPage />;
}

export function PermissionGate({ anyOf, children, fallback = null }: {
  anyOf: string | string[];
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const can = useCan();
  return <>{can(anyOf) ? children : fallback}</>;
}
