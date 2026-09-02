/** Shared localStorage keys and session/inactivity helpers used by both api.ts (silent
 * refresh) and auth.tsx (login/logout + inactivity watcher). Centralized so the two
 * modules never disagree on what a "session" consists of. */

export const ACCESS_TOKEN_KEY = 'citi_access_token'
export const REFRESH_TOKEN_KEY = 'citi_refresh_token'
export const LAST_ACTIVITY_KEY = 'citi_last_activity'

/** Session closes after this long with zero activity, regardless of token validity. */
export const INACTIVITY_LIMIT_MS = 5 * 60 * 60 * 1000 // 5 hours

export function recordActivity(): void {
  localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()))
}

export function getLastActivity(): number {
  const raw = localStorage.getItem(LAST_ACTIVITY_KEY)
  return raw ? Number(raw) : Date.now()
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(LAST_ACTIVITY_KEY)
}

export type SessionEndReason = 'expired' | 'inactivity'

export function redirectToLogin(reason: SessionEndReason): void {
  clearSession()
  if (window.location.pathname !== '/login') {
    window.location.assign(`/login?reason=${reason}`)
  }
}
