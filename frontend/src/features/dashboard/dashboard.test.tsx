import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= RO;

const months = Array.from({ length: 12 }, (_, i) => ({
  key: `2026-${String(i + 1).padStart(2, '0')}`, income: i === 10 ? '25000.00' : '0.00', expense: i === 10 ? '8000.00' : '0.00',
}));
const priest = {
  approvals: {
    pending: 2, overdue: 1, finance: 1,
    by_type: [{ key: 'ACTIVITY', label: 'Activity', value: 1 }, { key: 'FIN_TRANSACTION', label: 'Finance entry', value: 1 }],
    items: [
      { title: 'Youth Society – Career Camp', entity_type: 'ACTIVITY', entity_label: 'Activity', stage: 'Parish Priest', link: '/activities/A1', amount: null, due_at: '2026-11-01T10:00:00', overdue: true },
      { title: 'TXN-2026-000045', entity_type: 'FIN_TRANSACTION', entity_label: 'Finance entry', stage: 'Parish Priest', link: '/finance/transactions/T1', amount: 62000, due_at: null, overdue: false },
    ],
  },
  people: {
    families: 1240, members: 4812, new_families_month: 12, pending_anbiyam: 3,
    by_anbiyam: [{ name: 'St. Joseph Anbiyam', families: 60, members: 230 }],
    age_bands: [{ key: '0–12', label: '0–12', value: 800 }, { key: '60+', label: '60+', value: 500 }],
    gender: [{ key: 'M', label: 'M', value: 2400 }, { key: 'F', label: 'F', value: 2412 }],
  },
  organisations: [
    { code: 'ANBIYAM', name: 'Anbiyams', units: 24, members: 1200, member_kind: 'FAMILY' },
    { code: 'SOCIETY', name: 'Societies', units: 9, members: 310, member_kind: 'MEMBER' },
  ],
  finance: {
    fy_label: 'FY 2026–27', months, income_by_category: [{ name: 'Donations', amount: '15000.00' }],
    expense_by_category: [{ name: 'Charity', amount: '8000.00' }], donations_month: '15000.00', donations_fy: '15000.00',
    pending_entries: 3, periods: [{ key: '2026-10', status: 'RELEASED' }, { key: '2026-11', status: 'OPEN' }],
  },
  activities: { upcoming: [{ id: 'A2', title: 'Parish feast', date: '2026-12-08', org_unit: null, status: 'APPROVED' }], recent: [], awaiting_report: 2, in_review: 1,
    by_unit: [{ name: 'Youth Society', completed: 4, planned: 2 }] },
  meetings: { upcoming: 3, minutes_in_review: 1 },
  events: [{ id: 'A2', title: 'Parish feast', date: '2026-12-08', org_unit: null, status: 'APPROVED' }],
  me: null,
};

describe('dashboard', () => {
  it('shows the Parish Priest live numbers, queues and charts', async () => {
    signIn({ permissions: ['family.view', 'member.view', 'org_unit.view', 'finance.view', 'finance_period.view', 'activity.view', 'meeting.view'] });
    server.use(
      http.get(`${API}/dashboard`, () => HttpResponse.json(priest)),
      http.get(`${API}/finance/summary`, () => HttpResponse.json({ month: 'November 2026', income: '25000.00', expense: '8000.00', fy_label: 'FY 2026–27',
        fy_income: '25000.00', fy_expense: '8000.00', pending_entries: 3, balance: '40000.00', last_released: 'October 2026' })),
      http.get(`${API}/org-unit-types`, () => HttpResponse.json([])),
      http.get(`${API}/meetings`, () => HttpResponse.json({ items: [], page: 1, size: 5, total: 0, pages: 0 })),
    );
    renderRoutes(routes, '/');
    expect(await screen.findByText('1,240')).toBeInTheDocument();
    expect(screen.getByText('12 new this month')).toBeInTheDocument();
    expect(screen.getAllByText('Anbiyams').length).toBe(2); // stat card + organisations card use the configured type name
    const approvals = screen.getByRole('list', { name: 'My approvals' });
    expect(within(approvals).getByText('Youth Society – Career Camp')).toBeInTheDocument();
    expect(within(approvals).getByText(/₹62,000\.00/)).toBeInTheDocument();
    // Charts carry an accessible table with the same numbers.
    const ie = screen.getByRole('table', { name: 'Income vs expense' });
    expect(within(ie).getByText('₹25,000.00')).toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: 'Families by Anbiyam' })).getByText('St. Joseph Anbiyam')).toBeInTheDocument();
    expect(screen.getByText('Activities in review')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Monthly statements' })).getByText('Released')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Upcoming events' })).toHaveTextContent('Parish feast');
  }, 20_000);

  it('shows a parishioner their family, donations and parish events', async () => {
    signIn({ permissions: ['notice.view'] });
    server.use(http.get(`${API}/dashboard`, () => HttpResponse.json({
      approvals: { pending: 0, overdue: 0, finance: 0, by_type: [], items: [] },
      events: [{ id: 'A2', title: 'Parish feast', date: '2026-12-08', org_unit: null, status: 'APPROVED' }],
      me: { member_code: 'MEM-000001', name: 'John Arokiasamy', family: { id: 'F1', name: 'Arokiasamy' }, family_code: 'FAM-000001',
        anbiyam: 'St. Joseph Anbiyam', household: [{ name: 'John Arokiasamy', relationship: 'HEAD', age: 45 }, { name: 'Rita', relationship: 'SPOUSE', age: 40 }],
        memberships: ['Youth Society'], donations: [{ date: '2026-11-08', category: 'Donations', amount: '5000.00', code: 'TXN-1' }], donations_fy: '5000.00' },
    })));
    renderRoutes(routes, '/');
    expect(await screen.findByText('My family')).toBeInTheDocument();
    expect(screen.getAllByText('St. Joseph Anbiyam').length).toBeGreaterThan(0);
    expect(within(screen.getByRole('list', { name: 'Household' })).getByText('Spouse · 40 yrs')).toBeInTheDocument();
    expect(screen.getByText('₹5,000.00 this financial year')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Upcoming events' })).toHaveTextContent('Parish feast');
    expect(screen.queryByText('Pending approvals')).not.toBeInTheDocument(); // no staff widgets
    expect(screen.queryByText('My approvals')).not.toBeInTheDocument();
  }, 20_000);
});
