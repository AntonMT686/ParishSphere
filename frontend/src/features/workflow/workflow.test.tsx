import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

const ref = (id: string, name: string) => ({ id, name });
const summary = (over: object = {}) => ({
  id: 'I1', entity_type: 'ACTIVITY', entity_label: 'Activity', entity_id: 'ACT-1', title: 'Youth retreat', link: null,
  org_unit: ref('U1', 'Youth Society'), amount: null, category: null, status: 'IN_PROGRESS', cycle: 1, stage_index: 1,
  stage_name: 'Parish Secretary', stage_count: 3, pending_with: ['Mary Secretary'], submitted_by: ref('S1', 'John Submitter'),
  submitted_at: '2026-11-10T09:00:00', completed_at: null, ...over,
});
const task = (id: string, title: string) => ({
  id, status: 'PENDING', stage_index: 1, stage_name: 'Parish Secretary', kind: 'REVIEW', is_escalation: false,
  delegated_from: null, due_at: null, overdue: false, created_at: '2026-11-10T09:00:00', acted_at: null, comment: null,
  instance: summary({ id: `I-${id}`, title }),
});
const detail = (over: object = {}) => ({
  ...summary(),
  definition: { code: 'ACTIVITY_DEFAULT', version: 1, name: 'Activity approval' },
  stages: [
    { index: 0, name: 'President', kind: 'REVIEW', quorum: 'ANY', optional: true, state: 'DONE',
      tasks: [{ id: 'T0', assignee: ref('P', 'Paul President'), delegated_from: null, status: 'APPROVED', is_escalation: false,
        due_at: null, acted_at: '2026-11-10T10:00:00', acted_by: null, comment: 'Good plan' }] },
    { index: 1, name: 'Parish Secretary', kind: 'REVIEW', quorum: 'ANY', optional: true, state: 'CURRENT',
      tasks: [{ id: 'T1', assignee: ref('M', 'Mary Secretary'), delegated_from: null, status: 'PENDING', is_escalation: false,
        due_at: null, acted_at: null, acted_by: null, comment: null }] },
    { index: 2, name: 'Parish Priest', kind: 'APPROVE', quorum: 'ANY', optional: false, state: 'UPCOMING', tasks: [] },
  ],
  actions: [
    { id: 1, action: 'SUBMIT', actor: ref('S1', 'John Submitter'), on_behalf_of: null, comment: null, cycle: 1, stage_name: 'President',
      prev_status: null, new_status: 'IN_PROGRESS', created_at: '2026-11-10T09:00:00' },
    { id: 2, action: 'APPROVE', actor: ref('P', 'Paul President'), on_behalf_of: null, comment: 'Good plan', cycle: 1, stage_name: 'President',
      prev_status: 'IN_PROGRESS', new_status: 'IN_PROGRESS', created_at: '2026-11-10T10:00:00' },
  ],
  my_task: 'T1', can_withdraw: false, can_resubmit: false, can_override: false, ...over,
});

describe('my approvals', () => {
  it('shows the pending count in the menu and bulk-approves selected tasks', async () => {
    signIn({ permissions: [] });
    let bulk: unknown = null;
    server.use(
      http.get(`${API}/workflow/tasks/summary`, () => HttpResponse.json({ pending: 2, overdue: 0 })),
      http.get(`${API}/workflow/tasks`, () =>
        HttpResponse.json({ items: [task('A', 'Youth retreat'), task('B', 'Choir festival')], page: 1, size: 25, total: 2, pages: 1 })),
      http.post(`${API}/workflow/tasks/bulk-approve`, async ({ request }) => {
        bulk = await request.json();
        return HttpResponse.json({ approved: ['A', 'B'], failed: [] });
      }),
    );
    renderRoutes(routes, '/approvals');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(await within(nav).findByLabelText('2 approvals waiting')).toBeInTheDocument();
    expect(await screen.findByText('Choir festival')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve 2 selected' }));
    await waitFor(() => expect(bulk).toEqual({ task_ids: ['A', 'B'] }));
    expect(await screen.findByText('2 records approved')).toBeInTheDocument();
  });
});

describe('approval detail', () => {
  it('shows the timeline and requires a comment to return', async () => {
    signIn({ permissions: [] });
    let body: Record<string, unknown> = {};
    server.use(
      http.get(`${API}/workflow/instances/I1`, () => HttpResponse.json(detail())),
      http.post(`${API}/workflow/tasks/T1/act`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(detail({ status: 'REWORK', my_task: null }));
      }),
    );
    renderRoutes(routes, '/approvals/I1');
    const stages = await screen.findByRole('list', { name: 'Stages' });
    expect(within(stages).getByText('Paul President')).toBeInTheDocument();
    expect(within(stages).getByText('“Good plan”')).toBeInTheDocument();
    expect(within(stages).getByText('Waiting')).toBeInTheDocument();
    const ret = screen.getByRole('button', { name: 'Return for rework' });
    expect(ret).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Comment'), { target: { value: 'Add the budget' } });
    fireEvent.click(ret);
    await waitFor(() => expect(body).toMatchObject({ action: 'RETURN', comment: 'Add the budget' }));
    expect(await screen.findByText('Returned for rework')).toBeInTheDocument();
  });

  it('lets the submitter resubmit after rework', async () => {
    signIn({ permissions: [] });
    let called = false;
    server.use(
      http.get(`${API}/workflow/instances/I1`, () => HttpResponse.json(detail({ status: 'REWORK', my_task: null, can_resubmit: true, can_withdraw: true }))),
      http.post(`${API}/workflow/instances/I1/resubmit`, () => {
        called = true;
        return HttpResponse.json(detail({ cycle: 2 }));
      }),
    );
    renderRoutes(routes, '/approvals/I1');
    expect(await screen.findByText(/A reviewer asked for changes/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Resubmit' }));
    await waitFor(() => expect(called).toBe(true));
  });
});

describe('workflow designer', () => {
  const definition = {
    id: 'D1', code: 'ACTIVITY_DEFAULT', version: 1, is_latest: true, is_active: true, entity_type: 'ACTIVITY', entity_label: 'Activity',
    name: 'Activity approval', description: null, priority: 0, conditions: {}, is_system: true, running: 1,
    created_at: '2026-11-01T00:00:00', updated_at: '2026-11-01T00:00:00',
    stages: [{ key: 'parish_priest', name: 'Parish Priest', kind: 'APPROVE', quorum: 'ANY', optional: false, sla_hours: 120,
      allow_delegation: true, escalate_to: [],
      assignees: [{ type: 'ROLE', role: 'PARISH_PRIEST', scope: 'PARISH', position: null, user_id: null, label: 'Parish Priest (parish-wide)' }] }],
  };
  function handlers(onPut: (b: Record<string, unknown>) => void) {
    server.use(
      http.get(`${API}/workflow/definitions`, ({ request }) =>
        HttpResponse.json(new URL(request.url).searchParams.get('code') ? [definition] : [definition])),
      http.get(`${API}/workflow/definitions/D1`, () => HttpResponse.json(definition)),
      http.get(`${API}/workflow/entity-types`, () => HttpResponse.json([{ code: 'ACTIVITY', label: 'Activity', has_amount: false, has_category: true, definitions: 1 }])),
      http.get(`${API}/roles`, () => HttpResponse.json([{ id: 'R1', code: 'PARISH_PRIEST', name: 'Parish Priest' }, { id: 'R2', code: 'PARISH_SECRETARY', name: 'Parish Secretary' }])),
      http.get(`${API}/org-unit-types`, () => HttpResponse.json([])),
      http.get(`${API}/org-units`, () => HttpResponse.json({ items: [], page: 1, size: 20, total: 0, pages: 0 })),
      http.put(`${API}/workflow/definitions/D1`, async ({ request }) => {
        const b = (await request.json()) as Record<string, unknown>;
        onPut(b);
        return HttpResponse.json({ ...definition, id: 'D2', version: 2 });
      }),
      http.get(`${API}/workflow/definitions/D2`, () => HttpResponse.json({ ...definition, id: 'D2', version: 2 })),
    );
  }

  it('lists workflows by record type', async () => {
    signIn({ permissions: ['workflow.view', 'workflow.manage'] });
    handlers(() => {});
    renderRoutes(routes, '/admin/workflows');
    const section = await screen.findByRole('region', { name: 'Activity' });
    expect(within(section).getByText('Activity approval')).toBeInTheDocument();
    expect(within(section).getByText('1 approval in progress')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Notice' })).toHaveTextContent(/No workflow/);
  });

  it('adds a stage and saves a new version without display labels', async () => {
    signIn({ permissions: ['workflow.view', 'workflow.manage', 'role.view', 'org_unit.view'] });
    let put: Record<string, unknown> = {};
    handlers((b) => { put = b; });
    renderRoutes(routes, '/admin/workflows/D1');
    expect(await screen.findByText(/1 approval in progress uses this workflow/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add stage' }));
    const stage2 = screen.getByRole('region', { name: 'Stage 2' });
    fireEvent.change(within(stage2).getByLabelText(/Stage name/), { target: { value: 'Parish Secretary' } });
    fireEvent.click(within(stage2).getByRole('button', { name: 'Move up' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save as version 2' }));
    await waitFor(() => expect(put.stages).toBeDefined());
    const stages = put.stages as { name: string; assignees: Record<string, unknown>[] }[];
    expect(stages.map((s) => s.name)).toEqual(['Parish Secretary', 'Parish Priest']);
    expect(stages[1]!.assignees[0]).not.toHaveProperty('label');
    expect(await screen.findByText('Saved as version 2')).toBeInTheDocument();
  }, 20_000);
});
