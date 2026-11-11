import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { API, server } from '@/test/server';
import { renderRoutes, signIn } from '@/test/renderWithProviders';

const ref = (id: string, code: string, name: string) => ({ id, code, name });
const member = (id: string, name: string, rel: string, extra: Record<string, unknown> = {}) => ({
  id, code: `MEM${id}`, family: ref('F1', 'FAM000001', 'Arokiasamy'), anbiyam: ref('A1', 'ANB-001', 'St. Joseph'),
  first_name: name, last_name: null, full_name: name, name_local: null, gender: 'M', age: 40, relationship_to_head: rel,
  is_head: rel === 'HEAD', status: 'ACTIVE', date_of_death: null, sensitive_visible: false, sacraments_visible: false,
  created_at: '2026-01-01T00:00:00', ...extra,
});
const family = {
  id: 'F1', code: 'FAM000001', family_name: 'Arokiasamy', family_name_local: 'ஆரோக்கியசாமி', head_name: 'John',
  anbiyam: ref('A1', 'ANB-001', 'St. Joseph'), member_count: 2, phone: '98400 11111', city: 'Chennai', status: 'ACTIVE',
  registered_on: '2026-01-01', address_line1: '12 Church St', address_line2: null, state: null, postal_code: '600004',
  email: null, previous_parish: null, previous_diocese: null, remarks: null, merged_into: null, head_member_id: 'M1',
  members: [member('M1', 'John', 'HEAD'), member('M2', 'Peter', 'SON')], created_at: '2026-01-01T00:00:00',
};

function handlers() {
  server.use(
    http.get(`${API}/families`, () => HttpResponse.json({ items: [family], page: 1, size: 25, total: 1, pages: 1 })),
    http.get(`${API}/families/F1`, () => HttpResponse.json(family)),
    http.get(`${API}/families/F1/history`, () => HttpResponse.json({
      events: [{ event_type: 'REGISTERED', occurred_on: '2026-01-01', created_at: '2026-01-01T00:00:00', member: null,
        related_family: null, details: {}, performed_by: 'Mary Secretary' }], anbiyam_history: [] })),
    http.get(`${API}/members/M2`, () => HttpResponse.json(family.members[1])),
    http.get(`${API}/members/M2/memberships`, () => HttpResponse.json([])),
    http.get(`${API}/org-unit-types`, () => HttpResponse.json([])),
    http.get(`${API}/org-units`, () => HttpResponse.json({ items: [], page: 1, size: 20, total: 0, pages: 0 })),
  );
}

describe('families', () => {
  it('lists families and opens a family with members and history', async () => {
    signIn({ permissions: ['family.view', 'member.view'] });
    handlers();
    const { router } = renderRoutes(routes, '/families');
    expect(await screen.findByText('Arokiasamy')).toBeInTheDocument();
    expect(screen.getByText('ஆரோக்கியசாமி')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Register family/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Arokiasamy'));
    await waitFor(() => expect(router.state.location.pathname).toBe('/families/F1'));
    expect(await screen.findByText('Peter')).toBeInTheDocument();
    expect(screen.getAllByText('Registered').length).toBeGreaterThan(0);
    expect(screen.getByText(/Mary Secretary/)).toBeInTheDocument();
    // Read-only users get no action buttons.
    expect(screen.queryByRole('button', { name: 'Actions' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Peter'));
    const drawer = await screen.findByRole('presentation');
    expect(await within(drawer).findByText('Personal details are visible only to authorised staff.')).toBeInTheDocument();
  });

  it('registration warns about duplicates and requires confirmation', async () => {
    signIn({ permissions: ['family.view', 'family.create', 'member.view', 'member.create'] });
    handlers();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API}/families/check-duplicates`, () => HttpResponse.json([
        { family_id: 'F1', family_code: 'FAM000001', family_name: 'Arokiasamy', status: 'ACTIVE', reasons: ['Same family phone (98400 11111)'] }])),
      http.post(`${API}/families`, async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(family, { status: 201 });
      }),
    );
    renderRoutes(routes, '/families/new');
    fireEvent.change(await screen.findByLabelText(/Family name/, { selector: 'input[name="family_name"]' }), { target: { value: 'Arokiasamy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
    const first = await screen.findByLabelText(/First name/);
    fireEvent.change(first, { target: { value: 'John' } });
    fireEvent.mouseDown(screen.getByLabelText(/Gender/));
    fireEvent.click(await screen.findByRole('option', { name: 'Male' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText(/Possible duplicates/)).toBeInTheDocument();
    expect(screen.getByText(/Same family phone/)).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'Register family' });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByLabelText('I have checked: this is a different family'));
    fireEvent.click(submit);
    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toMatchObject({ family_name: 'Arokiasamy', confirm_not_duplicate: true, anbiyam_id: null });
    expect((created!.members as Record<string, unknown>[])[0]).toMatchObject({ first_name: 'John', relationship_to_head: 'HEAD', gender: 'M' });
  });
});
