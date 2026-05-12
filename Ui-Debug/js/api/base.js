/**
 * base.js — Base fetch helper.
 * All API modules import from here. Never call fetch directly elsewhere.
 *
 * Uses the same origin as the page — works on localhost, VPS, any host.
 */

// The debug UI is served by the bridge itself, so same origin = bridge URL
export const BASE = window.location.origin;

export async function apiFetch(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
