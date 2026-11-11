import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

const profile = {
  name: "St. Mary's Church", name_local: null, patron_saint: 'Our Lady of Good Health', established_on: '1890-05-01',
  address_line1: 'Church Street', address_line2: null, city: 'Chennai', state: 'Tamil Nadu', postal_code: '600001',
  phone: null, email: null, website: null, about: null, logo_url: null, primary_color: null, default_language: 'en',
  currency: 'INR', timezone: 'Asia/Kolkata', fy_start_month: 4, code: 'STMARYS', diocese_name: 'Chennai Diocese',
  parish_priest: 'Rev. Fr. Joseph', updated_at: '2026-11-01T00:00:00',
};
const assignment = (id: string, role: string, from: string, until: string | null, current: boolean) => ({
  id, role, appointed_on: from, relieved_on: until, current, responsibilities: null, appointment_ref: null,
  relieving_reason: null, remarks: null, grants_role: role === 'PARISH_PRIEST',
});
const joseph = {
  id: 'PR1', title: 'Rev. Fr.', full_name: 'Joseph Antony', display_name: 'Rev. Fr. Joseph Antony', name_local: null,
  date_of_birth: null, ordination_date: '2005-04-20', clergy_type: 'DIOCESAN', home_diocese: 'Chennai', congregation: null,
  phone: '9876543210', email: null, status: 'ACTIVE', user: null, remarks: null, current_roles: ['PARISH_PRIEST'],
  assignments: [assignment('A2', 'PARISH_PRIEST', '2024-06-01', null, true), assignment('A1', 'ASSISTANT_PRIEST', '2019-06-01', '2022-06-01', false)],
  created_at: '2026-01-01T00:00:00',
};

describe('parish settings', () => {
  it('saves the profile and refreshes branding', async () => {
    signIn({ permissions: ['settings.view', 'settings.update'] });
    let body: Record<string, unknown> = {};
    server.use(
      http.get(`${API}/parish/profile`, () => HttpResponse.json(profile)),
      http.patch(`${API}/parish/profile`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...profile, ...body });
      }),
    );
    renderRoutes(routes, '/admin/settings');
    const name = await screen.findByLabelText(/Parish name/);
    expect(name).toHaveValue("St. Mary's Church");
    fireEvent.change(name, { target: { value: "St. Mary's Shrine" } });
    fireEvent.change(screen.getByLabelText('Website'), { target: { value: 'https://stmarys.example' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(body.name).toBe("St. Mary's Shrine"));
    expect(body.website).toBe('https://stmarys.example');
    expect(body.phone).toBeNull(); // blank optional fields are cleared, not sent as ''
    expect(body.fy_start_month).toBe(4);
    expect(await screen.findByText('Saved')).toBeInTheDocument();
  });

  it('is read-only without settings.update', async () => {
    signIn({ permissions: ['settings.view'] });
    server.use(http.get(`${API}/parish/profile`, () => HttpResponse.json(profile)));
    renderRoutes(routes, '/admin/settings');
    expect(await screen.findByLabelText(/Parish name/)).toBeDisabled();
    expect(screen.getByText(/only the parish administrator can change them/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload logo' })).not.toBeInTheDocument();
  });
});

describe('priests', () => {
  it('lists priests and opens the detail page with appointment history', async () => {
    signIn({ permissions: ['priest.view'] });
    server.use(
      http.get(`${API}/priests`, () => HttpResponse.json({ items: [joseph], page: 1, size: 25, total: 1, pages: 1 })),
      http.get(`${API}/priests/PR1`, () => HttpResponse.json(joseph)),
    );
    renderRoutes(routes, '/admin/priests');
    fireEvent.click(await screen.findByText('Rev. Fr. Joseph Antony'));
    const table = await screen.findByRole('table', { name: 'Appointments' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getByText('Current')).toBeInTheDocument();
    expect(within(rows[2]!).getByText('Assistant Priest')).toBeInTheDocument();
    // view-only: no actions
    expect(screen.queryByRole('button', { name: 'Appoint' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Relieve' })).not.toBeInTheDocument();
  });

  it('appoints a new parish priest with same-day handover', async () => {
    signIn({ permissions: ['priest.view', 'priest.update'] });
    const peter = { ...joseph, id: 'PR2', full_name: 'Peter Paul', display_name: 'Rev. Fr. Peter Paul', current_roles: [], assignments: [] };
    let body: Record<string, unknown> = {};
    server.use(
      http.get(`${API}/priests/PR2`, () => HttpResponse.json(peter)),
      http.post(`${API}/priests/PR2/assignments`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        if (!body.relieve_current) {
          return HttpResponse.json({ error: { code: 'CURRENT_PARISH_PRIEST_EXISTS', message: 'exists', details: [] } }, { status: 409 });
        }
        return HttpResponse.json(peter);
      }),
    );
    renderRoutes(routes, '/admin/priests/PR2');
    fireEvent.click(await screen.findByRole('button', { name: 'Appoint' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText('Role'));
    fireEvent.click(await screen.findByRole('option', { name: 'Parish Priest' }));
    fireEvent.change(within(dialog).getByLabelText('From'), { target: { value: '2026-12-01' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Appoint' }));
    expect(await screen.findByText(/already has a Parish Priest/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText(/Relieve the current Parish Priest/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Appoint' }));
    await waitFor(() => expect(body.relieve_current).toBe(true));
    expect(body).toMatchObject({ role: 'PARISH_PRIEST', appointed_on: '2026-12-01', relieved_on: null });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('relieves an assignment on a handover date', async () => {
    signIn({ permissions: ['priest.view', 'priest.update'] });
    let body: Record<string, unknown> = {};
    server.use(
      http.get(`${API}/priests/PR1`, () => HttpResponse.json(joseph)),
      http.post(`${API}/priests/PR1/assignments/A2/relieve`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(joseph);
      }),
    );
    renderRoutes(routes, '/admin/priests/PR1');
    fireEvent.click(await screen.findByRole('button', { name: 'Relieve' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Handover date'), { target: { value: '2027-01-15' } });
    fireEvent.change(within(dialog).getByLabelText('Reason'), { target: { value: 'Transferred' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Relieve' }));
    await waitFor(() => expect(body).toEqual({ relieved_on: '2027-01-15', reason: 'Transferred' }));
  });

  it('shows the serving clergy on the dashboard', async () => {
    signIn({ permissions: [] });
    server.use(http.get(`${API}/parish/clergy`, () => HttpResponse.json({
      parish_priest: { id: 'PR1', name: 'Rev. Fr. Joseph Antony', role: 'PARISH_PRIEST', since: '2024-06-01' },
      others: [{ id: 'PR3', name: 'Rev. Fr. Arul', role: 'ASSISTANT_PRIEST', since: '2025-06-01' }],
    })));
    renderRoutes(routes, '/');
    expect(await screen.findByText('Rev. Fr. Joseph Antony')).toBeInTheDocument();
    expect(screen.getByText('Assistant Priest')).toBeInTheDocument();
  });
});
