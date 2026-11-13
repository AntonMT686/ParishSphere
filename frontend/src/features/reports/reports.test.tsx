import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

const catalog = [
  { code: 'donation_report', group: 'FINANCE', title: 'Donation report', description: 'Every approved donation.', can_export: true,
    params: [{ name: 'date_range', options: [], default: null }] },
  { code: 'member_register', group: 'PARISH', title: 'Member register', description: 'Members.', can_export: false,
    params: [{ name: 'status', options: [{ value: 'ACTIVE', label: 'Active' }, { value: 'DECEASED', label: 'Deceased' }], default: 'ACTIVE' }] },
];

describe('reports', () => {
  it('groups the catalog the user may run', async () => {
    signIn({ permissions: ['report.view'] });
    server.use(http.get(`${API}/reports`, () => HttpResponse.json(catalog)));
    renderRoutes(routes, '/reports');
    expect(await screen.findByRole('heading', { name: 'Finance' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Parish registers' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Donation report/ })).toHaveAttribute('href', '/reports/donation_report');
    expect(screen.queryByRole('heading', { name: 'Management' })).not.toBeInTheDocument();
  });

  it('runs a report with filters, shows totals and offers export', async () => {
    signIn({ permissions: ['report.view', 'report.export'] });
    const calls: string[] = [];
    server.use(
      http.get(`${API}/reports`, () => HttpResponse.json(catalog)),
      http.get(`${API}/reports/donation_report`, ({ request }) => {
        calls.push(new URL(request.url).search);
        return HttpResponse.json({
          code: 'donation_report', title: 'Donation report', subtitle: '01 Apr 2026 – 13 Nov 2026 · 1 donations', note: null,
          columns: [{ key: 'date', header: 'Date', kind: 'date' }, { key: 'donor', header: 'Donor', kind: 'text' }, { key: 'amount', header: 'Amount ₹', kind: 'money' }],
          rows: [{ date: '2026-11-08', donor: 'Arokiasamy', amount: '5000.00' }],
          totals: { donor: 'Total', amount: '5000.00' }, total_rows: 1, truncated: false,
        });
      }),
    );
    renderRoutes(routes, '/reports/donation_report');
    const table = await screen.findByRole('table', { name: 'Donation report' });
    expect(within(table).getByText('Arokiasamy')).toBeInTheDocument();
    expect(within(table).getAllByText('₹5,000.00')).toHaveLength(2); // row + totals
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run report' }));
    await waitFor(() => expect(calls.at(-1)).toContain('date_from=2026-11-01'));
  });

  it('applies select defaults and hides export without permission', async () => {
    signIn({ permissions: ['report.view'] });
    let asked = '';
    server.use(
      http.get(`${API}/reports`, () => HttpResponse.json(catalog)),
      http.get(`${API}/reports/member_register`, ({ request }) => {
        asked = new URL(request.url).search;
        return HttpResponse.json({ code: 'member_register', title: 'Member register', subtitle: '0 members', note: null,
          columns: [{ key: 'name', header: 'Name', kind: 'text' }], rows: [], totals: null, total_rows: 0, truncated: false });
      }),
    );
    renderRoutes(routes, '/reports/member_register');
    expect(await screen.findByText('No records match the selected filters.')).toBeInTheDocument();
    expect(asked).toContain('status=ACTIVE');
    expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  });
});
