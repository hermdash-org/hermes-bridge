/**
 * compare.js — Side-by-side session vs trajectory comparison.
 *
 * Left panel:  session list → click to load session messages
 * Middle:      session messages (what user saw)
 * Right:       matching trajectory (what agent actually did — thinking, tools)
 */

import { sessionApi } from './api/sessions.js';
import { trajectoryApi } from './api/trajectories.js';

let _sessions = [];
let _trajectories = [];

// ── Load both lists on startup ────────────────────────────────────────

async function init() {
  await Promise.all([loadSessions(), loadTrajectories()]);
}

async function loadSessions() {
  try {
    const data = await sessionApi.list(200);
    _sessions = data.sessions || [];
    renderSessionList();
  } catch (err) {
    document.getElementById('session-list').innerHTML =
      `<p class="text-xs text-red-400 px-3 py-2">${err.message}</p>`;
  }
}

async function loadTrajectories() {
  try {
    const data = await trajectoryApi.list(200);
    _trajectories = data.entries || [];
  } catch { /* silent — trajectories may be empty */ }
}

// ── Session list ──────────────────────────────────────────────────────

function renderSessionList() {
  const el = document.getElementById('session-list');
  if (_sessions.length === 0) {
    el.innerHTML = '<p class="text-xs text-gray-600 px-3 py-4 text-center">No sessions</p>';
    return;
  }
  el.innerHTML = _sessions.map((s, i) => `
    <div onclick="selectSession(${i})"
         id="sess-${i}"
         class="px-3 py-2.5 cursor-pointer border-b border-gray-800/50 hover:bg-gray-900 transition-colors">
      <p class="text-xs text-gray-300 truncate font-medium">${s.title || 'Untitled'}</p>
      <div class="flex items-center gap-2 mt-0.5">
        <span class="text-[10px] text-gray-600 font-mono truncate">${s.model || '—'}</span>
        <span class="text-[10px] text-gray-600 ml-auto shrink-0">${s.message_count} msgs</span>
      </div>
      <p class="text-[10px] text-gray-700 mt-0.5">${formatTime(s.started_at)}</p>
    </div>
  `).join('');
}

// ── Select session → load both panels ────────────────────────────────

window.selectSession = async function(index) {
  // Highlight
  document.querySelectorAll('[id^="sess-"]').forEach(el => el.classList.remove('bg-gray-900'));
  document.getElementById(`sess-${index}`)?.classList.add('bg-gray-900');

  const session = _sessions[index];
  if (!session) return;

  // Load session messages
  const sessionPanel = document.getElementById('session-panel');
  const trajPanel = document.getElementById('traj-panel');

  sessionPanel.innerHTML = '<p class="text-xs text-gray-600 p-4">Loading...</p>';
  trajPanel.innerHTML = '<p class="text-xs text-gray-600 p-4">Searching for matching trajectory...</p>';

  try {
    const data = await sessionApi.get(session.id);
    renderSessionPanel(session, data.messages || []);
  } catch (err) {
    sessionPanel.innerHTML = `<p class="text-xs text-red-400 p-4">${err.message}</p>`;
  }

  // Find matching trajectory by timestamp proximity
  await loadMatchingTrajectory(session);
};

// ── Session panel ─────────────────────────────────────────────────────

function renderSessionPanel(session, messages) {
  const el = document.getElementById('session-panel');

  const BADGE = {
    user:      'bg-blue-900/40 text-blue-400',
    assistant: 'bg-emerald-900/40 text-emerald-400',
    tool:      'bg-amber-900/40 text-amber-400',
    system:    'bg-gray-800 text-gray-500',
  };

  el.innerHTML = `
    <div class="px-3 py-2 border-b border-gray-800 shrink-0">
      <p class="text-xs text-gray-300 font-medium truncate">${session.title || 'Untitled'}</p>
      <p class="text-[10px] text-gray-600 font-mono">${session.model || '—'}</p>
    </div>
    <div class="flex-1 overflow-y-auto p-3 space-y-2">
      ${messages.map(msg => {
        const role = msg.role || 'unknown';
        const badge = BADGE[role] || 'bg-gray-800 text-gray-400';
        const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2);
        const toolCalls = msg.tool_calls || [];
        return `
          <div class="fade-in">
            <span class="text-[10px] font-medium px-1.5 py-0.5 rounded ${badge}">${role}</span>
            ${content ? `<pre class="mt-1 text-xs text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">${escapeHtml(content)}</pre>` : ''}
            ${toolCalls.map(tc => `
              <div class="mt-1 bg-gray-900 rounded px-2 py-1.5 border border-gray-800">
                <span class="text-[10px] text-amber-400 font-mono">${tc.function?.name || 'tool'}</span>
                <pre class="text-[10px] text-gray-500 mt-0.5 whitespace-pre-wrap break-words">${escapeHtml(tc.function?.arguments || '')}</pre>
              </div>
            `).join('')}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

// ── Trajectory panel ──────────────────────────────────────────────────

async function loadMatchingTrajectory(session) {
  const el = document.getElementById('traj-panel');

  // Match by timestamp — find trajectory closest to session start
  const sessionTs = session.started_at * 1000; // convert to ms

  let bestMatch = null;
  let bestDiff = Infinity;

  for (const entry of _trajectories) {
    if (!entry.timestamp) continue;
    const entryTs = new Date(entry.timestamp).getTime();
    const diff = Math.abs(entryTs - sessionTs);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestMatch = entry;
    }
  }

  // Only use match if within 24 hours
  if (!bestMatch || bestDiff > 86400000) {
    el.innerHTML = `
      <div class="flex items-center justify-center h-full">
        <p class="text-xs text-gray-700 text-center px-4">No matching trajectory found.<br>Enable save_trajectories and chat again.</p>
      </div>
    `;
    return;
  }

  try {
    const data = await trajectoryApi.get(bestMatch.source, bestMatch.index);
    renderTrajPanel(data);
  } catch (err) {
    el.innerHTML = `<p class="text-xs text-red-400 p-4">${err.message}</p>`;
  }
}

function renderTrajPanel(data) {
  const el = document.getElementById('traj-panel');
  const conversations = data.conversations || [];

  const ROLE_META = {
    system: { label: 'System',    badge: 'bg-gray-800 text-gray-500',         border: 'border-l-gray-700' },
    human:  { label: 'User',      badge: 'bg-blue-900/40 text-blue-400',      border: 'border-l-blue-700' },
    gpt:    { label: 'Assistant', badge: 'bg-emerald-900/40 text-emerald-400', border: 'border-l-emerald-700' },
    tool:   { label: 'Tool',      badge: 'bg-amber-900/40 text-amber-400',    border: 'border-l-amber-700' },
  };

  el.innerHTML = `
    <div class="px-3 py-2 border-b border-gray-800 shrink-0 flex items-center gap-2">
      <span class="w-1.5 h-1.5 rounded-full ${data.completed ? 'bg-emerald-500' : 'bg-red-500'}"></span>
      <p class="text-[10px] text-gray-500 font-mono">${data.model || '—'}</p>
      <span class="text-[10px] text-gray-700 ml-auto">${conversations.length} turns</span>
    </div>
    <div class="flex-1 overflow-y-auto p-3 space-y-2">
      ${conversations.map((turn, i) => {
        const role = turn.from || 'unknown';
        const meta = ROLE_META[role] || { label: role, badge: 'bg-gray-800 text-gray-400', border: 'border-l-gray-700' };
        const value = turn.value || '';
        const isSystem = role === 'system';

        // Extract <think> block
        const thinkMatch = value.match(/<think>([\s\S]*?)<\/think>/i);
        const think = thinkMatch ? thinkMatch[1].trim() : null;
        const content = value.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();

        return `
          <div class="border-l-2 ${meta.border} pl-2 fade-in">
            <span class="text-[10px] font-medium px-1.5 py-0.5 rounded ${meta.badge}">${meta.label}</span>
            ${think ? `
              <div class="mt-1 bg-gray-900/60 rounded px-2 py-1.5 border-l-2 border-gray-600">
                <span class="text-[9px] text-gray-600 block mb-0.5">thinking</span>
                <pre class="text-[10px] text-gray-500 whitespace-pre-wrap break-words italic leading-relaxed">${escapeHtml(think)}</pre>
              </div>
            ` : ''}
            ${content && !isSystem ? `<pre class="mt-1 text-xs text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">${escapeHtml(content)}</pre>` : ''}
            ${isSystem ? `<p class="text-[10px] text-gray-700 mt-0.5 italic">Tool definitions (${content.length} chars)</p>` : ''}
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
  } catch { return String(ts); }
}

// ── Init ──────────────────────────────────────────────────────────────

init();
