/**
 * turn-card.js — Renders a single conversation turn.
 *
 * Roles from trajectory format (agent/trajectory.py):
 *   system  → tool definitions
 *   human   → user message
 *   gpt     → assistant response (may contain <think> blocks)
 *   tool    → tool results wrapped in <tool_response> tags
 */

function extractThink(value) {
  const match = value.match(/<think>([\s\S]*?)<\/think>/i);
  return match ? match[1].trim() : null;
}

function stripThink(value) {
  return value.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

const ROLE_META = {
  system: { label: 'System',    cls: 'turn-system',  badge: 'bg-gray-800 text-gray-400' },
  human:  { label: 'User',      cls: 'turn-human',   badge: 'bg-blue-900/40 text-blue-400' },
  gpt:    { label: 'Assistant', cls: 'turn-gpt',     badge: 'bg-emerald-900/40 text-emerald-400' },
  tool:   { label: 'Tool',      cls: 'turn-tool',    badge: 'bg-amber-900/40 text-amber-400' },
};

export function renderTurnCard(turn, index) {
  const role = turn.from || 'unknown';
  const meta = ROLE_META[role] || { label: role, cls: '', badge: 'bg-gray-800 text-gray-400' };
  const value = turn.value || '';

  const think = role === 'gpt' ? extractThink(value) : null;
  const content = role === 'gpt' ? stripThink(value) : value;

  // Collapse system turns by default (they're long tool definitions)
  const isSystem = role === 'system';
  const preview = content.slice(0, 200);

  return `
    <div class="turn-card ${meta.cls} pl-3 py-2 mb-2 fade-in" data-index="${index}">
      <div class="flex items-center gap-2 mb-1.5">
        <span class="text-[10px] font-medium px-1.5 py-0.5 rounded ${meta.badge}">${meta.label}</span>
        <span class="text-[10px] text-gray-600">#${index + 1}</span>
        ${isSystem ? `<button onclick="toggleSystem(${index})" class="text-[10px] text-gray-600 hover:text-gray-400 ml-auto">show/hide</button>` : ''}
      </div>

      ${think ? `
        <div class="think-block bg-gray-900/50 rounded px-3 py-2 mb-2 text-xs text-gray-500 whitespace-pre-wrap" id="think-${index}">
          <span class="text-[10px] text-gray-600 block mb-1">thinking</span>
          ${escapeHtml(think)}
        </div>
      ` : ''}

      <div id="turn-content-${index}" class="${isSystem ? 'hidden' : ''}">
        <pre class="text-xs text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">${escapeHtml(content)}</pre>
      </div>

      ${isSystem ? `
        <div id="turn-preview-${index}">
          <pre class="text-xs text-gray-600 whitespace-pre-wrap break-words font-mono">${escapeHtml(preview)}${content.length > 200 ? '...' : ''}</pre>
        </div>
      ` : ''}
    </div>
  `;
}
