import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { useAuthStore } from '@/auth/authStore';
import { API, makeMe, makeToken, server } from '@/test/server';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { routes } from './router';

const usersPage = {
  items: [
    { id: 'U1', username: 'treasurer', full_name: 'Mr Treasurer', email: 't@stmarys.org', phone: null,
      preferred_language: 'en', is_active: true, is_locked: true, must_change_password: false,
      last_login_at: null, created_at: '2026-11-01T10:00:00', roles: ['PARISH_TREASURER'] },
  ],
  page: 1, size: 25, total: 1, pages: 1,
};
const roles = [
  { id: 'R1', code: 'PARISH_TREASURER', name: 'Parish Treasurer', description: '', is_system: true, scope_type: 'PARISH', permission_count: 20, active_users: 1 },
];

describe('routing & guards', () => {
  it('sends anonymous users to login, remembering the page', async () => {
    useAuthStore.setState({ status: 'anonymous' });
    const { router } = renderRoutes(routes, '/admin/users');
    expect(await screen.findByLabelText('Parish code')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?from=%2Fadmin%2Fusers');
  });

  it('shows the timeout message after an idle sign-out', async () => {
    useAuthStore.setState({ status: 'anonymous', endReason: 'timeout' });
    renderRoutes(routes, '/');
    expect(await screen.findByText(/30 minutes of inactivity/)).toBeInTheDocument();
  });

  it('logs in and returns to the requested page', async () => {
    useAuthStore.setState({ status: 'anonymous' });
    server.use(
      http.post(`${API}/auth/login`, async ({ request }) => {
        const body = (await request.json()) as { username: string; password: string };
        return body.password === 'right'
          ? HttpResponse.json(makeToken())
          : HttpResponse.json({ error: { code: 'INVALID_CREDENTIALS', message: 'x', details: [] } }, { status: 401 });
      }),
      http.get(`${API}/users`, () => HttpResponse.json(usersPage)),
      http.get(`${API}/roles`, () => HttpResponse.json(roles)),
    );
    const { router } = renderRoutes(routes, '/login?from=%2Fadmin%2Fusers');
    fireEvent.change(await screen.findByLabelText('Username or email'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Incorrect username or password.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'right' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/admin/users'));
    expect(await screen.findByText('Mr Treasurer')).toBeInTheDocument();
  });

  it('forces a password change when required', async () => {
    signIn({ must_change_password: true });
    const { router } = renderRoutes(routes, '/');
    await waitFor(() => expect(router.state.location.pathname).toBe('/change-password'));
    expect(screen.getByText('Please choose a new password before continuing.')).toBeInTheDocument();
  });

  it('hides navigation and blocks pages without permission', async () => {
    signIn({ roles: ['PARISH_TREASURER'], permissions: ['finance.view', 'finance.create'] });
    renderRoutes(routes, '/admin/users');
    expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByText('Transactions')).toBeInTheDocument();
    expect(within(nav).queryByText('Users')).not.toBeInTheDocument();
    expect(within(nav).queryByText('Families')).not.toBeInTheDocument();
  });

  it('renders the admin shell with notifications and user menu', async () => {
    signIn();
    renderRoutes(routes, '/');
    expect(await screen.findByRole('heading', { name: /Welcome to St. Mary's Church/ })).toBeInTheDocument();
    const bell = screen.getByRole('button', { name: 'Notifications' });
    await waitFor(() => expect(within(bell).getByText('2')).toBeInTheDocument());
    fireEvent.click(bell);
    expect(await screen.findByText('Choir practice')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('presentation'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByText('Choir practice')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'My profile' }));
    expect(screen.getByText('admin@stmarys.org')).toBeInTheDocument();
  });

  it('lists users from the API with server pagination and opens the drawer', async () => {
    signIn();
    let lastQuery = '';
    server.use(
      http.get(`${API}/users`, ({ request }) => {
        lastQuery = new URL(request.url).search;
        return HttpResponse.json(usersPage);
      }),
      http.get(`${API}/users/U1`, () => HttpResponse.json(usersPage.items[0])),
      http.get(`${API}/users/U1/roles`, () => HttpResponse.json([])),
      http.get(`${API}/roles`, () => HttpResponse.json(roles)),
    );
    renderRoutes(routes, '/admin/users');
    expect(await screen.findByText('Mr Treasurer')).toBeInTheDocument();
    expect(lastQuery).toContain('page=1');
    expect(lastQuery).toContain('size=25');
    expect(lastQuery).toContain('sort=full_name');
    fireEvent.click(screen.getByText('Mr Treasurer'));
    expect(await screen.findByText('@treasurer')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unlock' })).toBeInTheDocument();
  });

  it('skips the refresh call when there is no session cookie', async () => {
    let called = false;
    server.use(http.post(`${API}/auth/refresh`, () => { called = true; return HttpResponse.json(makeToken()); }));
    useAuthStore.setState({ status: 'loading' });
    await useAuthStore.getState().bootstrap();
    expect(called).toBe(false);
    expect(useAuthStore.getState().status).toBe('anonymous');
  });

  it('restores the session from the refresh cookie on load', async () => {
    server.use(http.post(`${API}/auth/refresh`, () => HttpResponse.json(makeToken(makeMe({ full_name: 'Fr. Antony' })))));
    useAuthStore.setState({ status: 'loading' });
    document.cookie = 'ps_csrf=abc; path=/';
    await useAuthStore.getState().bootstrap();
    expect(useAuthStore.getState()).toMatchObject({ status: 'authenticated', user: { full_name: 'Fr. Antony' } });
  });
});
