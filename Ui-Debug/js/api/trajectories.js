/**
 * trajectories.js — Trajectory API calls.
 */

import { apiFetch } from './base.js';

export const trajectoryApi = {
  getStatus:  ()             => apiFetch('/trajectories/status'),
  list:       (limit = 100)  => apiFetch(`/trajectories/?limit=${limit}`),
  get:        (source, idx)  => apiFetch(`/trajectories/${source}/${idx}`),
};
