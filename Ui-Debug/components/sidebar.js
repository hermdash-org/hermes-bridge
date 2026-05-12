/**
 * sidebar.js — Renders the sidebar nav and handles page switching.
 */

export function renderSidebar(activePage) {
  const nav = [
    { id: 'trajectories', label: 'Trajectories', icon: '⚡' },
    { id: 'sessions',     label: 'Sessions',     icon: '💬' },
  ];

  return `
    <aside class="w-48 shrink-0 border-r border-gray-800 flex flex-col h-screen sticky top-0">
      <div class="px-4 py-5 border-b border-gray-800">
        <span class="text-xs font-semibold text-gray-500 uppercase tracking-widest">Debug UI</span>
      </div>
      <nav class="flex-1 px-2 py-3 space-y-0.5">
        ${nav.map(item => `
          <a href="${item.id}.html"
             class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors
                    ${activePage === item.id ? 'nav-active' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-900'}">
            <span>${item.icon}</span>
            ${item.label}
          </a>
        `).join('')}
      </nav>
      <div class="px-4 py-3 border-t border-gray-800">
        <span class="text-xs text-gray-600">hermes debug</span>
      </div>
    </aside>
  `;
}
