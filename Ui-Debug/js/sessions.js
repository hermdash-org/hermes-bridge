/**
 * sessions.js — Sessions page logic.
 *
 * Left: list of sessions
 * Right: full message history of selected session
 */

import { sessionApi } from './api/sessions.js';

let _sessions = [];

// ── List ──────────────────────────────────────────────────────────────

async function loadList() {
  const listEl = document.getElementById('session-list');
  listEl.innerHTML = '<p class="text-xs text-gray-600 px-3 py-2">Loading...</p>';

  try {
    const data = await sessionApi.list(100);
    _sessions = data.sessions || [];

    if (_sessions.length === 0) {
      listEl.innerHTML = '<p class="text-xs text-gray-600 px-3 py-4 text-center">No sessions yet.</p>';
      return;
    }

    listEl.innerHTML = _sessions.map((s, i) => `
      <div onclick="selectSession(${i})"
           id="session-${i}"
           class="px-3 py-2.5 cursor-pointer border-b border-gray-800/50 hover:bg-gray-900 transition-colors">
        <p class="text-xs text-gray-300 truncate font-medium">${s.title || 'Untitled'}</p>
        <div class="flex items-center gap-2 mt-0.5">
          <span class="text-[10px] text-gray-600 font-mono">${s.model || '—'}</span>
          <span class="text-[10px] text-gray-600 ml-auto">${s.message_count} msgs</span>
        </div>
        <p class="text-[10px] text-gray-600 mt-0.5">${formatTime(s.started_at)}</p>
      </div>
    `).join('');

    if (_sessions.length > 0) selectSession(0);

  } catch (err) {
    listEl.innerHTML = `<p class="text-xs text-red-400 px-3 py-2">${err.message}</p>`;
  }
}

// ── Detail ────────────────────────────────────────────────────────────

window.selectSession = async function(index) {
  document.querySelectorAll('[id^="session-"]').forEach(el => el.classList.remove('bg-gray-900'));
  const el = document.getElementById(`session-${index}`);
  if (el) el.classList.add('bg-gray-900');

  const session = _sessions[index];
  if (!session) return;

  const detailEl = document.getElementById('session-detail');
  detailEl.innerHTML = '<p class="text-xs text-gray-600 p-4">Loading...</p>';

  try {
    const data = await sessionApi.get(session.id);
    renderDetail(session, data);
  } catch (err) {
    detailEl.innerHTML = `<p class="text-xs text-red-400 p-4">${err.message}</p>`;
  }
};

function renderDetail(session, data) {
  const messages = data.messages || [];
  const detailEl = document.getElementById('session-detail');

  const ROLE_BADGE = {
    user:      'bg-blue-900/40 text-blue-400',
    assistant: 'bg-emerald-900/40 text-emerald-400',
    tool:      'bg-amber-900/40 text-amber-400',
    system:    'bg-gray-800 text-gray-400',
  };

  detailEl.innerHTML = `
    <!-- Header -->
    <div class="px-4 py-3 border-b border-gray-800 flex items-center gap-3 shrink-0">
      <span class="text-xs text-gray-300 font-medium truncate">${session.title || 'Untitled'}</span>
      <span class="text-xs text-gray-600 font-mono ml-auto shrink-0">${session.model || '—'}</span>
    </div>

    <!-- Messages -->
    <div class="flex-1 overflow-y-auto p-4 space-y-3">
      ${messages.map((msg, i) => {
        const role = msg.role || 'unknown';
        const badge = ROLE_BADGE[role] || 'bg-gray-800 text-gray-400';
        const content = typeof msg.content === 'string'
          ? msg.content
          : JSON.stringify(msg.content, null, 2);

        // Tool calls
        const toolCalls = msg.tool_calls || [];

        return `
          <div class="fade-in">
            <span class="text-[10px] font-medium px-1.5 py-0.5 rounded ${badge}">${role}</span>
            ${content ? `<pre class="mt-1.5 text-xs text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">${escapeHtml(content)}</pre>` : ''}
            ${toolCalls.map(tc => `
              <div class="mt-1.5 bg-gray-900 rounded px-3 py-2 border border-gray-800">
                <span class="text-[10px] text-amber-400 font-mono">${tc.function?.name || 'tool'}</span>
                <pre class="text-[10px] text-gray-500 mt-1 whitespace-pre-wrap break-words">${escapeHtml(tc.function?.arguments || '')}</pre>
              </div>
            `).join('')}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

// ── Helpers ───────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function formatTime(ts) {
  if (!ts) return '—';
  try {
    const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
    return d.toLocaleString();
  } catch {
    return String(ts);
  }
}

// ── Init ──────────────────────────────────────────────────────────────

loadList();
