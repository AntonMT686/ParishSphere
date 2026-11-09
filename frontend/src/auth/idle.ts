/**
 * Client-side inactivity tracking (docs/06-security.md §2).
 *
 * Activity is shared across tabs via localStorage so a user working in one tab is not logged out
 * by another. The server enforces the same 30-minute limit independently.
 */
const KEY = 'ps.lastActivity';
const WRITE_THROTTLE_MS = 5_000;

let memoryLast = Date.now();
let lastWrite = 0;

export function lastActivity(): number {
  try {
    const stored = Number(window.localStorage.getItem(KEY) ?? 0);
    return Math.max(stored, memoryLast);
  } catch {
    return memoryLast;
  }
}

export function markActivity(now = Date.now(), force = false): void {
  memoryLast = now;
  if (!force && now - lastWrite < WRITE_THROTTLE_MS) return;
  lastWrite = now;
  try {
    window.localStorage.setItem(KEY, String(now));
  } catch {
    /* storage unavailable – memory only */
  }
}

export const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'scroll', 'touchstart', 'wheel', 'mousemove'] as const;

export interface IdleState {
  /** Seconds until the session expires for inactivity. */
  remaining: number;
  warning: boolean;
  expired: boolean;
}

export function computeIdle(now: number, last: number, timeoutSeconds: number, warnSeconds = 120): IdleState {
  const remaining = Math.max(0, Math.ceil(timeoutSeconds - (now - last) / 1000));
  return { remaining, warning: remaining > 0 && remaining <= warnSeconds, expired: remaining === 0 };
}
