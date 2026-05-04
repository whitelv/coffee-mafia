(async function () {
  const token     = sessionStorage.getItem('token');
  const sessionId = sessionStorage.getItem('session_id');
  if (!token) { window.location.href = '/index.html'; return; }
  if (!sessionId) { window.location.href = '/select.html'; return; }

  const user = JSON.parse(sessionStorage.getItem('user') || '{}');
  document.getElementById('nav-username').textContent = user.name || '';

  /* ── State ── */
  let recipe       = null;
  let steps        = [];
  let currentIndex = 0;
  let weightState  = 'IDLE'; // IDLE | STREAMING | STABLE
  let timerInterval = null;
  let timerRemaining = 0;
  let ws;

  /* ── DOM refs ── */
  const brewApp      = document.getElementById('brew-app');
  const stepCard     = document.getElementById('step-card');
  const stepList     = document.getElementById('step-list');
  const topName      = document.getElementById('top-recipe-name');
  const topCounter   = document.getElementById('top-step-counter');
  const topProgress  = document.getElementById('top-progress');
  const espOverlay   = document.getElementById('esp-overlay');
  const completeScr  = document.getElementById('complete-screen');
  const dropButton   = document.getElementById('btn-drop-session');
  let leavingSession = false;
  let dropRequested = false;

  /* ── Heartbeat ── */
  let heartbeatTimer = null;

  function showSessionToast(message) {
    if (typeof showToast === 'function') {
      showToast(message, 'error');
    }
  }

  function handleHeartbeatExpired() {
    if (leavingSession) return;
    leavingSession = true;
    clearInterval(heartbeatTimer);
    clearInterval(timerInterval);
    ws && ws.disconnect();
    sessionStorage.clear();
    showSessionToast('Session expired');
    setTimeout(() => {
      window.location.href = '/index.html';
    }, 2000);
  }

  heartbeatTimer = setInterval(async () => {
    const currentToken = sessionStorage.getItem('token');
    if (!currentToken) {
      handleHeartbeatExpired();
      return;
    }

    try {
      const res = await fetch(BASE_URL + '/api/sessions/current/heartbeat', {
        method: 'PATCH',
        headers: { Authorization: 'Bearer ' + currentToken },
      });
      if (res.status === 401) handleHeartbeatExpired();
    } catch {
      // Network heartbeat failures are non-blocking; normal API calls surface connectivity.
    }
  }, 20000);

  /* ── Ping-close beacon ── */
  window.addEventListener('beforeunload', () => {
    navigator.sendBeacon(BASE_URL + '/api/sessions/current/ping-close');
  });

  /* ── Step type helpers ── */
  const STEP_ICONS = { weight: '⚖️', timer: '⏱️', instruction: '📋' };

  function updateTopBar() {
    topName.textContent    = recipe ? recipe.name : '—';
    topCounter.textContent = `Step ${currentIndex + 1} of ${steps.length}`;
    const pct = steps.length > 1 ? (currentIndex / (steps.length - 1)) * 100 : 100;
    topProgress.style.width = pct + '%';
  }

  function renderSidebar() {
    stepList.innerHTML = '';
    steps.forEach((step, i) => {
      const div = document.createElement('div');
      div.className = 'sidebar-step' +
        (i === currentIndex ? ' current' : '') +
        (i < currentIndex   ? ' done'    : '');
      div.innerHTML = `
        <span class="sidebar-step-icon">${STEP_ICONS[step.type] || '•'}</span>
        <span>${step.label || step.type}</span>
        ${i < currentIndex ? '<span class="sidebar-check">✓</span>' : ''}`;
      stepList.appendChild(div);
    });
  }

  /* ── Render: instruction ── */
  function renderInstruction(step) {
    stepCard.innerHTML = `
      <div class="step-type-label">Instruction</div>
      <div class="step-label">${step.label || 'Instruction'}</div>
      <div class="step-instruction-text">${step.instruction_text || ''}</div>
      <button class="btn btn-primary" id="btn-done">✓ Mark as Done</button>`;
    document.getElementById('btn-done').addEventListener('click', () => {
      ws.send('next_step');
    });
    hideEspOverlay();
  }

  /* ── Render: timer ── */
  function renderTimer(step) {
    timerRemaining = step.target_value || 0;
    let started = false;

    stepCard.innerHTML = `
      <div class="step-type-label">Timer</div>
      <div class="step-label">${step.label || 'Timer'}</div>
      <div class="timer-display" id="timer-display">${formatTime(timerRemaining)}</div>
      <div style="display:flex; gap:0.75rem; flex-wrap:wrap;">
        <button class="btn btn-primary" id="btn-start-timer">▶ Start Timer</button>
        <button class="btn btn-primary" id="btn-next-step" disabled>Next Step →</button>
      </div>`;

    const display  = document.getElementById('timer-display');
    const btnStart = document.getElementById('btn-start-timer');
    const btnNext  = document.getElementById('btn-next-step');

    btnStart.addEventListener('click', () => {
      if (started) return;
      started = true;
      btnStart.disabled = true;
      clearInterval(timerInterval);
      timerInterval = setInterval(() => {
        timerRemaining--;
        display.textContent = formatTime(timerRemaining);
        if (timerRemaining <= 0) {
          clearInterval(timerInterval);
          generateBeep();
          btnNext.disabled = false;
          display.style.color = 'var(--success)';
        }
      }, 1000);
    });

    btnNext.addEventListener('click', () => {
      clearInterval(timerInterval);
      ws.send('next_step');
    });

    hideEspOverlay();
  }

  /* ── Render: weight ── */
  function renderWeight(step) {
    weightState = 'IDLE';
    const target = step.target_value || 0;

    stepCard.innerHTML = `
      <div class="step-type-label">Weight</div>
      <div class="step-label">${step.label || 'Weigh'}</div>
      <div class="weight-target-label">Target: <strong>${target}g</strong></div>
      <div class="weight-display" id="weight-val">--</div>
      <div class="weight-progress-wrap">
        <div class="progress-track">
          <div class="progress-bar" id="weight-bar" style="width:0%"></div>
        </div>
      </div>
      <div class="weight-controls">
        <button class="btn btn-primary" id="btn-start-weight">Start Weighing</button>
        <button class="btn btn-primary" id="btn-next-weight" style="display:none;">Next Step →</button>
        <button class="btn btn-sm btn-secondary tare-btn" id="btn-tare">Tare Scale</button>
      </div>`;

    document.getElementById('btn-start-weight').addEventListener('click', () => {
      weightState = 'STREAMING';
      document.getElementById('btn-start-weight').style.display = 'none';
      ws.send('start_weight', { target });
    });

    document.getElementById('btn-tare').addEventListener('click', () => {
      ws.send('tare_scale');
    });

    document.getElementById('btn-next-weight').addEventListener('click', () => {
      ws.send('next_step');
    });

    // Show overlay — weight step needs hardware
    showEspOverlay();
    // but immediately hide if WS is connected (overlay only for disconnect)
    // overlay will be managed by esp_disconnected / esp_reconnected events
    hideEspOverlay();
  }

  function updateWeightDisplay(value, stable) {
    const el  = document.getElementById('weight-val');
    const bar = document.getElementById('weight-bar');
    if (!el) return;
    const step = steps[currentIndex];
    const target = step ? (step.target_value || 1) : 1;
    el.textContent = value.toFixed(1) + 'g';
    const pct = Math.min(100, (value / target) * 100);
    if (bar) bar.style.width = pct + '%';
  }

  function transitionWeightStable(value) {
    weightState = 'STABLE';
    const el   = document.getElementById('weight-val');
    const next = document.getElementById('btn-next-weight');
    const bar  = document.getElementById('weight-bar');
    if (el)   { el.textContent = value.toFixed(1) + 'g'; el.classList.add('stable'); }
    if (bar)  { bar.classList.add('success'); bar.style.width = '100%'; }
    if (next) next.style.display = '';
    const startBtn = document.getElementById('btn-start-weight');
    if (startBtn) startBtn.style.display = 'none';
  }

  /* ── Generic step renderer ── */
  function renderStep(step) {
    clearInterval(timerInterval);
    if (!step) return;
    if      (step.type === 'instruction') renderInstruction(step);
    else if (step.type === 'timer')       renderTimer(step);
    else if (step.type === 'weight')      renderWeight(step);
    else {
      stepCard.innerHTML = `<div class="step-label">${step.label || 'Step'}</div>`;
    }
  }

  /* ── Overlay helpers ── */
  function showEspOverlay() { espOverlay.classList.add('open'); }
  function hideEspOverlay() { espOverlay.classList.remove('open'); }

  /* ── Session complete ── */
  async function handleComplete() {
    if (leavingSession) return;
    leavingSession = true;
    clearInterval(heartbeatTimer);
    clearInterval(timerInterval);
    ws && ws.disconnect();
    sessionStorage.removeItem('session_id');
    try { await completeSession(sessionId); } catch { /* already complete */ }
    brewApp.style.display = 'none';
    completeScr.classList.add('open');
  }

  function leaveAbandonedSession(message) {
    if (leavingSession) return;
    leavingSession = true;
    clearInterval(heartbeatTimer);
    clearInterval(timerInterval);
    ws && ws.disconnect();
    sessionStorage.removeItem('session_id');
    sessionStorage.removeItem('restart_recipe_id');
    if (message) showToast(message, 'error');
    setTimeout(() => { window.location.replace('/select.html'); }, message ? 1200 : 0);
  }

  dropButton.addEventListener('click', async () => {
    dropButton.disabled = true;
    dropRequested = true;
    try {
      await dropSession();
      leaveAbandonedSession();
    } catch (err) {
      dropRequested = false;
      dropButton.disabled = false;
      showToast(err.message || 'Could not drop session', 'error');
    }
  });

  /* ── Connect WebSocket ── */
  function connectWS() {
    ws = new CoffeeWebSocket(sessionId, token, {
      onSessionState(data) {
        recipe       = data.recipe || {};
        steps        = data.recipe ? data.recipe.steps : [];
        currentIndex = data.current_step || 0;
        brewApp.style.display = '';
        updateTopBar();
        renderSidebar();
        renderStep(steps[currentIndex]);
      },
      onWeightUpdate(value) {
        if (steps[currentIndex] && steps[currentIndex].type === 'weight') {
          if (weightState === 'IDLE') {
            weightState = 'STREAMING';
            const startBtn = document.getElementById('btn-start-weight');
            if (startBtn) startBtn.style.display = 'none';
          }
          updateWeightDisplay(value);
        }
      },
      onWeightStable(value) {
        transitionWeightStable(value);
      },
      onStepAdvance(stepIndex, step) {
        currentIndex = stepIndex;
        steps[stepIndex] = step;
        clearInterval(timerInterval);
        updateTopBar();
        renderSidebar();
        renderStep(step);
      },
      onSessionComplete() {
        handleComplete();
      },
      onSessionAbandoned() {
        leaveAbandonedSession(dropRequested ? '' : 'Session abandoned');
      },
      onEspDisconnected() {
        if (steps[currentIndex] && steps[currentIndex].type === 'weight') {
          showEspOverlay();
        }
      },
      onEspReconnected() {
        hideEspOverlay();
      },
      onTareDone() {
        showToast('Scale tared', 'success');
      },
    });
    ws.connect();
  }

  /* ── Session bootstrap ── */
  async function init() {
    try {
      const current = await getCurrentSession();
      if (!current || !current.session) {
        sessionStorage.removeItem('session_id');
        window.location.href = '/select.html';
        return;
      }
      connectWS();
    } catch {
      sessionStorage.removeItem('session_id');
      window.location.href = '/select.html';
    }
  }

  init();
})();
