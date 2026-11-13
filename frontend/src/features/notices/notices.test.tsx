import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

const item = (over: object = {}) => ({
  id: 'N1', code: 'NTC-2026-0001', category: 'WEEKLY', title: 'Christmas Mass timings', title_local: 'கிறிஸ்துமஸ் திருப்பலி நேரங்கள்',
  excerpt: 'Midnight Mass at 11:30 pm.', excerpt_local: null, org_unit: null, audience_all: true, audience: [], is_important: true,
  is_public: true, publish_at: '2026-11-12T09:00:00', expires_at: null, status: 'PUBLISHED', state: 'LIVE', attachments: 0, ...over,
});
const detail = (over: object = {}) => ({
  ...item(), body: 'Midnight Mass at 11:30 pm.\nChristmas Day: 7 am and 9 am.', body_local: 'நள்ளிரவு திருப்பலி இரவு 11:30.',
  created_by: 'Mary Secretary', created_at: '2026-11-10T09:00:00', approved_at: null, approval_id: null,
  can: { edit: false, submit: false, delete: false, publish: false, archive: false }, ...over,
});

describe('notices', () => {
  it('shows the board with important notices and filters by category', async () => {
    signIn({ permissions: ['notice.view'] });
    let lastCategory: string | null = null;
    server.use(http.get(`${API}/notices/board`, ({ request }) => {
      lastCategory = new URL(request.url).searchParams.get('category');
      return HttpResponse.json({ items: [item(), item({ id: 'N2', title: 'Choir practice', is_important: false, category: 'EVENT' })], page: 1, size: 50, total: 2, pages: 1 });
    }));
    renderRoutes(routes, '/notices');
    const card = await screen.findByRole('article', { name: 'Christmas Mass timings' });
    expect(within(card).getByText('Important')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Prepare & approve' })).not.toBeInTheDocument(); // readers only see the board
    fireEvent.click(screen.getByRole('button', { name: 'Event' }));
    await waitFor(() => expect(lastCategory).toBe('EVENT'));
  });

  it('reads a notice in Tamil', async () => {
    signIn({ permissions: ['notice.view'] });
    server.use(http.get(`${API}/notices/N1`, () => HttpResponse.json(detail())));
    renderRoutes(routes, '/notices/N1');
    expect(await screen.findByRole('heading', { name: 'Christmas Mass timings' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'தமிழ்' }));
    expect(screen.getByRole('heading', { name: 'கிறிஸ்துமஸ் திருப்பலி நேரங்கள்' })).toBeInTheDocument();
    expect(screen.getByText('நள்ளிரவு திருப்பலி இரவு 11:30.')).toBeInTheDocument();
  });

  it('prepares a notice for selected organisations and submits it', async () => {
    signIn({ permissions: ['notice.view', 'notice.create', 'notice.update', 'notice.submit', 'org_unit.view'] });
    let body: Record<string, unknown> = {};
    let submitted = false;
    const draft = () => detail({ id: 'N9', status: submitted ? 'IN_REVIEW' : 'DRAFT', state: submitted ? 'IN_REVIEW' : 'DRAFT', audience_all: false,
      audience: [{ id: 'U1', name: 'Youth Society' }], can: { edit: !submitted, submit: !submitted, delete: !submitted, publish: false, archive: false } });
    server.use(
      http.get(`${API}/org-unit-types`, () => HttpResponse.json([])),
      http.get(`${API}/org-units/mine`, () => HttpResponse.json({ parish: true, units: [] })),
      http.get(`${API}/org-units`, () => HttpResponse.json({ items: [{ id: 'U1', code: 'SOC-001', name: 'Youth Society' }], page: 1, size: 20, total: 1, pages: 1 })),
      http.post(`${API}/notices`, async ({ request }) => { body = (await request.json()) as Record<string, unknown>; return HttpResponse.json(draft(), { status: 201 }); }),
      http.get(`${API}/notices/N9`, () => HttpResponse.json(draft())),
      http.get(`${API}/notices/N9/attachments`, () => HttpResponse.json([])),
      http.get(`${API}/workflow/entities/:t/:id`, () => HttpResponse.json([])),
      http.post(`${API}/notices/N9/submit`, () => { submitted = true; return HttpResponse.json(draft()); }),
    );
    renderRoutes(routes, '/notices/new');
    fireEvent.change(await screen.findByLabelText(/^Title\s*\*$/), { target: { value: 'Youth retreat' } });
    fireEvent.change(screen.getByLabelText(/^Notice\s*\*$/), { target: { value: 'Bring your Bibles.' } });
    fireEvent.click(screen.getByLabelText('Only selected organisations'));
    expect(screen.getByLabelText('Show on the public / member portal')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Add an organisation'), { target: { value: 'You' } });
    fireEvent.click(await screen.findByRole('option', { name: /Youth Society/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(body.title).toBe('Youth retreat'));
    expect(body).toMatchObject({ audience_all: false, audience_org_units: ['U1'], is_public: false, category: 'WEEKLY', publish_at: null });
    fireEvent.click(await screen.findByRole('button', { name: 'Submit for approval' }));
    expect(await screen.findByText('In review')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Submit for approval' })).not.toBeInTheDocument();
  }, 20_000);
});
