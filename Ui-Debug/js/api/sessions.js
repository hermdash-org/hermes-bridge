/**
 * sessions.js — Sessions API calls.
 */

import { apiFetch } from './base.js';

export const sessionApi = {
  list: (limit = 100) => apiFetch(`/sessions/?limit=${limit}`),
  get:  (id)          => apiFetch(`/sessions/${id}`),
};
