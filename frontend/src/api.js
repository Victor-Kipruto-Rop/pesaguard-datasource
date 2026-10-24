// Same-origin by default in production builds; the dev server talks to the local API.
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
let csrfToken = '';

// The CSRF token is held in memory only. The session itself is an HttpOnly cookie that page
// JavaScript cannot read, so no long-lived credential is ever stored in the browser.
export function setCsrfToken(token) { csrfToken = token || ''; }

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();
  if (!(options.body instanceof FormData) && options.body) headers.set('Content-Type', 'application/json');
  if (!SAFE_METHODS.has(method) && csrfToken && !headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include', ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || body?.error?.message || body?.message || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    error.code = detail?.code || body?.error?.code;
    error.payload = body;
    throw error;
  }
  return response;
}
