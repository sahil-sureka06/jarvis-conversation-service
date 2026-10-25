"""
Analytics API routes & Standalone Admin Portal for JARVIS Conversation Service.
Accessible at:
    - HTML Dashboard: http://localhost:8002/analytics
    - JSON API:       http://localhost:8002/api/analytics/summary
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from collections import defaultdict

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from src.services.conversation_service import ConversationService

router = APIRouter(tags=["analytics"])


def get_service() -> ConversationService:
    from src.app import service
    return service


@router.get("/api/analytics/summary", summary="Get comprehensive admin analytics summary")
async def get_analytics_summary(
    service: ConversationService = Depends(get_service)
) -> Dict[str, Any]:
    all_data = service.db.get_all_data()
    conversations: List[Dict[str, Any]] = all_data.get("conversations", [])
    messages: List[Dict[str, Any]] = all_data.get("messages", [])

    total_convs = len(conversations)
    active_convs = sum(1 for c in conversations if not c.get("is_deleted", False))
    deleted_convs = sum(1 for c in conversations if c.get("is_deleted", False))

    total_msgs = len(messages)
    active_msgs = sum(1 for m in messages if not m.get("is_deleted", False))
    deleted_msgs = sum(1 for m in messages if m.get("is_deleted", False))
    user_msgs = sum(1 for m in messages if m.get("role") == "user")
    assistant_msgs = sum(1 for m in messages if m.get("role") == "assistant")

    # Tokens & Cost
    total_input_tokens = sum(c.get("total_input_tokens", 0) for c in conversations)
    total_output_tokens = sum(c.get("total_output_tokens", 0) for c in conversations)
    total_tokens = sum(c.get("total_tokens", 0) for c in conversations)
    total_cost = sum(c.get("total_cost", 0.0) for c in conversations)

    # Unique users
    unique_users = set(c.get("user_id") for c in conversations if c.get("user_id"))

    # Latency, tool calls, citations
    latencies: List[int] = []
    total_tool_calls = 0
    total_citations = 0

    # Models breakdown
    models_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "latencies": [],
    })

    # Timeline daily aggregation (last 14 days)
    daily_timeline: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "date": "",
        "conversations": 0,
        "messages": 0,
        "tokens": 0,
        "cost": 0.0,
    })

    # Repositories breakdown
    repo_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "repository_id": "",
        "conversation_count": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
    })

    # User breakdown
    users_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "user_id": "",
        "conversation_count": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "last_active": 0,
    })

    for c in conversations:
        # User agg
        u_id = c.get("user_id") or "anonymous"
        users_usage[u_id]["user_id"] = u_id
        users_usage[u_id]["conversation_count"] += 1
        users_usage[u_id]["total_tokens"] += c.get("total_tokens", 0)
        users_usage[u_id]["total_cost"] += c.get("total_cost", 0.0)
        users_usage[u_id]["last_active"] = max(users_usage[u_id]["last_active"], c.get("updated_at", 0))

        # Repos agg
        rep_ids = c.get("repository_ids", [])
        for r in rep_ids:
            if r:
                repo_usage[r]["repository_id"] = r
                repo_usage[r]["conversation_count"] += 1
                repo_usage[r]["total_tokens"] += c.get("total_tokens", 0)
                repo_usage[r]["total_cost"] += c.get("total_cost", 0.0)

        # Daily timeline agg
        created_ts = c.get("created_at") or 0
        if created_ts > 0:
            date_str = datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            daily_timeline[date_str]["date"] = date_str
            daily_timeline[date_str]["conversations"] += 1
            daily_timeline[date_str]["tokens"] += c.get("total_tokens", 0)
            daily_timeline[date_str]["cost"] += c.get("total_cost", 0.0)

    # Process messages for detailed assistant stats
    for m in messages:
        payload = m.get("payload") or {}
        meta = payload.get("metadata") or {}
        stats = payload.get("stats") or {}

        # Latency
        lat = meta.get("latency_ms")
        if lat and isinstance(lat, (int, float)) and lat > 0:
            latencies.append(int(lat))

        # Tool calls & citations
        total_tool_calls += meta.get("tool_calls_count", 0)
        total_citations += meta.get("citations_count", 0)

        # Model stats
        model = meta.get("model") or "gpt-4o"
        models_usage[model]["call_count"] += 1
        in_t = stats.get("input_tokens", 0)
        out_t = stats.get("output_tokens", 0)
        tot_t = stats.get("total_tokens", in_t + out_t)
        cst = stats.get("cost", 0.0)

        models_usage[model]["input_tokens"] += in_t
        models_usage[model]["output_tokens"] += out_t
        models_usage[model]["total_tokens"] += tot_t
        models_usage[model]["total_cost"] += cst
        if lat:
            models_usage[model]["latencies"].append(lat)

        # Message timeline
        msg_ts = m.get("created_at") or 0
        if msg_ts > 0:
            date_str = datetime.fromtimestamp(msg_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            daily_timeline[date_str]["date"] = date_str
            daily_timeline[date_str]["messages"] += 1

    # Compute averages
    avg_latency_ms = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    avg_tokens_per_conv = round(total_tokens / total_convs, 1) if total_convs else 0.0
    avg_cost_per_conv = round(total_cost / total_convs, 5) if total_convs else 0.0
    avg_turns_per_conv = (
        round(sum(c.get("turn_count", 0) for c in conversations) / total_convs, 1)
        if total_convs else 0.0
    )

    # Format models summary
    models_summary = []
    for model_name, m_data in models_usage.items():
        m_lats = m_data.pop("latencies", [])
        m_data["model"] = model_name
        m_data["total_cost"] = round(m_data["total_cost"], 6)
        m_data["avg_latency_ms"] = round(sum(m_lats) / len(m_lats), 1) if m_lats else 0.0
        models_summary.append(m_data)
    models_summary.sort(key=lambda x: x["call_count"], reverse=True)

    # Format timeline (sorted chronologically)
    timeline_list = sorted(daily_timeline.values(), key=lambda x: x["date"])
    for item in timeline_list:
        item["cost"] = round(item["cost"], 5)

    # Format repositories
    repos_summary = list(repo_usage.values())
    for r in repos_summary:
        r["total_cost"] = round(r["total_cost"], 5)
    repos_summary.sort(key=lambda x: x["conversation_count"], reverse=True)

    # Format users
    users_summary = list(users_usage.values())
    for u in users_summary:
        u["total_cost"] = round(u["total_cost"], 5)
    users_summary.sort(key=lambda x: x["total_cost"], reverse=True)

    # Top costliest assistant responses
    costliest_turns = []
    for m in messages:
        if m.get("role") == "assistant":
            pl = m.get("payload") or {}
            st = pl.get("stats") or {}
            mt = pl.get("metadata") or {}
            cst = st.get("cost", 0.0)
            if cst > 0 or st.get("total_tokens", 0) > 0:
                costliest_turns.append({
                    "msg_id": m.get("msg_id") or m.get("id"),
                    "conversation_id": m.get("conversation_id"),
                    "cost": round(cst, 6),
                    "total_tokens": st.get("total_tokens", 0),
                    "input_tokens": st.get("input_tokens", 0),
                    "output_tokens": st.get("output_tokens", 0),
                    "latency_ms": mt.get("latency_ms"),
                    "model": mt.get("model", "gpt-4o"),
                    "created_at": m.get("created_at"),
                })
    costliest_turns.sort(key=lambda x: x["cost"], reverse=True)
    costliest_turns = costliest_turns[:10]

    # Recent conversations
    recent_convs = []
    for c in conversations[:20]:
        recent_convs.append({
            "conversation_id": c.get("conversation_id") or c.get("id"),
            "user_id": c.get("user_id"),
            "title": c.get("title"),
            "repository_ids": c.get("repository_ids", []),
            "turn_count": c.get("turn_count", 0),
            "total_tokens": c.get("total_tokens", 0),
            "total_cost": round(c.get("total_cost", 0.0), 5),
            "status": c.get("status", "active"),
            "is_deleted": c.get("is_deleted", False),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        })

    return {
        "overview": {
            "total_conversations": total_convs,
            "active_conversations": active_convs,
            "deleted_conversations": deleted_convs,
            "total_messages": total_msgs,
            "active_messages": active_msgs,
            "deleted_messages": deleted_msgs,
            "user_messages": user_msgs,
            "assistant_messages": assistant_msgs,
            "total_unique_users": len(unique_users),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "avg_latency_ms": avg_latency_ms,
            "avg_tokens_per_conv": avg_tokens_per_conv,
            "avg_cost_per_conv": avg_cost_per_conv,
            "avg_turns_per_conv": avg_turns_per_conv,
            "total_tool_calls": total_tool_calls,
            "total_citations": total_citations,
        },
        "database": {
            "database_name": all_data.get("database", "jarvis-conversations"),
            "is_connected": all_data.get("is_connected", False),
            "endpoint": all_data.get("endpoint", "Local Fallback Store"),
            "conversations_count": total_convs,
            "messages_count": total_msgs,
        },
        "models": models_summary,
        "timeline": timeline_list,
        "repositories": repos_summary,
        "users": users_summary,
        "costliest_turns": costliest_turns,
        "recent_conversations": recent_convs,
        "generated_at": int(time.time() * 1000),
    }


@router.get("/analytics", response_class=HTMLResponse, summary="Standalone Admin Analytics Portal")
async def analytics_dashboard():
    """Serves the standalone Admin Analytics Dashboard at http://localhost:8002/analytics."""
    return HTMLResponse(content=STANDALONE_DASHBOARD_HTML)


STANDALONE_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>JARVIS Admin Analytics Portal — Cosmos DB</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090a0f;
      --card-bg: #12151e;
      --card-border: rgba(255, 255, 255, 0.07);
      --accent: #0078d4;
      --accent-hover: #1084d8;
      --orange: #f97316;
      --green: #10b981;
      --purple: #a855f7;
      --red: #ef4444;
      --cyan: #38bdf8;
      --text: #f0f3f8;
      --muted: #8b949e;
      --faint: #586069;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 32px 40px 60px;
      line-height: 1.5;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .header-title {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 6px;
    }
    h1 {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }
    .pill {
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .pill-blue { background: rgba(0, 120, 212, 0.15); color: var(--cyan); border: 1px solid rgba(0, 120, 212, 0.3); }
    .pill-green { background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.3); }
    .pill-orange { background: rgba(249, 115, 22, 0.15); color: var(--orange); border: 1px solid rgba(249, 115, 22, 0.3); }
    .pill-red { background: rgba(239, 68, 68, 0.15); color: var(--red); border: 1px solid rgba(239, 68, 68, 0.3); }
    
    .status-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 16px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--card-border);
      font-size: 12px;
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 12px;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 500;
      padding: 7px 14px;
      border-radius: 8px;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s ease;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: var(--text);
    }
    .btn:hover { background: rgba(255, 255, 255, 0.09); }
    .btn-primary { background: var(--accent); border-color: var(--accent-hover); color: #fff; }
    .btn-primary:hover { background: var(--accent-hover); }

    .grid-kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }
    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .card-value {
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: #fff;
    }
    .card-sub {
      font-size: 12px;
      color: var(--muted);
      margin-top: 6px;
    }

    .tabs {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 20px;
    }
    .tab-btn {
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--muted);
      padding: 10px 16px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s;
    }
    .tab-btn.active {
      color: #fff;
      border-bottom-color: var(--orange);
      font-weight: 600;
      background: rgba(255, 255, 255, 0.03);
      border-radius: 6px 6px 0 0;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }
    th {
      padding: 10px 14px;
      color: var(--muted);
      font-weight: 600;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    td {
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: var(--text);
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    code, .mono { font-family: 'Fira Code', monospace; }
  </style>
</head>
<body>

  <div class="header">
    <div>
      <div class="header-title">
        <span style="font-size: 24px;">📊</span>
        <h1>JARVIS Admin Analytics Portal</h1>
        <span class="pill pill-blue">Cosmos DB Live</span>
      </div>
      <p style="font-size: 13px; color: var(--muted);">
        Dedicated, standalone telemetry dashboard measuring tokens, costs, models, and conversation sessions.
      </p>
    </div>

    <div style="display: flex; gap: 10px; align-items: center;">
      <a href="/explorer" target="_blank" class="btn">
        <span>🪐 Cosmos Data Explorer</span> ↗
      </a>
      <button id="btnAutoRefresh" class="btn" onclick="toggleAutoRefresh()">○ Auto-Refresh (15s)</button>
      <button class="btn btn-primary" onclick="loadAnalytics()">↻ Refresh Now</button>
    </div>
  </div>

  <div class="status-bar" id="statusBar">
    <div>
      <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--green); margin-right: 8px; box-shadow: 0 0 8px var(--green);"></span>
      <strong id="dbName">Cosmos DB: jarvis-conversations</strong>
      <span style="color: var(--muted); margin: 0 8px;">·</span>
      <span id="containersInfo">Loading containers...</span>
    </div>
    <div class="mono" style="font-size: 11px; color: var(--faint);" id="dbEndpoint">Endpoint: Local / Azure Cosmos DB</div>
  </div>

  <!-- KPI Grid -->
  <div class="grid-kpis" id="kpiGrid">
    <div class="card" style="border-color: rgba(249, 115, 22, 0.3);">
      <div class="card-top" style="color: var(--orange);"><span>Cumulative Spend</span><span>💰</span></div>
      <div class="card-value" id="kpiCost">$0.0000</div>
      <div class="card-sub" id="kpiAvgCost">Loading...</div>
    </div>
    <div class="card" style="border-color: rgba(0, 120, 212, 0.3);">
      <div class="card-top" style="color: var(--cyan);"><span>Tokens Consumed</span><span>⚡</span></div>
      <div class="card-value" id="kpiTokens">0</div>
      <div class="card-sub" id="kpiTokensBreakdown">0 in · 0 out</div>
    </div>
    <div class="card" style="border-color: rgba(16, 185, 129, 0.3);">
      <div class="card-top" style="color: var(--green);"><span>Total Conversations</span><span>💬</span></div>
      <div class="card-value" id="kpiConvs">0</div>
      <div class="card-sub" id="kpiConvsBreakdown">0 active · 0 deleted</div>
    </div>
    <div class="card" style="border-color: rgba(168, 85, 247, 0.3);">
      <div class="card-top" style="color: var(--purple);"><span>Total Messages</span><span>📨</span></div>
      <div class="card-value" id="kpiMsgs">0</div>
      <div class="card-sub" id="kpiMsgsBreakdown">0 questions · 0 answers</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Unique Developers</span><span>👥</span></div>
      <div class="card-value" id="kpiUsers">0</div>
      <div class="card-sub">Active developer partitions</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Avg Response Latency</span><span>⏱️</span></div>
      <div class="card-value" id="kpiLatency">0.0s</div>
      <div class="card-sub" id="kpiLatencyMs">0 ms average</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Conversation Depth</span><span>🔄</span></div>
      <div class="card-value" id="kpiDepth">0.0</div>
      <div class="card-sub">Average turns per conversation</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Citations & Tools</span><span>🔍</span></div>
      <div class="card-value" id="kpiTools">0 / 0</div>
      <div class="card-sub">Tool calls / Citations</div>
    </div>
  </div>

  <!-- Navigation Tabs -->
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('overview')">📈 Overview & Trends</button>
    <button class="tab-btn" onclick="switchTab('conversations')">💬 Conversations Audit</button>
    <button class="tab-btn" onclick="switchTab('costs')">💳 Costliest LLM Turns</button>
    <button class="tab-btn" onclick="switchTab('repos')">📁 Repositories & Developers</button>
  </div>

  <!-- Tab 1: Overview -->
  <div id="tabOverview">
    <div style="display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; margin-bottom: 24px;">
      <div class="card">
        <h3 style="font-size: 15px; margin-bottom: 4px;">Daily Conversation Activity</h3>
        <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Historical volume and tokens over recorded dates</p>
        <div id="timelineContainer" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>

      <div class="card">
        <h3 style="font-size: 15px; margin-bottom: 4px;">Model Breakdown</h3>
        <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">AI completions and cost distribution</p>
        <div id="modelsContainer" style="display: flex; flex-direction: column; gap: 12px;"></div>
      </div>
    </div>
  </div>

  <!-- Tab 2: Conversations -->
  <div id="tabConversations" style="display: none;">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
        <div>
          <h3 style="font-size: 15px;">Recent Conversation Sessions</h3>
          <p style="font-size: 12px; color: var(--muted);">Direct from Cosmos DB <code class="mono" style="color: var(--cyan);">conversations</code> collection</p>
        </div>
        <input type="text" id="convFilter" placeholder="Filter by title, user, or repo…" oninput="renderConversations()" style="padding: 8px 12px; border-radius: 8px; background: rgba(255,255,255,0.04); border: 1px solid var(--card-border); color: #fff; font-size: 12px; width: 280px; outline: none;">
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>User ID</th>
              <th>Repositories</th>
              <th>Turns</th>
              <th>Tokens</th>
              <th>Cost ($)</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody id="conversationsTbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Tab 3: Costliest Turns -->
  <div id="tabCosts" style="display: none;">
    <div class="card">
      <h3 style="font-size: 15px; margin-bottom: 4px;">Costliest & Slowest LLM Turns</h3>
      <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Audit of heaviest individual completions stored in Cosmos DB</p>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Message ID</th>
              <th>Model</th>
              <th>Input Toks</th>
              <th>Output Toks</th>
              <th>Total Toks</th>
              <th>Latency</th>
              <th>Cost ($ USD)</th>
            </tr>
          </thead>
          <tbody id="costliestTbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Tab 4: Repositories & Developers -->
  <div id="tabRepos" style="display: none;">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div class="card">
        <h3 style="font-size: 15px; margin-bottom: 4px;">Top Repositories</h3>
        <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Sessions and tokens per codebase</p>
        <div id="reposContainer" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>

      <div class="card">
        <h3 style="font-size: 15px; margin-bottom: 4px;">Developer Partitions</h3>
        <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Usage by user ID</p>
        <div id="usersContainer" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>
    </div>
  </div>

  <script>
    let globalData = null;
    let autoInterval = null;

    async function loadAnalytics() {
      try {
        const res = await fetch('/api/analytics/summary');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        globalData = await res.json();
        renderAll(globalData);
      } catch (e) {
        console.error('Failed to load analytics', e);
      }
    }

    function renderAll(d) {
      if (!d) return;

      // Status bar
      document.getElementById('dbName').textContent = 'Cosmos DB: ' + (d.database.database_name || 'jarvis-conversations');
      document.getElementById('containersInfo').innerHTML = 
        'Containers: <code class="mono" style="color: var(--cyan);">conversations</code> (' + d.database.conversations_count + ') · ' +
        '<code class="mono" style="color: var(--purple);">messages</code> (' + d.database.messages_count + ')';
      document.getElementById('dbEndpoint').textContent = 'Backend: ' + d.database.endpoint;

      // KPIs
      document.getElementById('kpiCost').textContent = '$' + d.overview.total_cost.toFixed(4);
      document.getElementById('kpiAvgCost').textContent = 'Avg $' + d.overview.avg_cost_per_conv + ' / conv';

      document.getElementById('kpiTokens').textContent = d.overview.total_tokens.toLocaleString();
      document.getElementById('kpiTokensBreakdown').textContent = d.overview.total_input_tokens.toLocaleString() + ' in · ' + d.overview.total_output_tokens.toLocaleString() + ' out';

      document.getElementById('kpiConvs').textContent = d.overview.total_conversations;
      document.getElementById('kpiConvsBreakdown').textContent = d.overview.active_conversations + ' active · ' + d.overview.deleted_conversations + ' soft-deleted';

      document.getElementById('kpiMsgs').textContent = d.overview.total_messages;
      document.getElementById('kpiMsgsBreakdown').textContent = d.overview.user_messages + ' user · ' + d.overview.assistant_messages + ' assistant';

      document.getElementById('kpiUsers').textContent = d.overview.total_unique_users;
      document.getElementById('kpiLatency').textContent = (d.overview.avg_latency_ms / 1000).toFixed(2) + 's';
      document.getElementById('kpiLatencyMs').textContent = d.overview.avg_latency_ms.toLocaleString() + ' ms average';

      document.getElementById('kpiDepth').textContent = d.overview.avg_turns_per_conv;
      document.getElementById('kpiTools').textContent = d.overview.total_tool_calls + ' / ' + d.overview.total_citations;

      // Timeline
      const tContainer = document.getElementById('timelineContainer');
      if (d.timeline.length === 0) {
        tContainer.innerHTML = '<div style="color: var(--faint); font-size: 12px;">No historical records yet.</div>';
      } else {
        const maxTokens = Math.max(...d.timeline.map(p => p.tokens), 1);
        tContainer.innerHTML = d.timeline.map(p => {
          const pct = Math.min(100, Math.max(8, (p.tokens / maxTokens) * 100));
          return `
            <div style="display: flex; align-items: center; gap: 10px; font-size: 12px;">
              <span class="mono" style="width: 85px; color: var(--muted);">${p.date}</span>
              <div style="flex: 1; background: rgba(255,255,255,0.04); height: 24px; border-radius: 4px; overflow: hidden; padding: 0 4px; display: flex; align-items: center;">
                <div style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, #0078d4, #38bdf8); border-radius: 3px;"></div>
              </div>
              <span class="mono" style="width: 90px; text-align: right; font-weight: 600;">${p.tokens.toLocaleString()} toks</span>
              <span class="mono" style="width: 70px; text-align: right; color: var(--orange);">$${p.cost.toFixed(4)}</span>
            </div>
          `;
        }).join('');
      }

      // Models
      const mContainer = document.getElementById('modelsContainer');
      mContainer.innerHTML = d.models.map(m => `
        <div style="padding: 12px 14px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border);">
          <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
            <span class="mono" style="font-weight: 600; color: var(--cyan);">${m.model}</span>
            <span class="mono" style="font-weight: 600; color: var(--orange);">$${m.total_cost.toFixed(4)}</span>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--muted);">
            <span>${m.call_count} calls</span>
            <span>${m.total_tokens.toLocaleString()} toks</span>
            <span>${(m.avg_latency_ms / 1000).toFixed(1)}s avg</span>
          </div>
        </div>
      `).join('');

      renderConversations();

      // Costliest
      const cTbody = document.getElementById('costliestTbody');
      cTbody.innerHTML = d.costliest_turns.map(t => `
        <tr>
          <td class="mono" style="color: var(--muted); font-size: 11px;">${t.msg_id.slice(0, 8)}…</td>
          <td style="color: var(--cyan); font-weight: 500;">${t.model}</td>
          <td class="mono" style="color: var(--muted);">${t.input_tokens.toLocaleString()}</td>
          <td class="mono" style="color: var(--muted);">${t.output_tokens.toLocaleString()}</td>
          <td class="mono" style="font-weight: 600;">${t.total_tokens.toLocaleString()}</td>
          <td class="mono">${t.latency_ms ? (t.latency_ms / 1000).toFixed(2) + 's' : '—'}</td>
          <td class="mono" style="color: var(--orange); font-weight: 700;">$${t.cost.toFixed(5)}</td>
        </tr>
      `).join('');

      // Repos
      const rContainer = document.getElementById('reposContainer');
      rContainer.innerHTML = d.repositories.map(r => `
        <div style="padding: 12px 14px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div class="mono" style="font-weight: 600; color: var(--cyan); font-size: 13px;">${r.repository_id}</div>
            <div style="font-size: 11px; color: var(--muted); margin-top: 3px;">${r.conversation_count} sessions · ${r.total_tokens.toLocaleString()} tokens</div>
          </div>
          <div class="mono" style="font-weight: 700; color: var(--orange);">$${r.total_cost.toFixed(4)}</div>
        </div>
      `).join('');

      // Users
      const uContainer = document.getElementById('usersContainer');
      uContainer.innerHTML = d.users.map(u => `
        <div style="padding: 12px 14px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-weight: 600; font-size: 13px;">${u.user_id}</div>
            <div style="font-size: 11px; color: var(--muted); margin-top: 3px;">${u.conversation_count} conversations · ${u.total_tokens.toLocaleString()} tokens</div>
          </div>
          <div class="mono" style="font-weight: 700; color: var(--orange);">$${u.total_cost.toFixed(4)}</div>
        </div>
      `).join('');
    }

    function renderConversations() {
      if (!globalData) return;
      const q = (document.getElementById('convFilter').value || '').toLowerCase().trim();
      let convs = globalData.recent_conversations || [];
      if (q) {
        convs = convs.filter(c => 
          (c.title || '').toLowerCase().includes(q) ||
          (c.user_id || '').toLowerCase().includes(q) ||
          (c.conversation_id || '').toLowerCase().includes(q) ||
          (c.repository_ids || []).some(r => r.toLowerCase().includes(q))
        );
      }
      const tbody = document.getElementById('conversationsTbody');
      tbody.innerHTML = convs.map(c => `
        <tr style="opacity: ${c.is_deleted ? '0.6' : '1'};">
          <td style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500;">
            ${c.title || 'Untitled Session'}
          </td>
          <td style="color: var(--muted); font-size: 12px;">${c.user_id}</td>
          <td>
            ${(c.repository_ids || []).map(r => `<span class="pill pill-blue" style="font-size: 9px; margin-right: 4px;">${r}</span>`).join('') || '<span style="color: var(--faint);">None</span>'}
          </td>
          <td class="mono">${c.turn_count}</td>
          <td class="mono">${c.total_tokens.toLocaleString()}</td>
          <td class="mono" style="color: var(--orange); font-weight: 600;">$${c.total_cost.toFixed(4)}</td>
          <td>
            <span class="pill ${c.is_deleted ? 'pill-red' : 'pill-green'}">${c.is_deleted ? 'Soft-Deleted' : 'Active'}</span>
          </td>
          <td style="font-size: 11px; color: var(--muted);">${c.created_at ? new Date(c.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' }) : ''}</td>
        </tr>
      `).join('');
    }

    function switchTab(tabId) {
      document.querySelectorAll('.tabs .tab-btn').forEach(btn => btn.classList.remove('active'));
      event.target.classList.add('active');

      document.getElementById('tabOverview').style.display = tabId === 'overview' ? 'block' : 'none';
      document.getElementById('tabConversations').style.display = tabId === 'conversations' ? 'block' : 'none';
      document.getElementById('tabCosts').style.display = tabId === 'costs' ? 'block' : 'none';
      document.getElementById('tabRepos').style.display = tabId === 'repos' ? 'block' : 'none';
    }

    function toggleAutoRefresh() {
      const btn = document.getElementById('btnAutoRefresh');
      if (autoInterval) {
        clearInterval(autoInterval);
        autoInterval = null;
        btn.textContent = '○ Auto-Refresh (15s)';
        btn.classList.remove('pill-green');
      } else {
        autoInterval = setInterval(loadAnalytics, 15000);
        btn.textContent = '● Auto (15s)';
        btn.classList.add('pill-green');
      }
    }

    loadAnalytics();
  </script>
</body>
</html>
"""
