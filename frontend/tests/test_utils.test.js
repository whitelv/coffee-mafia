const fs   = require('fs');
const path = require('path');

// Load utils.js into the jsdom global scope
eval(fs.readFileSync(path.join(__dirname, '../js/utils.js'), 'utf8'));

// ── formatDuration ──────────────────────────────────────────────────────────

describe('formatDuration', () => {
  test('returns "—" for null', () => {
    expect(formatDuration(null)).toBe('—');
  });

  test('returns "—" for undefined', () => {
    expect(formatDuration(undefined)).toBe('—');
  });

  test('0 seconds returns "0s"', () => {
    expect(formatDuration(0)).toBe('0s');
  });

  test('seconds only (< 60)', () => {
    expect(formatDuration(45)).toBe('45s');
  });

  test('exact minutes (no remainder)', () => {
    expect(formatDuration(120)).toBe('2m');
  });

  test('minutes and seconds', () => {
    expect(formatDuration(90)).toBe('1m 30s');
  });

  test('rounds to nearest second', () => {
    expect(formatDuration(61.7)).toBe('1m 2s');
  });

  test('large value', () => {
    expect(formatDuration(3661)).toBe('61m 1s');
  });
});

// ── formatTime ──────────────────────────────────────────────────────────────

describe('formatTime', () => {
  test('zero returns "00:00"', () => {
    expect(formatTime(0)).toBe('00:00');
  });

  test('negative clamped to 0', () => {
    expect(formatTime(-5)).toBe('00:00');
  });

  test('59 seconds', () => {
    expect(formatTime(59)).toBe('00:59');
  });

  test('60 seconds → 1 minute', () => {
    expect(formatTime(60)).toBe('01:00');
  });

  test('65 seconds', () => {
    expect(formatTime(65)).toBe('01:05');
  });

  test('rounds to nearest second', () => {
    expect(formatTime(61.8)).toBe('01:02');
  });

  test('pads minutes and seconds with leading zeros', () => {
    expect(formatTime(125)).toBe('02:05');
  });
});

// ── formatDate ──────────────────────────────────────────────────────────────

describe('formatDate', () => {
  test('returns "—" for null', () => {
    expect(formatDate(null)).toBe('—');
  });

  test('returns "—" for empty string', () => {
    expect(formatDate('')).toBe('—');
  });

  test('returns a non-empty string for a valid ISO date', () => {
    const result = formatDate('2024-01-15T10:30:00.000Z');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
    expect(result).not.toBe('—');
  });
});

// ── setButtonLoading ────────────────────────────────────────────────────────

describe('setButtonLoading', () => {
  test('disables button and shows spinner when loading=true', () => {
    const btn = document.createElement('button');
    btn.innerHTML = 'Submit';
    setButtonLoading(btn, true);
    expect(btn.disabled).toBe(true);
    expect(btn.innerHTML).toContain('spinner');
  });

  test('restores original HTML and re-enables when loading=false', () => {
    const btn = document.createElement('button');
    btn.innerHTML = 'Submit';
    setButtonLoading(btn, true);
    setButtonLoading(btn, false);
    expect(btn.disabled).toBe(false);
    expect(btn.innerHTML).toBe('Submit');
  });
});

// ── showToast ───────────────────────────────────────────────────────────────

describe('showToast', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  test('creates a toast element in the DOM', () => {
    showToast('Hello world', 'info');
    const toast = document.querySelector('.toast');
    expect(toast).not.toBeNull();
    expect(toast.textContent).toBe('Hello world');
  });

  test('applies the correct type class', () => {
    showToast('Error!', 'error');
    const toast = document.querySelector('.toast');
    expect(toast.classList.contains('toast-error')).toBe(true);
  });

  test('creates toast container if absent', () => {
    expect(document.getElementById('toast-container')).toBeNull();
    showToast('msg');
    expect(document.getElementById('toast-container')).not.toBeNull();
  });

  test('reuses existing toast container', () => {
    showToast('first');
    showToast('second');
    const containers = document.querySelectorAll('#toast-container');
    expect(containers.length).toBe(1);
  });
});
