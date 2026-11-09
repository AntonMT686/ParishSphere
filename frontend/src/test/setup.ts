import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import '@/i18n';
import { setAccessToken } from '@/api/client';
import { useAuthStore } from '@/auth/authStore';
import { server } from './server';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: query.includes('min-width'), // desktop layout (permanent sidebar) in tests
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

const initialAuth = useAuthStore.getState();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  setAccessToken(null);
  useAuthStore.setState({ ...initialAuth, status: 'anonymous', user: null, permissions: new Set(), endReason: null });
  window.localStorage.clear();
  document.cookie.split('; ').forEach((c) => {
    const name = c.split('=')[0];
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
});
afterAll(() => server.close());
