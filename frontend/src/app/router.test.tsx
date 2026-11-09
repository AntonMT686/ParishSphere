import { fireEvent, screen } from '@testing-library/react';
import { renderRoutes } from '@/test/renderWithProviders';
import { routes } from './router';

vi.mock('@/api/tenant', () => ({
  useTenantBranding: () => ({
    data: { display_name: "St. Mary's Church", diocese_name: 'Chennai Diocese', primary_color: null, logo_url: null },
    isLoading: false,
    isError: false,
  }),
}));

describe('app routes', () => {
  it('renders the admin shell with navigation and dashboard', async () => {
    renderRoutes(routes, '/');
    expect(await screen.findByRole('heading', { name: /Welcome to St. Mary's Church/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getAllByText('Families').length).toBeGreaterThan(0);
  });

  it('renders scheduled module pages', async () => {
    renderRoutes(routes, '/finance/transactions');
    expect(await screen.findByText(/roadmap task T12/)).toBeInTheDocument();
  });

  it('renders the login page with parish code on localhost', async () => {
    renderRoutes(routes, '/login');
    expect(await screen.findByLabelText('Parish code')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });
});
