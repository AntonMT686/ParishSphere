import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import type { Me, TokenOut } from '@/api/types';

export const API = '*/api/v1';

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    id: '01HUSER0000000000000000001',
    username: 'admin',
    full_name: 'Parish Admin',
    email: 'admin@stmarys.org',
    phone: null,
    preferred_language: 'en',
    must_change_password: false,
    last_login_at: null,
    roles: ['PARISH_ADMIN'],
    permissions: ['user.view', 'user.create', 'user.update', 'user.assign_role', 'role.view', 'role.manage', 'audit.view', 'audit.export'],
    ...overrides,
  };
}

export function makeToken(me: Me = makeMe(), overrides: Partial<TokenOut> = {}): TokenOut {
  return { access_token: 'access-1', token_type: 'bearer', expires_in: 900, idle_timeout_seconds: 1800, user: me, ...overrides };
}

export const defaultHandlers = [
  http.get(`${API}/tenant/branding`, () =>
    HttpResponse.json({
      parish_id: 'P1', code: 'STMARYS', name: "St. Mary's Church", display_name: "St. Mary's Church",
      logo_url: null, primary_color: null, default_language: 'en', currency: 'INR', diocese_name: 'Chennai Diocese',
    }),
  ),
  http.get(`${API}/notifications/unread-count`, () => HttpResponse.json({ unread: 2 })),
  http.get(`${API}/notifications`, () =>
    HttpResponse.json({
      items: [
        { id: 'N1', event_code: 'general.message', title: 'Choir practice', body: 'Friday 6pm', link: null,
          entity_type: null, entity_id: null, is_important: true, is_read: false, created_at: '2026-11-09T10:00:00' },
      ],
      page: 1, size: 6, total: 1, pages: 1,
    }),
  ),
  http.post(`${API}/auth/refresh`, () =>
    HttpResponse.json({ error: { code: 'INVALID_REFRESH_TOKEN', message: 'no', details: [] } }, { status: 401 }),
  ),
  http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 204 })),
];

export const server = setupServer(...defaultHandlers);
