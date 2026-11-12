import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

const cash = { id: 'AC1', code: 'CASH', name: 'Parish cash', kind: 'CASH', org_unit: null, bank_name: null, account_number_masked: null,
  opening_balance: '1000.00', opening_date: '2026-01-01', is_active: true, balance: '12900.00', pending: 0 };
const youth = { ...cash, id: 'AC2', code: 'YOUTH', name: 'Youth cash', org_unit: { id: 'U1', name: 'Youth Society' }, balance: '320.00' };
const categories = [
  { id: 'C1', code: 'OFFERING', name: 'Offerings', name_local: null, kind: 'INCOME', sort_order: 10, is_active: true, is_system: true },
  { id: 'C2', code: 'CHARITY', name: 'Charity', name_local: null, kind: 'EXPENSE', sort_order: 20, is_active: true, is_system: true },
];
const txn = (over: object = {}) => ({
  id: 'T1', code: 'TXN-2026-000001', txn_date: '2026-11-08', kind: 'INCOME', category: { id: 'C1', name: 'Offerings' },
  account: { id: 'AC1', name: 'Parish cash' }, to_account: null, org_unit: null, amount: '2500.00', payment_method: 'CASH',
  description: 'Sunday collection', payer_payee: null, status: 'APPROVED', is_correction: false, reference_no: null, family: null,
  period: 'November 2026', period_status: 'OPEN', adjusts: null, corrections: [], entered_by: 'Peter Treasurer', reviewed_by: null,
  approved_by: 'Fr. Joseph', created_at: '2026-11-08T10:00:00', submitted_at: null, approved_at: '2026-11-08T12:00:00', approval_id: null,
  can_edit: false, can_submit: false, can_delete: false, can_correct: true, can_attach: true, ...over,
});
const summary = { month: 'November 2026', income: '2500.00', expense: '800.00', fy_label: 'FY 2026–27', fy_income: '9000.00',
  fy_expense: '3000.00', pending_entries: 1, balance: '13220.00', last_released: 'October 2026' };

function common() {
  server.use(
    http.get(`${API}/finance/accounts`, () => HttpResponse.json([cash, youth])),
    http.get(`${API}/finance/categories`, () => HttpResponse.json(categories)),
    http.get(`${API}/finance/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/org-units/mine`, () => HttpResponse.json({ parish: true, units: [{ id: 'U1', code: 'SOC-001', name: 'Youth Society', type_code: 'SOCIETY', type_name: 'Society' }] })),
    http.get(`${API}/finance/transactions/T1/attachments`, () => HttpResponse.json([])),
    http.get(`${API}/workflow/entities/:t/:id`, () => HttpResponse.json([])),
  );
}

describe('finance', () => {
  it('lists entries with the month summary and records a new income entry', async () => {
    signIn({ permissions: ['finance.view', 'finance.create', 'finance.view_summary'] });
    let body: Record<string, unknown> = {};
    common();
    server.use(
      http.get(`${API}/finance/transactions`, () => HttpResponse.json({ items: [txn()], page: 1, size: 25, total: 1, pages: 1 })),
      http.post(`${API}/finance/transactions`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(txn({ id: 'T2', status: 'DRAFT' }), { status: 201 });
      }),
      http.get(`${API}/finance/transactions/T2`, () => HttpResponse.json(txn({ id: 'T2', status: 'DRAFT' }))),
      http.get(`${API}/finance/transactions/T2/attachments`, () => HttpResponse.json([])),
    );
    renderRoutes(routes, '/finance/transactions');
    expect(await screen.findByText('Sunday collection')).toBeInTheDocument();
    expect(await screen.findByText('₹13,220.00')).toBeInTheDocument(); // balance card
    fireEvent.click(screen.getByRole('button', { name: 'New entry' }));
    const d = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(d).getByLabelText(/^Category/));
    fireEvent.click(await screen.findByRole('option', { name: 'Offerings' }));
    fireEvent.mouseDown(within(d).getByLabelText(/^Account/));
    const options = await screen.findAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['Parish cash']); // the society's cash box is not offered for parish entries
    fireEvent.click(options[0]!);
    fireEvent.change(within(d).getByLabelText(/^Amount/), { target: { value: '1500' } });
    fireEvent.change(within(d).getByLabelText(/^Particulars/), { target: { value: 'Feast day collection' } });
    fireEvent.click(within(d).getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(body.description).toBe('Feast day collection'));
    expect(body).toMatchObject({ kind: 'INCOME', category_id: 'C1', account_id: 'AC1', amount: '1500', org_unit_id: null, adjusts_transaction_id: null });
  }, 20_000);

  it('corrects an approved entry with a negative amount', async () => {
    signIn({ permissions: ['finance.view', 'finance.create'] });
    let body: Record<string, unknown> = {};
    common();
    server.use(
      http.get(`${API}/finance/transactions/T1`, () => HttpResponse.json(txn())),
      http.post(`${API}/finance/transactions`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(txn({ id: 'T3', amount: '-500.00', status: 'DRAFT', is_correction: true }), { status: 201 });
      }),
      http.get(`${API}/finance/transactions/T3`, () => HttpResponse.json(txn({ id: 'T3', amount: '-500.00', status: 'DRAFT' }))),
      http.get(`${API}/finance/transactions/T3/attachments`, () => HttpResponse.json([])),
    );
    renderRoutes(routes, '/finance/transactions/T1');
    expect(await screen.findByText('Peter Treasurer')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Correct this entry' }));
    const d = await screen.findByRole('dialog');
    expect(within(d).getByText(/references TXN-2026-000001/)).toBeInTheDocument();
    fireEvent.change(within(d).getByLabelText(/^Amount/), { target: { value: '-500' } });
    fireEvent.click(within(d).getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(body.adjusts_transaction_id).toBe('T1'));
    expect(body).toMatchObject({ amount: '-500', category_id: 'C1', kind: 'INCOME', description: 'Correction of TXN-2026-000001' });
  });

  it('shows an approved statement and releases it', async () => {
    signIn({ permissions: ['finance_period.view', 'finance_period.release'] });
    const period = (status: string) => ({
      id: 'P1', key: '2026-10', label: 'October 2026', status, live: false, submitted_at: null, approved_at: null,
      released_at: status === 'RELEASED' ? '2026-11-05T10:00:00' : null, released_by: status === 'RELEASED' ? 'Fr. Joseph' : null,
      revision_reason: null, approval_id: null, can_close: false, can_release: status === 'APPROVED', can_reopen: status === 'RELEASED',
      statements: [{ id: 'S1', version: 1, generated_at: '2026-11-04T10:00:00', generated_by: 'Fr. Joseph', released_at: null, is_current: true, revision_reason: null, sha256: 'ab'.repeat(32) }],
      snapshot: {
        label: 'October 2026', version: 1, transactions: 2,
        totals: { opening: '11200.00', income: '2500.00', expense: '800.00', surplus: '1700.00', closing: '12900.00' },
        accounts: [{ code: 'CASH', name: 'Parish cash', kind: 'CASH', org_unit: null, opening: '11200.00', income: '2500.00', expense: '800.00', transfers_in: '0.00', transfers_out: '0.00', closing: '12900.00' }],
        income_by_category: [{ code: 'OFFERING', name: 'Offerings', amount: '2500.00' }],
        expense_by_category: [{ code: 'CHARITY', name: 'Charity', amount: '800.00' }],
        organisations: [{ name: 'Parish', type: '', income: '2500.00', expense: '800.00', net: '1700.00' }], pending: [],
      },
    });
    let released = false;
    server.use(
      http.get(`${API}/finance/periods/2026-10`, () => HttpResponse.json(period(released ? 'RELEASED' : 'APPROVED'))),
      http.post(`${API}/finance/periods/2026-10/release`, () => { released = true; return HttpResponse.json(period('RELEASED')); }),
      http.get(`${API}/workflow/entities/:t/:id`, () => HttpResponse.json([])),
    );
    renderRoutes(routes, '/finance/statements/2026-10');
    expect(await screen.findByRole('heading', { name: 'Statement · October 2026' })).toBeInTheDocument();
    expect(screen.getAllByText('₹12,900.00').length).toBeGreaterThan(0);
    expect(within(screen.getByRole('table', { name: 'Income by category' })).getByText('Offerings')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Release statement' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));
    expect(await screen.findByText('Statement released')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Reopen for corrections' })).toBeInTheDocument();
  }, 20_000);

  it('creates an account for an organisation', async () => {
    signIn({ permissions: ['finance.view', 'finance.configure', 'org_unit.view'] });
    let body: Record<string, unknown> = {};
    common();
    server.use(
      http.get(`${API}/org-unit-types`, () => HttpResponse.json([])),
      http.get(`${API}/org-units`, () => HttpResponse.json({ items: [{ id: 'U1', code: 'SOC-001', name: 'Youth Society' }], page: 1, size: 20, total: 1, pages: 1 })),
      http.post(`${API}/finance/accounts`, async ({ request }) => { body = (await request.json()) as Record<string, unknown>; return HttpResponse.json(youth, { status: 201 }); }),
    );
    renderRoutes(routes, '/finance/accounts');
    expect(await screen.findByText('Youth cash')).toBeInTheDocument();
    expect(screen.getByText('₹13,220.00')).toBeInTheDocument(); // total of accounts in use
    fireEvent.click(screen.getByRole('button', { name: 'New account' }));
    const d = await screen.findByRole('dialog');
    fireEvent.change(within(d).getByLabelText(/^Code/), { target: { value: 'youth' } });
    fireEvent.change(within(d).getByLabelText(/^Name/), { target: { value: 'Youth cash' } });
    fireEvent.change(within(d).getByLabelText(/Held by organisation/), { target: { value: 'You' } });
    fireEvent.click(await screen.findByRole('option', { name: /Youth Society/ }));
    fireEvent.change(within(d).getByLabelText(/Opening balance/), { target: { value: '500' } });
    fireEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(body.code).toBe('YOUTH'));
    expect(body).toMatchObject({ kind: 'CASH', org_unit_id: 'U1', opening_balance: '500' });
  }, 20_000);
});
