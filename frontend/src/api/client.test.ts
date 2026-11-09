import { http, HttpResponse } from 'msw';
import { useAuthStore } from '@/auth/authStore';
import { API, makeToken, server } from '@/test/server';
import { api, ApiError, refreshSession, setAccessToken } from './client';

describe('api client', () => {
  it('maps the error envelope to ApiError', async () => {
    server.use(http.get(`${API}/x`, () => HttpResponse.json({ error: { code: 'NOT_FOUND', message: 'nope', details: [] } }, { status: 404 })));
    await expect(api.get('/x')).rejects.toMatchObject({ status: 404, code: 'NOT_FOUND' });
  });

  it('sends the CSRF cookie as a header on unsafe requests and the bearer token', async () => {
    document.cookie = 'ps_csrf=csrf-123; path=/';
    setAccessToken('tok', 900);
    let seen: Record<string, string | null> = {};
    server.use(
      http.post(`${API}/echo`, ({ request }) => {
        seen = { csrf: request.headers.get('x-csrf-token'), auth: request.headers.get('authorization') };
        return HttpResponse.json({});
      }),
    );
    await api.post('/echo');
    expect(seen).toEqual({ csrf: 'csrf-123', auth: 'Bearer tok' });
  });

  it('refreshes once on TOKEN_EXPIRED and retries concurrent requests with the new token', async () => {
    setAccessToken('old', 900);
    let refreshes = 0;
    server.use(
      http.post(`${API}/auth/refresh`, async () => {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 20));
        return HttpResponse.json(makeToken(undefined, { access_token: 'new' }));
      }),
      http.get(`${API}/data/:n`, ({ request, params }) =>
        request.headers.get('authorization') === 'Bearer new'
          ? HttpResponse.json({ n: params.n })
          : HttpResponse.json({ error: { code: 'TOKEN_EXPIRED', message: 'expired', details: [] } }, { status: 401 }),
      ),
    );
    const results = await Promise.all([api.get('/data/1'), api.get('/data/2'), api.get('/data/3')]);
    expect(results.map((r) => r.data.n)).toEqual(['1', '2', '3']);
    expect(refreshes).toBe(1);
    expect(useAuthStore.getState().status).toBe('authenticated');
  });

  it('signs the user out when the server reports the session expired', async () => {
    useAuthStore.setState({ status: 'authenticated' });
    server.use(
      http.get(`${API}/data`, () =>
        HttpResponse.json({ error: { code: 'SESSION_EXPIRED', message: 'idle', details: [] } }, { status: 401 }),
      ),
    );
    await expect(api.get('/data')).rejects.toBeInstanceOf(ApiError);
    expect(useAuthStore.getState()).toMatchObject({ status: 'anonymous', endReason: 'timeout' });
  });

  it('shares one in-flight refresh', async () => {
    let calls = 0;
    server.use(
      http.post(`${API}/auth/refresh`, () => {
        calls += 1;
        return HttpResponse.json(makeToken());
      }),
    );
    await Promise.all([refreshSession(), refreshSession()]);
    expect(calls).toBe(1);
  });
});
