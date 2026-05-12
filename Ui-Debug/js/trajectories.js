/**
 * trajectories.js — Trajectory page logic.
 *
 * Left: list of trajectory entries
 * Right: full turn-by-turn view of selected trajectory
 */

import { trajectoryApi } from './api/trajectories.js';
import { renderTurnCard } from '../components/turn-card.js';

let _entries = [];
let _selected = null;

// ── List ──────────────────────────────────────────────────────────────

async function loadList() {
  const listEl = document.getElementById('traj-list');
  listEl.innerHTML = '<p class="text-xs text-gray-600 px-3 py-2">Loading...</p>';

  try {
    const data = await trajectoryApi.list(100);
    _entries = data.entries || [];

    if (_entries.length === 0) {
      listEl.innerHTML = '<p class="text-xs text-gray-600 px-3 py-4 text-center">No trajectories yet.<br>Enable save_trajectories in config.</p>';
      return;
    }

    listEl.innerHTML = _entries.map((e, i) => `
      <div onclick="selectEntry(${i})"
           id="entry-${i}"
           class="px-3 py-2.5 cursor-pointer border-b border-gray-800/50 hover:bg-gray-900 transition-colors">
        <div class="flex items-center gap-1.5 mb-0.5">
          <span class="w-1.5 h-1.5 rounded-full ${e.completed ? 'bg-emerald-500' : 'bg-red-500'}"></span>
          <span class="text-[10px] text-gray-500 font-mono">${e.model || '—'}</span>
          <span class="text-[10px] text-gray-600 ml-auto">${e.turn_count} turns</span>
        </div>
        <p class="text-xs text-gray-400 truncate">${e.preview || '(no preview)'}</p>
        <p class="text-[10px] text-gray-600 mt-0.5">${formatTime(e.timestamp)}</p>
      </div>
    `).join('');

    // Auto-select first
    if (_entries.length > 0) selectEntry(0);

  } catch (err) {
    listEl.innerHTML = `<p class="text-xs text-red-400 px-3 py-2">${err.message}</p>`;
  }
}

// ── Detail ────────────────────────────────────────────────────────────

window.selectEntry = async function(index) {
  // Highlight selected
  document.querySelectorAll('[id^="entry-"]').forEach(el => el.classList.remove('bg-gray-900'));
  const el = document.getElementById(`entry-${index}`);
  if (el) el.classList.add('bg-gray-900');

  const entry = _entries[index];
  if (!entry) return;

  const detailEl = document.getElementById('traj-detail');
  detailEl.innerHTML = '<p class="text-xs text-gray-600 p-4">Loading...</p>';

  try {
    const data = await trajectoryApi.get(entry.source, entry.index);
    _selected = data;
    renderDetail(data);
  } catch (err) {
    detailEl.innerHTML = `<p class="text-xs text-red-400 p-4">${err.message}</p>`;
  }
};

function renderDetail(data) {
  const conversations = data.conversations || [];
  const detailEl = document.getElementById('traj-detail');

  detailEl.innerHTML = `
    <!-- Header -->
    <div class="px-4 py-3 border-b border-gray-800 flex items-center gap-3 shrink-0">
      <span class="w-2 h-2 rounded-full ${data.completed ? 'bg-emerald-500' : 'bg-red-500'}"></span>
      <span class="text-xs text-gray-400 font-mono">${data.model || '—'}</span>
      <span class="text-xs text-gray-600">${formatTime(data.timestamp)}</span>
      <span class="text-xs text-gray-600 ml-auto">${conversations.length} turns</span>
    </div>

    <!-- Turns -->
    <div class="flex-1 overflow-y-auto p-4">
      ${conversations.map((turn, i) => renderTurnCard(turn, i)).join('')}
    </div>
  `;
}

// ── Toggle system turn ────────────────────────────────────────────────

window.toggleSystem = function(index) {
  const content = document.getElementById(`turn-content-${index}`);
  const preview = document.getElementById(`turn-preview-${index}`);
  if (!content) return;
  content.classList.toggle('hidden');
  if (preview) preview.classList.toggle('hidden');
};

// ── Helpers ───────────────────────────────────────────────────────────

function formatTime(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// ── Status bar ────────────────────────────────────────────────────────

async function loadStatus() {
  try {
    const s = await trajectoryApi.getStatus();
    const bar = document.getElementById('status-bar');
    if (bar) {
      bar.innerHTML = `
        <span class="flex items-center gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full ${s.enabled ? 'bg-emerald-500' : 'bg-gray-600'}"></span>
          <span>${s.enabled ? 'Saving enabled' : 'Saving disabled'}</span>
        </span>
        <span>${s.completed_count} completed · ${s.failed_count} failed</span>
        <span class="text-gray-600 font-mono text-[10px]">${s.profile}</span>
      `;
    }
  } catch { /* silent */ }
}

// ── Init ──────────────────────────────────────────────────────────────

loadStatus();
loadList();
