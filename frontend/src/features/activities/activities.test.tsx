import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

const unit = { id: 'U1', name: 'Youth Society', type_code: 'SOCIETY' };
const can = (over: object = {}) => ({ edit: true, submit: true, delete: true, complete: false, cancel: true, attach: true, ...over });
const activity = (over: object = {}) => ({
  id: 'A1', code: 'ACT-2026-0001', title: 'Youth retreat', category: 'SPIRITUAL', org_unit: unit, activity_date: '2026-12-05',
  end_date: null, location: 'Kodaikanal', responsible: 'Arul Raj', status: 'DRAFT', planned_amount: '15000.00', actual_amount: null,
  participant_count: null, description: 'Two days', responsible_member: null, planned_details: 'Talks', actual_details: null,
  remarks: null, participants: [{ member_id: null, name: 'Guest speaker', role: 'Speaker' }], created_by: 'Anitha Mary',
  created_at: '2026-11-10T09:00:00', submitted_at: null, approved_at: null, completed_at: null, approval_id: null, can: can(), ...over,
});
const meeting = (over: object = {}) => ({
  id: 'M1', code: 'MTG-2026-0001', title: 'Monthly meeting', meeting_type: 'REGULAR', org_unit: unit,
  scheduled_at: '2026-11-08T18:00:00', ends_at: null, location: 'Parish hall', status: 'HELD', minutes_status: null, open_actions: 0,
  description: null, agenda: [{ seq: 1, title: 'Christmas liturgy', description: null, presenter: null }], called_by: 'Anitha Mary',
  cancel_reason: null, minutes: null, can: { edit: true, submit: false, delete: false, complete: false, cancel: false, attach: true }, ...over,
});
const empty = { items: [], page: 1, size: 50, total: 0, pages: 0 };

function common() {
  server.use(
    http.get(`${API}/activities/A1/attachments`, () => HttpResponse.json([])),
    http.get(`${API}/meetings/M1/attachments`, () => HttpResponse.json([])),
    http.get(`${API}/workflow/entities/:type/:id`, () => HttpResponse.json([])),
    http.get(`${API}/action-items`, () => HttpResponse.json(empty)),
  );
}

describe('activities', () => {
  it('creates an activity for the only organisation the user may record for', async () => {
    signIn({ permissions: ['activity.view', 'activity.create'] });
    let body: Record<string, unknown> = {};
    server.use(
      http.get(`${API}/org-units/mine`, () => HttpResponse.json({ parish: false, units: [{ ...unit, code: 'SOC-001', type_name: 'Society' }] })),
      http.post(`${API}/activities`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(activity(), { status: 201 });
      }),
      http.get(`${API}/activities/A1`, () => HttpResponse.json(activity())),
    );
    common();
    renderRoutes(routes, '/activities/new');
    fireEvent.change(await screen.findByLabelText(/Activity name/), { target: { value: 'Youth retreat' } });
    await waitFor(() => expect(screen.getByLabelText('Organisation')).toHaveTextContent('Youth Society'));
    fireEvent.click(screen.getByRole('button', { name: 'Add a guest' }));
    const name = screen.getAllByLabelText('Name').at(-1)!;
    fireEvent.change(name, { target: { value: 'Guest speaker' } });
    fireEvent.change(screen.getByLabelText('Planned budget'), { target: { value: '15000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(body.title).toBe('Youth retreat'));
    expect(body).toMatchObject({ org_unit_id: 'U1', planned_amount: '15000', participants: [{ member_id: null, name: 'Guest speaker', role: null }] });
    expect(await screen.findByRole('heading', { name: 'Youth retreat' })).toBeInTheDocument();
  });

  it('submits a draft for approval and shows the reviewer decision panel', async () => {
    signIn({ permissions: ['activity.view', 'activity.submit'] });
    let submitted = false;
    server.use(
      http.get(`${API}/activities/A1`, () => HttpResponse.json(activity(submitted ? { status: 'IN_REVIEW', can: can({ edit: false, submit: false, delete: false }) } : {}))),
      http.post(`${API}/activities/A1/submit`, () => {
        submitted = true;
        return HttpResponse.json(activity({ status: 'IN_REVIEW', can: can({ edit: false, submit: false, delete: false }) }));
      }),
    );
    common();
    renderRoutes(routes, '/activities/A1');
    fireEvent.click(await screen.findByRole('button', { name: 'Submit for approval' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Send for approval' }));
    expect(await screen.findByText(/waiting for approval and cannot be changed/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  });
});

describe('meetings', () => {
  it('records attendance from the member list', async () => {
    signIn({ permissions: ['meeting.view', 'meeting.update'] });
    let saved: { rows: { name: string; status: string }[] } | null = null;
    server.use(
      http.get(`${API}/meetings/M1`, () => HttpResponse.json(meeting())),
      http.get(`${API}/meetings/M1/attendance`, () => HttpResponse.json({
        recorded: false, present: 0, total: 2,
        rows: [{ member_id: 'X1', family_id: null, name: 'Arul Raj', status: 'ABSENT', remarks: null },
          { member_id: 'X2', family_id: null, name: 'Jessy Mary', status: 'ABSENT', remarks: null }],
      })),
      http.put(`${API}/meetings/M1/attendance`, async ({ request }) => {
        saved = (await request.json()) as typeof saved;
        return HttpResponse.json({ recorded: true, present: 1, total: 2, rows: saved!.rows });
      }),
    );
    common();
    renderRoutes(routes, '/meetings/M1');
    fireEvent.click(await screen.findByRole('tab', { name: 'Attendance' }));
    const table = await screen.findByRole('table', { name: 'Attendance' });
    fireEvent.click(within(within(table).getByRole('group', { name: 'Arul Raj' })).getByRole('button', { name: 'Present' }));
    fireEvent.click(within(within(table).getByRole('group', { name: 'Jessy Mary' })).getByRole('button', { name: 'Excused' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save attendance' }));
    await waitFor(() => expect(saved?.rows.map((r) => r.status)).toEqual(['PRESENT', 'EXCUSED']));
    expect(await screen.findByText('Attendance saved')).toBeInTheDocument();
  });

  it('writes minutes and submits them', async () => {
    signIn({ permissions: ['meeting.view', 'meeting.update', 'meeting.submit'] });
    let minutes: Record<string, unknown> = {};
    const withMinutes = (status: string) => meeting({ minutes: {
      id: 'MM1', status, summary: 'Opened with prayer.', points: [{ topic: 'Christmas liturgy', discussion: 'Midnight mass' }],
      resolutions: [{ text: 'Hire a sound system', decision: 'PASSED' }], recorded_by: 'Anitha Mary', submitted_at: null,
      approved_at: null, approval_id: null, can_edit: status === 'DRAFT', can_submit: status === 'DRAFT' } });
    let current = meeting();
    server.use(
      http.get(`${API}/meetings/M1`, () => HttpResponse.json(current)),
      http.put(`${API}/meetings/M1/minutes`, async ({ request }) => {
        minutes = (await request.json()) as Record<string, unknown>;
        current = withMinutes('DRAFT');
        return HttpResponse.json(current);
      }),
      http.post(`${API}/meetings/M1/minutes/submit`, () => { current = withMinutes('IN_REVIEW'); return HttpResponse.json(current); }),
    );
    common();
    renderRoutes(routes, '/meetings/M1');
    fireEvent.click(await screen.findByRole('tab', { name: 'Minutes' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Write minutes' }));
    const editor = screen.getByRole('region', { name: 'Minutes of the meeting' });
    fireEvent.change(within(editor).getByLabelText('Summary'), { target: { value: 'Opened with prayer.' } });
    fireEvent.change(within(editor).getByLabelText('Topic'), { target: { value: 'Christmas liturgy' } });
    fireEvent.click(within(editor).getByRole('button', { name: 'Add resolution' }));
    fireEvent.change(within(editor).getByLabelText('Resolution'), { target: { value: 'Hire a sound system' } });
    fireEvent.click(within(editor).getByRole('button', { name: 'Save minutes' }));
    await waitFor(() => expect(minutes.summary).toBe('Opened with prayer.'));
    expect(minutes).toMatchObject({ points: [{ topic: 'Christmas liturgy' }], resolutions: [{ text: 'Hire a sound system', decision: 'PASSED' }] });
    fireEvent.click(await screen.findByRole('button', { name: 'Submit for approval' }));
    expect(await screen.findByText('In review')).toBeInTheDocument();
  });
});

describe('action items', () => {
  it('lets the person responsible update progress from the drawer', async () => {
    signIn({ permissions: [] });
    const item = (over: object = {}) => ({
      id: 'AI1', code: 'AI-2026-00001', title: 'Get three quotations', description: null, org_unit: unit,
      source: { type: 'MEETING', id: 'M1', title: 'Monthly meeting' }, owner: { id: 'me', name: 'John Doe' }, owner_name: 'John Doe',
      due_date: '2026-11-01', status: 'OPEN', overdue: true, progress_pct: 0, completed_on: null, created_at: '2026-10-20T09:00:00',
      updates: [], can_update: true, can_edit: false, ...over,
    });
    let body: Record<string, unknown> = {};
    server.use(
      http.get(`${API}/action-items`, () => HttpResponse.json({ items: [item()], page: 1, size: 25, total: 1, pages: 1 })),
      http.get(`${API}/action-items/summary`, () => HttpResponse.json({ open: 1, overdue: 1 })),
      http.get(`${API}/action-items/AI1`, () => HttpResponse.json(item())),
      http.post(`${API}/action-items/AI1/progress`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(item({ status: 'DONE', overdue: false, progress_pct: 100 }));
      }),
    );
    renderRoutes(routes, '/action-items');
    expect(await screen.findByText('1 open for you · 1 overdue')).toBeInTheDocument();
    fireEvent.click(await screen.findByText('Get three quotations'));
    const drawer = await screen.findByRole('region', { name: 'Get three quotations' });
    expect(within(drawer).getByText('Monthly meeting')).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText('Note'), { target: { value: 'All three received' } });
    fireEvent.click(within(drawer).getByRole('button', { name: 'Mark done' }));
    await waitFor(() => expect(body).toMatchObject({ status: 'DONE', text: 'All three received' }));
  });
});

describe('calendar', () => {
  it('places activities and meetings on their days', async () => {
    signIn({ permissions: ['activity.view', 'meeting.view'] });
    const now = new Date();
    const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-15`;
    server.use(
      http.get(`${API}/org-units/mine`, () => HttpResponse.json({ parish: true, units: [] })),
      http.get(`${API}/calendar`, () => HttpResponse.json([
        { id: 'A1', kind: 'ACTIVITY', title: 'Food drive', start: `${day}T00:00:00`, end: null, all_day: true, status: 'APPROVED', org_unit: unit, location: null, link: '/activities/A1' },
        { id: 'M1', kind: 'MEETING', title: 'Council meeting', start: `${day}T18:00:00`, end: null, all_day: false, status: 'SCHEDULED', org_unit: null, location: null, link: '/meetings/M1' },
      ])),
    );
    renderRoutes(routes, '/calendar');
    await screen.findByText('Food drive');
    const grid = screen.getByRole('grid');
    const cell = within(grid).getAllByRole('gridcell').find((c) => c.textContent?.startsWith('15') && c.textContent.includes('Food drive'));
    expect(cell).toBeDefined();
    expect(within(cell!).getByRole('link', { name: /Council meeting/ })).toHaveAttribute('href', '/meetings/M1');
  });
});
