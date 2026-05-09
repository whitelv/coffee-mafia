const fs   = require('fs');
const path = require('path');

// Load utils.js first (api.js calls showNetworkToast → showToast)
eval(fs.readFileSync(path.join(__dirname, '../js/utils.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '../js/api.js'),   'utf8'));

// ── fetchWithNetworkRetry ───────────────────────────────────────────────────

describe('fetchWithNetworkRetry', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });
  afterEach(() => {
    jest.useRealTimers();
    global.fetch = undefined;
  });

  test('returns response on first success', async () => {
    const mockResponse = { ok: true, status: 200 };
    global.fetch = jest.fn().mockResolvedValue(mockResponse);
    const result = await fetchWithNetworkRetry('https://example.com/api', {});
    expect(result).toBe(mockResponse);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test('retries once after network failure and succeeds', async () => {
    const mockResponse = { ok: true, status: 200 };
    global.fetch = jest.fn()
      .mockRejectedValueOnce(new TypeError('Network error'))
      .mockResolvedValueOnce(mockResponse);

    const promise = fetchWithNetworkRetry('https://example.com/api', {});
    await jest.runAllTimersAsync();
    const result = await promise;
    expect(result).toBe(mockResponse);
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  test('throws after two consecutive failures', async () => {
    global.fetch = jest.fn()
      .mockImplementationOnce(() => Promise.reject(new TypeError('Network error')))
      .mockImplementationOnce(() => Promise.reject(new TypeError('Network error')));
    const promise = fetchWithNetworkRetry('https://example.com/api', {});
    // Attach catch immediately so the eventual rejection is never unhandled
    const caught = promise.catch(err => err);
    // advanceTimersByTimeAsync runs timers AND drains microtasks between each tick,
    // so delay(2000) is registered (in a microtask) and then fired correctly.
    await jest.advanceTimersByTimeAsync(3000);
    const err = await caught;
    expect(err.message).toBe('Network error');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});

// ── apiFetch ────────────────────────────────────────────────────────────────

describe('apiFetch', () => {
  afterEach(() => {
    global.fetch = undefined;
    sessionStorage.clear();
  });

  function mockFetch(status, body) {
    global.fetch = jest.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    });
  }

  test('sends Content-Type: application/json header', async () => {
    mockFetch(200, { ok: true, data: {} });
    await apiFetch('/api/recipes');
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['Content-Type']).toBe('application/json');
  });

  test('attaches Bearer token when token is in sessionStorage', async () => {
    sessionStorage.setItem('token', 'my-jwt-token');
    mockFetch(200, { ok: true, data: { name: 'Espresso' } });
    await apiFetch('/api/recipes');
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['Authorization']).toBe('Bearer my-jwt-token');
  });

  test('does not attach Authorization header when no token', async () => {
    mockFetch(200, { ok: true, data: [] });
    await apiFetch('/api/recipes');
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers['Authorization']).toBeUndefined();
  });

  test('builds correct URL with BASE_URL prefix', async () => {
    mockFetch(200, { ok: true, data: null });
    await apiFetch('/api/sessions/current');
    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe('https://coffee-mafia.onrender.com/api/sessions/current');
  });

  test('returns data.data for responses with ok flag', async () => {
    const payload = { id: '1', name: 'Latte' };
    mockFetch(200, { ok: true, data: payload });
    const result = await apiFetch('/api/recipes/1');
    expect(result).toEqual(payload);
  });

  test('returns raw body for responses without ok flag', async () => {
    const rawBody = { token: 'abc', user: { name: 'Alice' } };
    mockFetch(200, rawBody);
    const result = await apiFetch('/auth/token');
    expect(result).toEqual(rawBody);
  });

  test('throws on non-ok response', async () => {
    mockFetch(404, { error: 'not found' });
    await expect(apiFetch('/api/recipes/bad')).rejects.toThrow('not found');
  });

  test('throws with detail when error field is missing', async () => {
    mockFetch(500, { detail: 'Internal Server Error' });
    await expect(apiFetch('/api/boom')).rejects.toThrow('Internal Server Error');
  });

  test('throws generic message when no error or detail', async () => {
    mockFetch(503, {});
    await expect(apiFetch('/api/boom')).rejects.toThrow('HTTP 503');
  });
});

// ── URL builder helpers ─────────────────────────────────────────────────────

describe('API URL builders', () => {
  afterEach(() => { global.fetch = undefined; });

  function captureFetch() {
    const calls = [];
    global.fetch = jest.fn((url) => {
      calls.push(url);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ok: true, data: null }),
      });
    });
    return calls;
  }

  test('getRecipes calls /api/recipes', async () => {
    const calls = captureFetch();
    await getRecipes();
    expect(calls[0]).toContain('/api/recipes');
  });

  test('getRecipe calls /api/recipes/:id', async () => {
    const calls = captureFetch();
    await getRecipe('abc123');
    expect(calls[0]).toContain('/api/recipes/abc123');
  });

  test('getMyHistory defaults to page=1 limit=20', async () => {
    const calls = captureFetch();
    await getMyHistory();
    expect(calls[0]).toContain('/api/history/me?page=1&limit=20');
  });

  test('getMyHistory accepts custom page/limit', async () => {
    const calls = captureFetch();
    await getMyHistory(2, 10);
    expect(calls[0]).toContain('page=2&limit=10');
  });

  test('getAllHistory without user_id has no user_id param', async () => {
    const calls = captureFetch();
    await getAllHistory();
    expect(calls[0]).not.toContain('user_id');
  });

  test('getAllHistory with user_id appends it', async () => {
    const calls = captureFetch();
    await getAllHistory(1, 20, 'u42');
    expect(calls[0]).toContain('user_id=u42');
  });

  test('deleteRecipe sends DELETE to /api/recipes/:id', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({ ok: true, data: null }),
    });
    await deleteRecipe('r1');
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.method).toBe('DELETE');
  });

  test('dropSession calls current/drop with POST', async () => {
    const calls = [];
    global.fetch = jest.fn((url, opts) => {
      calls.push({ url, opts });
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ ok: true, data: null }),
      });
    });
    await dropSession();
    expect(calls[0].url).toContain('/api/sessions/current/drop');
    expect(calls[0].opts.method).toBe('POST');
  });
});
