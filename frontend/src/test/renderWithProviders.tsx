import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router-dom';
import { setAccessToken } from '@/api/client';
import type { Me } from '@/api/types';
import { AppProviders } from '@/app/AppProviders';
import { useAuthStore } from '@/auth/authStore';
import { makeMe } from './server';

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

export function signIn(me: Partial<Me> = {}): Me {
  const user = makeMe(me);
  setAccessToken('access-1', 900);
  useAuthStore.setState({
    status: 'authenticated',
    user,
    permissions: new Set(user.permissions ?? []),
    idleTimeoutSeconds: 1800,
    endReason: null,
    lastRefreshAt: Date.now(),
  });
  return user;
}

export function renderRoutes(routes: RouteObject[], initialPath = '/') {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  const utils = render(
    <AppProviders client={client()} skipBootstrap>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...utils, router };
}

export function renderWithProviders(ui: ReactElement) {
  return render(
    <AppProviders client={client()} skipBootstrap>
      {ui}
    </AppProviders>,
  );
}
