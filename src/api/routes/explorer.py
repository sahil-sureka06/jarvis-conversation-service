"""
Cosmos DB Visual Data Explorer Route.

Provides an interactive browser interface to inspect and query the Cosmos DB
database ('jarvis-conversations') and its collections ('conversations' and 'messages').
Accessible at http://localhost:8002/explorer
"""
from __future__ import annotations

import json
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["explorer"])


@router.get("/api/explorer/data", summary="Raw Cosmos DB data for Data Explorer")
async def get_explorer_data():
    from src.app import db_manager
    return db_manager.get_all_data()


@router.get("/explorer", response_class=HTMLResponse, summary="Visual Cosmos DB Data Explorer")
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def cosmos_data_explorer():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Azure Cosmos DB — Data Explorer | JARVIS</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0c10;
      --sidebar-bg: #111318;
      --card-bg: #161922;
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #0078d4;
      --accent-hover: #1084d8;
      --accent-glow: rgba(0, 120, 212, 0.25);
      --text-main: #f0f3f8;
      --text-muted: #8b949e;
      --text-faint: #586069;
      --orange: #f97316;
      --green: #10b981;
      --purple: #a855f7;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text-main);
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* Header */
    header {
      background: #0d0f14;
      border-bottom: 1px solid var(--card-border);
      padding: 10px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 52px;
      flex-shrink: 0;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .azure-logo {
      width: 24px;
      height: 24px;
      background: linear-gradient(135deg, #0078d4, #00bcbc);
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 800;
      font-size: 13px;
      box-shadow: 0 0 10px rgba(0, 120, 212, 0.4);
    }
    .brand-title {
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge {
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px;
      border-radius: 12px;
      font-family: 'Fira Code', monospace;
    }
    .badge-status {
      background: rgba(16, 185, 129, 0.12);
      color: var(--green);
      border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .badge-local {
      background: rgba(249, 115, 22, 0.12);
      color: var(--orange);
      border: 1px solid rgba(249, 115, 22, 0.25);
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .btn {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
      color: var(--text-main);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .btn:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.15);
    }
    .btn-primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .btn-primary:hover {
      background: var(--accent-hover);
    }

    /* Layout */
    .app-body {
      display: flex;
      flex: 1;
      min-height: 0;
    }

    /* Left Sidebar: Collections Tree */
    .tree-sidebar {
      width: 280px;
      background: var(--sidebar-bg);
      border-right: 1px solid var(--card-border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }
    .tree-header {
      padding: 12px 16px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.05em;
      border-bottom: 1px solid var(--card-border);
    }
    .db-node {
      padding: 12px 16px;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }
    .coll-item {
      padding: 10px 16px 10px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
      color: var(--text-muted);
      cursor: pointer;
      border-left: 3px solid transparent;
      transition: all 0.12s;
    }
    .coll-item:hover {
      background: rgba(255, 255, 255, 0.04);
      color: var(--text-main);
    }
    .coll-item.active {
      background: rgba(0, 120, 212, 0.12);
      color: #fff;
      border-left-color: var(--accent);
      font-weight: 500;
    }
    .coll-meta {
      font-size: 11px;
      color: var(--text-faint);
      font-family: 'Fira Code', monospace;
    }

    /* Main Area */
    .main-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }

    /* Query & Filter Bar */
    .query-bar {
      padding: 10px 16px;
      background: #0e1017;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .sql-input {
      flex: 1;
      background: rgba(0, 0, 0, 0.4);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 7px 12px;
      color: #38bdf8;
      font-family: 'Fira Code', monospace;
      font-size: 12px;
      outline: none;
    }
    .sql-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-glow);
    }

    /* Split Pane: Items List & Document Inspector */
    .explorer-panes {
      display: flex;
      flex: 1;
      min-height: 0;
    }
    .items-pane {
      width: 45%;
      border-right: 1px solid var(--card-border);
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .inspector-pane {
      width: 55%;
      display: flex;
      flex-direction: column;
      min-height: 0;
      background: #0d0f15;
    }

    .pane-header {
      padding: 10px 16px;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid var(--card-border);
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .items-table-wrap {
      flex: 1;
      overflow-y: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th {
      position: sticky;
      top: 0;
      background: #13161f;
      padding: 8px 12px;
      text-align: left;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--card-border);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    td {
      padding: 9px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: var(--text-main);
      font-family: 'Fira Code', monospace;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 160px;
    }
    tr {
      cursor: pointer;
      transition: background 0.1s;
    }
    tr:hover {
      background: rgba(255, 255, 255, 0.04);
    }
    tr.selected {
      background: rgba(0, 120, 212, 0.15) !important;
    }

    /* JSON Inspector */
    .json-wrap {
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      font-family: 'Fira Code', monospace;
      font-size: 12px;
      line-height: 1.6;
      color: #93c5fd;
      background: #090a0e;
    }
    pre {
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* Cloud guide modal */
    .guide-banner {
      background: rgba(0, 120, 212, 0.08);
      border-bottom: 1px solid rgba(0, 120, 212, 0.2);
      padding: 8px 16px;
      font-size: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: #93c5fd;
    }
    .guide-banner a {
      color: #38bdf8;
      text-decoration: underline;
      cursor: pointer;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="azure-logo">⚡</div>
      <div class="brand-title">
        Azure Cosmos DB Data Explorer
        <span style="color: var(--text-faint); font-weight: 400;">/</span>
        <span style="color: #60a5fa;" id="db-title">jarvis-conversations</span>
      </div>
      <span class="badge" id="status-badge">Loading...</span>
    </div>
    <div class="header-actions">
      <button class="btn" onclick="fetchData()">🔄 Refresh</button>
      <a class="btn" href="/analytics">📊 Analytics Dashboard</a>
      <a class="btn" href="http://localhost:3000/chat" target="_blank">💬 Open Chat UI</a>
      <a class="btn" href="/docs" target="_blank">📖 API Docs</a>
    </div>
  </header>

  <div class="guide-banner" id="cloud-banner">
    <div>
      ℹ️ <strong>Storage Target:</strong> <span id="storage-detail">Loading configuration...</span>
    </div>
    <div>
      <span>To connect directly to live Azure Cloud: set <code>COSMOS_ENDPOINT</code> and <code>COSMOS_KEY</code> in <code>jarvis-conversation-service/.env</code></span>
    </div>
  </div>

  <div class="app-body">
    <!-- Left Tree Sidebar -->
    <div class="tree-sidebar">
      <div class="tree-header">Database & Collections</div>
      <div class="db-node">
        <span>🗄️</span>
        <span style="flex: 1;">jarvis-conversations</span>
      </div>
      <div class="coll-item active" id="tab-convs" onclick="switchCollection('conversations')">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span>📦</span>
          <span>conversations</span>
        </div>
        <div class="coll-meta" id="count-convs">0</div>
      </div>
      <div class="coll-item" id="tab-msgs" onclick="switchCollection('messages')">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span>💬</span>
          <span>messages</span>
        </div>
        <div class="coll-meta" id="count-msgs">0</div>
      </div>

      <div style="margin-top: auto; padding: 16px; border-top: 1px solid var(--card-border); font-size: 11px; color: var(--text-muted); line-height: 1.5;">
        <div><strong>Partition Keys:</strong></div>
        <div style="margin-top: 4px; font-family: 'Fira Code', monospace; color: var(--orange);">• conversations: /user_id</div>
        <div style="margin-top: 2px; font-family: 'Fira Code', monospace; color: #38bdf8;">• messages: /conversation_id</div>
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="main-content">
      <!-- Query Bar -->
      <div class="query-bar">
        <span style="font-size: 12px; font-weight: 600; color: var(--text-muted);">SQL QUERY:</span>
        <input class="sql-input" id="query-input" value="SELECT * FROM c" oninput="filterItems()">
        <button class="btn btn-primary" onclick="filterItems()">Execute Query</button>
      </div>

      <!-- Split Explorer Panes -->
      <div class="explorer-panes">
        <!-- Table Pane -->
        <div class="items-pane">
          <div class="pane-header">
            <span id="items-title">Items (0)</span>
            <span id="items-pk-label" style="font-family: 'Fira Code', monospace; font-size: 11px; color: var(--orange);">PK: /user_id</span>
          </div>
          <div class="items-table-wrap">
            <table id="items-table">
              <thead>
                <tr id="table-head">
                  <!-- Injected via JS -->
                </tr>
              </thead>
              <tbody id="table-body">
                <!-- Injected via JS -->
              </tbody>
            </table>
          </div>
        </div>

        <!-- Document Inspector Pane -->
        <div class="inspector-pane">
          <div class="pane-header">
            <span>Document Inspector</span>
            <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="copyJSON()">📋 Copy JSON</button>
          </div>
          <div class="json-wrap">
            <pre id="json-viewer">// Select an item on the left to inspect its Cosmos DB JSON document</pre>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let rawData = { conversations: [], messages: [] };
    let currentCollection = 'conversations';
    let selectedItem = null;

    async function fetchData() {
      try {
        const res = await fetch('/api/explorer/data');
        rawData = await res.json();
        
        document.getElementById('count-convs').innerText = rawData.conversations.length;
        document.getElementById('count-msgs').innerText = rawData.messages.length;

        const badge = document.getElementById('status-badge');
        if (rawData.is_connected) {
          badge.className = 'badge badge-status';
          badge.innerText = 'Connected to Azure Cosmos DB';
          document.getElementById('storage-detail').innerText = rawData.endpoint;
        } else {
          badge.className = 'badge badge-local';
          badge.innerText = 'Local Collection Mode';
          document.getElementById('storage-detail').innerText = 'Local Storage Emulator (Dual Collections)';
        }

        renderTable();
      } catch (err) {
        console.error('Failed to load explorer data:', err);
      }
    }

    function switchCollection(name) {
      currentCollection = name;
      document.getElementById('tab-convs').className = 'coll-item ' + (name === 'conversations' ? 'active' : '');
      document.getElementById('tab-msgs').className = 'coll-item ' + (name === 'messages' ? 'active' : '');
      
      const pkLabel = document.getElementById('items-pk-label');
      if (name === 'conversations') {
        pkLabel.innerText = 'PK: /user_id';
        pkLabel.style.color = 'var(--orange)';
      } else {
        pkLabel.innerText = 'PK: /conversation_id';
        pkLabel.style.color = '#38bdf8';
      }

      selectedItem = null;
      document.getElementById('json-viewer').innerText = '// Select an item on the left to inspect its Cosmos DB JSON document';
      renderTable();
    }

    function renderTable() {
      const items = rawData[currentCollection] || [];
      const query = document.getElementById('query-input').value.toLowerCase().trim();
      
      const thead = document.getElementById('table-head');
      const tbody = document.getElementById('table-body');
      thead.innerHTML = '';
      tbody.innerHTML = '';

      if (currentCollection === 'conversations') {
        thead.innerHTML = `
          <th>ID</th>
          <th>User ID (PK)</th>
          <th>Turns</th>
          <th>Updated</th>
        `;
      } else {
        thead.innerHTML = `
          <th>Msg ID</th>
          <th>Conversation ID (PK)</th>
          <th>Role</th>
        `;
      }

      const filtered = items.filter(it => {
        if (!query || query === 'select * from c') return true;
        return JSON.stringify(it).toLowerCase().includes(query);
      });

      document.getElementById('items-title').innerText = `${currentCollection} (${filtered.length})`;

      if (filtered.length === 0) {
        const colSpan = currentCollection === 'conversations' ? 4 : 3;
        tbody.innerHTML = `<tr><td colspan="${colSpan}" style="text-align: center; color: var(--text-faint); padding: 24px;">No items found in this collection.</td></tr>`;
        return;
      }

      filtered.forEach((it, idx) => {
        const tr = document.createElement('tr');
        if (selectedItem && selectedItem.id === it.id) tr.className = 'selected';
        
        tr.onclick = () => {
          document.querySelectorAll('#table-body tr').forEach(r => r.classList.remove('selected'));
          tr.classList.add('selected');
          inspectDoc(it);
        };

        const deletedBadge = it.is_deleted ? ' <span style="font-size: 10px; color: #f87171; background: rgba(239,68,68,0.15); padding: 1px 5px; border-radius: 4px; font-weight: 600;">DELETED</span>' : '';

        if (currentCollection === 'conversations') {
          const date = new Date(it.updated_at || it.created_at || Date.now()).toLocaleTimeString();
          tr.innerHTML = `
            <td style="color: #60a5fa;" title="${it.id}">${it.id.slice(0, 12)}…${deletedBadge}</td>
            <td style="color: var(--orange);">${it.user_id || 'default_user'}</td>
            <td>${it.turn_count || 0}</td>
            <td style="color: var(--text-muted);">${date}</td>
          `;
        } else {
          const roleColor = it.role === 'user' ? 'var(--orange)' : '#10b981';
          tr.innerHTML = `
            <td style="color: #60a5fa;" title="${it.id}">${(it.msg_id || it.id).slice(0, 14)}…${deletedBadge}</td>
            <td style="color: #38bdf8;" title="${it.conversation_id}">${it.conversation_id}</td>
            <td style="color: ${roleColor}; font-weight: 600;">${it.role}</td>
          `;
        }
        tbody.appendChild(tr);
      });

      // Select first item by default if nothing selected
      if (!selectedItem && filtered.length > 0) {
        tbody.children[0].classList.add('selected');
        inspectDoc(filtered[0]);
      }
    }

    function inspectDoc(doc) {
      selectedItem = doc;
      document.getElementById('json-viewer').innerText = JSON.stringify(doc, null, 2);
    }

    function filterItems() {
      renderTable();
    }

    function copyJSON() {
      if (!selectedItem) return;
      navigator.clipboard.writeText(JSON.stringify(selectedItem, null, 2));
      alert('Copied document JSON to clipboard!');
    }

    fetchData();
    setInterval(fetchData, 4000); // Polling update every 4s
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content, status_code=200)
