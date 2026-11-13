import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { routes } from '@/app/router';
import { renderRoutes, signIn } from '@/test/renderWithProviders';
import { API, server } from '@/test/server';

const result = {
  q: 'arok',
  groups: [
    { key: 'families', total: 2, more_link: '/families?q=arok', hits: [
      { id: 'F1', title: 'Arokiasamy', code: 'FAM000001', status: 'ACTIVE', subtitle: 'St. Joseph Anbiyam', link: '/families/F1' },
      { id: 'F2', title: 'Arokiaraj', code: 'FAM000002', status: 'ACTIVE', subtitle: 'St. Mary Anbiyam', link: '/families/F2' },
    ] },
    { key: 'members', total: 1, more_link: null, hits: [
      { id: 'M1', title: 'John Arokiasamy', code: 'MEM000001', status: 'ACTIVE', subtitle: 'Arokiasamy · FAM000001', link: '/families/F1?member=M1' },
    ] },
  ],
};

describe('global search', () => {
  it('shows grouped results and opens one with the keyboard', async () => {
    signIn({ permissions: ['family.view', 'member.view'] });
    let asked = '';
    let opened = '';
    server.use(
      http.get(`${API}/search`, ({ request }) => { asked = new URL(request.url).searchParams.get('q') ?? ''; return HttpResponse.json(result); }),
      http.get(`${API}/dashboard`, () => HttpResponse.json({ approvals: { pending: 0, overdue: 0, finance: 0, by_type: [], items: [] }, events: [] })),
      http.get(`${API}/families/:id`, ({ params }) => { opened = String(params.id); return HttpResponse.json({}, { status: 404 }); }),
      http.get(`${API}/families/:id/history`, () => HttpResponse.json([])),
    );
    renderRoutes(routes, '/');
    const box = await screen.findByRole('combobox', { name: 'Search…' });
    fireEvent.change(box, { target: { value: 'arok' } });
    const list = await screen.findByRole('listbox', { name: 'Search results' });
    expect(asked).toBe('arok');
    expect(within(list).getByRole('group', { name: 'Families' })).toHaveTextContent('Arokiaraj');
    expect(within(list).getByRole('group', { name: 'Members' })).toHaveTextContent('John Arokiasamy');
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    expect(within(list).getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(box, { key: 'Enter' });
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
    await waitFor(() => expect(opened).toBe('F2'));
  }, 20_000);

  it('lists every group on the search page', async () => {
    signIn({ permissions: ['family.view', 'member.view'] });
    server.use(http.get(`${API}/search`, () => HttpResponse.json(result)));
    renderRoutes(routes, '/search?q=arok');
    expect(await screen.findByRole('heading', { name: 'Search' })).toBeInTheDocument();
    const fam = await screen.findByRole('list', { name: 'Families' });
    expect(within(fam).getByRole('link', { name: 'Arokiasamy' })).toHaveAttribute('href', '/families/F1');
    expect(screen.getByText('2 matches')).toBeInTheDocument();
  });
});
