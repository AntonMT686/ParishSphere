import { act, fireEvent, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { useAuthStore } from '@/auth/authStore';
import { API, makeToken, server } from '@/test/server';
import { renderWithProviders, signIn } from '@/test/renderWithProviders';
import { IdleTimeoutDialog } from './IdleTimeoutDialog';

describe('IdleTimeoutDialog', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('warns two minutes before expiry and continues the session', async () => {
    signIn();
    useAuthStore.setState({ idleTimeoutSeconds: 130 });
    let refreshed = 0;
    server.use(
      http.post(`${API}/auth/refresh`, () => {
        refreshed += 1;
        return HttpResponse.json(makeToken(undefined, { idle_timeout_seconds: 130 }));
      }),
    );
    renderWithProviders(<IdleTimeoutDialog />);
    expect(screen.queryByText('Your session is about to expire')).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12_000);
    });
    expect(await screen.findByText('Your session is about to expire')).toBeInTheDocument();
    expect(screen.getByText(/signed out in 1:5\d/)).toBeInTheDocument();
    // Passive activity does not dismiss the warning – only an explicit choice does.
    fireEvent.mouseMove(window);
    fireEvent.click(screen.getByRole('button', { name: 'Continue session' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    expect(refreshed).toBe(1);
    expect(screen.queryByText('Your session is about to expire')).not.toBeInTheDocument();
  });

  it('signs the user out when the idle limit is reached', async () => {
    signIn();
    useAuthStore.setState({ idleTimeoutSeconds: 5 });
    let loggedOut = 0;
    server.use(http.post(`${API}/auth/logout`, () => { loggedOut += 1; return new HttpResponse(null, { status: 204 }); }));
    renderWithProviders(<IdleTimeoutDialog />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_000);
    });
    expect(useAuthStore.getState()).toMatchObject({ status: 'anonymous', endReason: 'timeout' });
    expect(loggedOut).toBe(1);
  });
});
