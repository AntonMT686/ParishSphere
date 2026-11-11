import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { API, server } from '@/test/server';
import { renderRoutes, signIn } from '@/test/renderWithProviders';

const position = (code: string, name: string, role: string | null) => ({
  id: `P-${code}`, code, name, name_local: null, role_code: role, role_name: role ? `${role} role` : null, max_holders: 1, sort_order: 10,
});
const types = [
  { id: 'T1', code: 'COUNCIL', name: 'Parish Council', name_plural: 'Parish Council', name_local: 'பங்குப் பேரவை',
    description: null, member_kind: 'MEMBER', membership_rules: {}, allow_multiple_units: false, code_prefix: 'PC',
    is_system: true, sort_order: 10, unit_count: 1, positions: [position('PRESIDENT', 'President', 'PARISH_PRESIDENT')] },
  { id: 'T2', code: 'SOCIETY', name: 'Society', name_plural: 'Societies', name_local: 'சங்கங்கள்', description: 'Parish societies',
    member_kind: 'MEMBER', membership_rules: {}, allow_multiple_units: true, code_prefix: 'SOC', is_system: true,
    sort_order: 50, unit_count: 1, positions: [position('PRESIDENT', 'President', 'SOCIETY_LEADER'), position('SECRETARY', 'Secretary', 'COMMITTEE_SECRETARY')] },
];
const youth = {
  id: 'U1', code: 'SOC-001', name: 'Youth Society', name_local: 'இளைஞர் சங்கம்', type_code: 'SOCIETY', type_name: 'Society',
  parent: null, description: 'Youth of the parish', status: 'ACTIVE', established_on: '2010-06-01', meeting_place: 'Parish hall',
  meeting_schedule: 'Every Sunday', contact_phone: null, contact_email: null, sub_unit_count: 0, can_manage: true,
  created_at: '2026-01-01T00:00:00',
  office_bearers: [
    { id: 'B1', position_code: 'PRESIDENT', position_name: 'President', user_id: 'X', holder_name: 'Arul Raj',
      valid_from: '2026-01-01', valid_to: null, current: true, ended_at: null, grants_role: 'Society Leader', remarks: null },
  ],
};

function handlers() {
  server.use(
    http.get(`${API}/org-unit-types`, () => HttpResponse.json(types)),
    http.get(`${API}/org-units`, ({ request }) => {
      const url = new URL(request.url);
      const items = url.searchParams.get('parent') ? [] : [youth];
      return HttpResponse.json({ items, page: 1, size: 25, total: items.length, pages: 1 });
    }),
    http.get(`${API}/org-units/U1`, () => HttpResponse.json(youth)),
    http.get(`${API}/org-units/U1/office-bearers`, () => HttpResponse.json(youth.office_bearers)),
    http.get(`${API}/org-units/U1/memberships`, () =>
      HttpResponse.json({
        items: [{ id: 'MS1', org_unit: { id: 'U1', code: 'SOC-001', name: 'Youth Society' },
          member: { id: 'M9', code: 'MEM000009', name: 'Anitha Mary' }, family: { id: 'F9', code: 'FAM000009', name: 'Selvaraj' },
          gender: 'F', age: 19, joined_on: '2026-02-01', left_on: null, current: true, remarks: null }],
        page: 1, size: 20, total: 1, pages: 1,
      }),
    ),
  );
}

describe('organisations', () => {
  it('builds the Organisations menu from configured types', async () => {
    signIn({ permissions: ['org_unit.view'] });
    handlers();
    renderRoutes(routes, '/');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(await within(nav).findByText('Societies')).toBeInTheDocument();
    expect(within(nav).getByText('Parish Council')).toBeInTheDocument();
  });

  it('lists units of a type and opens the detail page', async () => {
    signIn({ permissions: ['org_unit.view', 'org_unit.manage_members'] });
    handlers();
    const { router } = renderRoutes(routes, '/org/society');
    expect(await screen.findByRole('heading', { name: 'Societies' })).toBeInTheDocument();
    expect(await screen.findByText('Youth Society')).toBeInTheDocument();
    expect(screen.getByText('President: Arul Raj')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /New Society/ })).not.toBeInTheDocument(); // no org_unit.create
    fireEvent.click(screen.getByText('Youth Society'));
    await waitFor(() => expect(router.state.location.pathname).toBe('/org/units/U1'));
    expect(await screen.findByText('Every Sunday')).toBeInTheDocument();
    expect(screen.getByText(/grants Society Leader/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Appoint office bearer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'End term' })).toBeInTheDocument();
    // Members card (memberships of the society)
    expect(await screen.findByText('Anitha Mary · MEM000009')).toBeInTheDocument();
    expect(screen.getByText(/Selvaraj · 19 years/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add member' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'End membership' })).toBeInTheDocument();
  });

  it('shows the Tamil name of the type in Tamil', async () => {
    const i18n = (await import('@/i18n')).default;
    await i18n.changeLanguage('ta');
    try {
      signIn({ permissions: ['org_unit.view'] });
      handlers();
      renderRoutes(routes, '/org/society');
      expect(await screen.findByRole('heading', { name: 'சங்கங்கள்' })).toBeInTheDocument();
    } finally {
      await i18n.changeLanguage('en');
    }
  });

  it('returns not found for an unknown type', async () => {
    signIn({ permissions: ['org_unit.view'] });
    handlers();
    renderRoutes(routes, '/org/nope');
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
  });
});
