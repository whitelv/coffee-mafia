const fs   = require('fs');
const path = require('path');

// ── Mock WebSocket ──────────────────────────────────────────────────────────

class MockWebSocket {
  constructor(url) {
    this.url        = url;
    this.readyState = MockWebSocket.CONNECTING;
    this.sent       = [];
    MockWebSocket._last = this;
  }

  send(data) { this.sent.push(data); }
  close()    { this.readyState = MockWebSocket.CLOSED; if (this.onclose) this.onclose({ code: 1000 }); }

  _open()        { this.readyState = MockWebSocket.OPEN; this.onopen && this.onopen(); }
  _message(data) { this.onmessage && this.onmessage({ data: JSON.stringify(data) }); }
  _close(code)   { this.readyState = MockWebSocket.CLOSED; this.onclose && this.onclose({ code }); }
  _error(err)    { this.onerror && this.onerror(err); }
}
MockWebSocket.CONNECTING = 0;
MockWebSocket.OPEN       = 1;
MockWebSocket.CLOSED     = 3;

global.WebSocket = MockWebSocket;

// Load ws.js and explicitly expose class on global (class declarations in eval
// are not automatically added to the global object)
const wsCode = fs.readFileSync(path.join(__dirname, '../js/ws.js'), 'utf8');
eval(wsCode + '\nglobal.CoffeeWebSocket = CoffeeWebSocket;');

// ── Construction ────────────────────────────────────────────────────────────

describe('CoffeeWebSocket construction', () => {
  test('stores sessionId, token, handlers', () => {
    const handlers = { onWeightUpdate: jest.fn() };
    const cws = new CoffeeWebSocket('sess1', 'tok1', handlers);
    expect(cws.sessionId).toBe('sess1');
    expect(cws.token).toBe('tok1');
    expect(cws.handlers).toBe(handlers);
  });

  test('defaults _closed to false', () => {
    const cws = new CoffeeWebSocket('s', 't', {});
    expect(cws._closed).toBe(false);
  });
});

// ── connect() — URL building ────────────────────────────────────────────────

describe('CoffeeWebSocket connect()', () => {
  test('replaces http with ws in BASE_URL', () => {
    const cws = new CoffeeWebSocket('abc', 'mytoken', {});
    cws.connect();
    expect(MockWebSocket._last.url).toContain('wss://');
  });

  test('includes session id in URL path', () => {
    const cws = new CoffeeWebSocket('mysession', 'tok', {});
    cws.connect();
    expect(MockWebSocket._last.url).toContain('/ws/browser/mysession');
  });

  test('includes encoded token as query param', () => {
    const cws = new CoffeeWebSocket('s', 'tok+special', {});
    cws.connect();
    expect(MockWebSocket._last.url).toContain('token=tok%2Bspecial');
  });

  test('sets _closed=false on connect', () => {
    const cws = new CoffeeWebSocket('s', 't', {});
    cws._closed = true;
    cws.connect();
    expect(cws._closed).toBe(false);
  });
});

// ── onmessage event routing ─────────────────────────────────────────────────

describe('CoffeeWebSocket onmessage routing', () => {
  let handlers, cws, ws;

  beforeEach(() => {
    handlers = {
      onWeightUpdate:     jest.fn(),
      onWeightStable:     jest.fn(),
      onStepAdvance:      jest.fn(),
      onSessionComplete:  jest.fn(),
      onSessionAbandoned: jest.fn(),
      onEspDisconnected:  jest.fn(),
      onEspReconnected:   jest.fn(),
      onTareDone:         jest.fn(),
      onSessionState:     jest.fn(),
    };
    cws = new CoffeeWebSocket('sess', 'token', handlers);
    cws.connect();
    ws = MockWebSocket._last;
    ws._open();
  });

  test('weight_update calls onWeightUpdate with value and stable', () => {
    ws._message({ event: 'weight_update', value: 150.5, stable: false });
    expect(handlers.onWeightUpdate).toHaveBeenCalledWith(150.5, false);
  });

  test('weight_stable calls onWeightStable with value', () => {
    ws._message({ event: 'weight_stable', value: 200.0 });
    expect(handlers.onWeightStable).toHaveBeenCalledWith(200.0);
  });

  test('step_advance calls onStepAdvance with index and step', () => {
    const step = { type: 'timer', label: 'Wait' };
    ws._message({ event: 'step_advance', step_index: 2, step });
    expect(handlers.onStepAdvance).toHaveBeenCalledWith(2, step);
  });

  test('session_complete calls onSessionComplete', () => {
    ws._message({ event: 'session_complete' });
    expect(handlers.onSessionComplete).toHaveBeenCalled();
  });

  test('session_abandoned calls onSessionAbandoned', () => {
    ws._message({ event: 'session_abandoned' });
    expect(handlers.onSessionAbandoned).toHaveBeenCalled();
  });

  test('esp_disconnected calls onEspDisconnected', () => {
    ws._message({ event: 'esp_disconnected' });
    expect(handlers.onEspDisconnected).toHaveBeenCalled();
  });

  test('esp_reconnected calls onEspReconnected', () => {
    ws._message({ event: 'esp_reconnected' });
    expect(handlers.onEspReconnected).toHaveBeenCalled();
  });

  test('tare_done calls onTareDone', () => {
    ws._message({ event: 'tare_done' });
    expect(handlers.onTareDone).toHaveBeenCalled();
  });

  test('session_state calls onSessionState with the full message', () => {
    const msg = { event: 'session_state', current_step: 1, recipe: {} };
    ws._message(msg);
    expect(handlers.onSessionState).toHaveBeenCalledWith(msg);
  });

  test('pong does not call any handler', () => {
    ws._message({ event: 'pong' });
    Object.values(handlers).forEach(fn => expect(fn).not.toHaveBeenCalled());
  });

  test('unknown event does not throw', () => {
    expect(() => ws._message({ event: 'unknown_event' })).not.toThrow();
  });

  test('malformed JSON is silently ignored', () => {
    expect(() => {
      cws._ws.onmessage({ data: 'not json{{{{' });
    }).not.toThrow();
    Object.values(handlers).forEach(fn => expect(fn).not.toHaveBeenCalled());
  });
});

// ── send() ──────────────────────────────────────────────────────────────────

describe('CoffeeWebSocket send()', () => {
  test('sends JSON when socket is OPEN', () => {
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    const ws = MockWebSocket._last;
    ws.readyState = MockWebSocket.OPEN;
    cws.send('next_step', { foo: 'bar' });
    expect(ws.sent.length).toBe(1);
    expect(JSON.parse(ws.sent[0])).toEqual({ event: 'next_step', foo: 'bar' });
  });

  test('does nothing when socket is not OPEN', () => {
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    const ws = MockWebSocket._last;
    ws.readyState = MockWebSocket.CONNECTING;
    cws.send('next_step');
    expect(ws.sent.length).toBe(0);
  });

  test('does nothing when _ws is null', () => {
    const cws = new CoffeeWebSocket('s', 't', {});
    expect(() => cws.send('next_step')).not.toThrow();
  });
});

// ── disconnect() ────────────────────────────────────────────────────────────

describe('CoffeeWebSocket disconnect()', () => {
  test('sets _closed=true and nulls _ws', () => {
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    cws.disconnect();
    expect(cws._closed).toBe(true);
    expect(cws._ws).toBeNull();
  });

  test('clears retry timer', () => {
    jest.useFakeTimers();
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    cws._retryTimer = setTimeout(() => {}, 9999);
    cws.disconnect();
    expect(jest.getTimerCount()).toBe(0);
    jest.useRealTimers();
  });
});

// ── close code handling ─────────────────────────────────────────────────────

describe('CoffeeWebSocket close-code handling', () => {
  beforeEach(() => {
    delete window.location;
    window.location = { href: '' };
  });

  test('code 4001 redirects to /index.html and clears sessionStorage', () => {
    sessionStorage.setItem('token', 'x');
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    MockWebSocket._last._close(4001);
    expect(window.location.href).toBe('/index.html');
    expect(sessionStorage.getItem('token')).toBeNull();
  });

  test('code 4004 redirects to /select.html', () => {
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    MockWebSocket._last._close(4004);
    expect(window.location.href).toBe('/select.html');
  });

  test('unexpected close schedules reconnect when not manually closed', () => {
    jest.useFakeTimers();
    const connectSpy = jest.spyOn(CoffeeWebSocket.prototype, 'connect');
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    connectSpy.mockClear();
    MockWebSocket._last._close(1006);
    jest.runAllTimers();
    expect(connectSpy).toHaveBeenCalled();
    jest.useRealTimers();
    connectSpy.mockRestore();
  });

  test('no reconnect when manually disconnected', () => {
    jest.useFakeTimers();
    const connectSpy = jest.spyOn(CoffeeWebSocket.prototype, 'connect');
    const cws = new CoffeeWebSocket('s', 't', {});
    cws.connect();
    cws.disconnect();
    connectSpy.mockClear();
    jest.runAllTimers();
    expect(connectSpy).not.toHaveBeenCalled();
    jest.useRealTimers();
    connectSpy.mockRestore();
  });
});
