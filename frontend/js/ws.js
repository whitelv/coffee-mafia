class CoffeeWebSocket {
  constructor(sessionId, token, handlers) {
    this.sessionId = sessionId;
    this.token     = token;
    this.handlers  = handlers || {};
    this._ws       = null;
    this._closed   = false; // true when disconnect() called manually
    this._retryTimer = null;
  }

  connect() {
    this._closed = false;
    const wsBase = BASE_URL.replace(/^http/, 'ws');
    const url    = `${wsBase}/ws/browser/${this.sessionId}?token=${encodeURIComponent(this.token)}`;
    this._ws     = new WebSocket(url);

    this._ws.onopen = () => {
      console.log('[WS] Connected');
    };

    this._ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch { return; }
      const h = this.handlers;
      switch (msg.event) {
        case 'weight_update':    h.onWeightUpdate  && h.onWeightUpdate(msg.value, msg.stable); break;
        case 'weight_stable':    h.onWeightStable  && h.onWeightStable(msg.value);             break;
        case 'step_advance':     h.onStepAdvance   && h.onStepAdvance(msg.step_index, msg.step); break;
        case 'session_complete': h.onSessionComplete && h.onSessionComplete();                  break;
        case 'session_abandoned':h.onSessionAbandoned && h.onSessionAbandoned();               break;
        case 'esp_disconnected': h.onEspDisconnected && h.onEspDisconnected();                 break;
        case 'esp_reconnected':  h.onEspReconnected && h.onEspReconnected();                   break;
        case 'tare_done':        h.onTareDone      && h.onTareDone();                          break;
        case 'session_state':    h.onSessionState  && h.onSessionState(msg);                   break;
        case 'pong': break;
        default: console.log('[WS] Unknown event:', msg.event);
      }
    };

    this._ws.onclose = (evt) => {
      console.log('[WS] Closed', evt.code);
      if (evt.code === 4001) {
        // auth failure — token expired or invalid, go re-authenticate
        sessionStorage.clear();
        window.location.href = '/index.html';
        return;
      }
      if (evt.code === 4004) {
        // session not found — go pick a recipe
        sessionStorage.removeItem('session_id');
        window.location.href = '/select.html';
        return;
      }
      if (!this._closed) {
        // unexpected close — schedule reconnect
        this._retryTimer = setTimeout(() => this.connect(), 3000);
      }
    };

    this._ws.onerror = (err) => {
      console.error('[WS] Error', err);
    };
  }

  send(event, data = {}) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ event, ...data }));
    }
  }

  disconnect() {
    this._closed = true;
    clearTimeout(this._retryTimer);
    if (this._ws) { this._ws.close(); this._ws = null; }
  }
}
