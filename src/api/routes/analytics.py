"""
Analytics API routes & Standalone Admin Portal for JARVIS Conversation Service.
Accessible at:
    - HTML Dashboard: http://localhost:8002/analytics
    - JSON API:       http://localhost:8002/api/analytics/summary
"""
from __future__ import annotations

import json
import time
import urllib.request
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


def fetch_parsing_metrics() -> Dict[str, Any]:
    """
    Fetches real-time indexing & parsing telemetry from the Jarvis Parser daemon (http://localhost:8001).
    Computes node counts, relationship counts, parse error statistics, stage latency averages,
    and LLM / embedding cost breakdowns.
    """
    jobs: List[Dict[str, Any]] = []
    repos: List[Dict[str, Any]] = []
    is_connected = False

    # 1. Fetch indexing jobs
    try:
        req = urllib.request.Request(
            "http://localhost:8001/api/index",
            headers={"User-Agent": "Jarvis-Analytics/1.0"}
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            jobs = json.loads(resp.read().decode("utf-8"))
        is_connected = True
    except Exception:
        jobs = []

    # 2. Fetch indexed repos
    try:
        req2 = urllib.request.Request(
            "http://localhost:8001/api/repos",
            headers={"User-Agent": "Jarvis-Analytics/1.0"}
        )
        with urllib.request.urlopen(req2, timeout=2.5) as resp2:
            repos = json.loads(resp2.read().decode("utf-8"))
    except Exception:
        repos = []

    total_jobs = len(jobs)
    completed_jobs = sum(1 for j in jobs if j.get("status") == "done")
    failed_jobs = sum(1 for j in jobs if j.get("status") == "failed")
    running_jobs = sum(1 for j in jobs if j.get("status") in ("running", "queued"))

    total_nodes = sum(j.get("node_count") or 0 for j in jobs)
    total_edges = sum(j.get("relationship_count") or 0 for j in jobs)
    total_errors = sum(j.get("parse_errors") or 0 for j in jobs)

    total_llm_input_tokens = total_nodes * 200
    total_llm_output_tokens = total_nodes * 40
    total_llm_tokens = total_llm_input_tokens + total_llm_output_tokens
    total_embedding_tokens = total_nodes * 200
    total_parsing_tokens = total_llm_tokens + total_embedding_tokens

    llm_spend = total_nodes * 0.000054
    embedding_spend = total_nodes * 0.000004
    total_parsing_cost = round(llm_spend + embedding_spend, 5)
    total_gpt4o_spend = round(total_nodes * 0.000904, 5)

    stage_totals: Dict[str, float] = {}
    stage_counts: Dict[str, int] = {}
    job_durations: List[float] = []

    formatted_jobs: List[Dict[str, Any]] = []
    for j in sorted(jobs, key=lambda x: x.get("created_at") or 0, reverse=True):
        st = j.get("created_at") or 0
        fin = j.get("finished_at") or 0
        dur = round(fin - st, 1) if (fin and st and fin >= st) else 0.0
        if dur > 0:
            job_durations.append(dur)

        nc = j.get("node_count") or 0
        rel_c = j.get("relationship_count") or 0
        job_cost = round(nc * 0.000058, 5)

        stages_info: List[Dict[str, Any]] = []
        for s in j.get("stages", []):
            s_name = s.get("name")
            s_st = s.get("started_at")
            s_fin = s.get("finished_at")
            s_dur = round(s_fin - s_st, 2) if (s_fin and s_st and s_fin >= s_st) else 0.0
            if s_name and s_dur > 0:
                stage_totals[s_name] = stage_totals.get(s_name, 0.0) + s_dur
                stage_counts[s_name] = stage_counts.get(s_name, 0) + 1
            stages_info.append({
                "number": s.get("number"),
                "name": s_name,
                "status": s.get("status"),
                "duration_s": s_dur,
                "detail": s.get("detail", "")
            })

        formatted_jobs.append({
            "job_id": j.get("job_id"),
            "repository_id": j.get("repository_id") or j.get("repo_url"),
            "repo_url": j.get("repo_url"),
            "branch": j.get("branch", "main"),
            "cluster_id": j.get("cluster_id", "default"),
            "status": j.get("status"),
            "node_count": nc,
            "relationship_count": rel_c,
            "parse_errors": j.get("parse_errors") or 0,
            "error_details": j.get("error_details") or [],
            "duration_s": dur,
            "estimated_cost": job_cost,
            "stages": stages_info,
            "created_at": st,
            "finished_at": fin,
        })

    total_pipeline_time = sum(stage_totals.values())
    stage_breakdown: List[Dict[str, Any]] = []
    stage_order = [
        "Git Clone", "AST Parsing", "Graph Building",
        "Neo4j Write", "Cross-Repo Linking", "LLM Descriptions", "Milvus Embeddings"
    ]
    all_stage_names = list(stage_totals.keys())
    sorted_stages = sorted(
        all_stage_names,
        key=lambda x: stage_order.index(x) if x in stage_order else 99
    )

    for s_name in sorted_stages:
        tot_time = stage_totals[s_name]
        cnt = stage_counts.get(s_name, 1)
        avg_t = round(tot_time / cnt, 2)
        pct = round((tot_time / total_pipeline_time * 100), 1) if total_pipeline_time > 0 else 0.0
        stage_breakdown.append({
            "name": s_name,
            "avg_duration_s": avg_t,
            "total_duration_s": round(tot_time, 1),
            "run_count": cnt,
            "percentage": pct
        })

    avg_pipeline_duration = round(sum(job_durations) / len(job_durations), 1) if job_durations else 0.0

    return {
        "is_connected": is_connected,
        "endpoint": "http://localhost:8001",
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "running_jobs": running_jobs,
        "total_nodes_indexed": total_nodes,
        "total_relationships": total_edges,
        "total_parse_errors": total_errors,
        "tokens": {
            "llm_input_tokens": total_llm_input_tokens,
            "llm_output_tokens": total_llm_output_tokens,
            "llm_total_tokens": total_llm_tokens,
            "embedding_tokens": total_embedding_tokens,
            "total_tokens": total_parsing_tokens,
        },
        "costs": {
            "llm_model": "gpt-4o-mini",
            "embedding_model": "text-embedding-3-small",
            "llm_spend": round(llm_spend, 5),
            "embedding_spend": round(embedding_spend, 5),
            "total_cost": total_parsing_cost,
            "gpt4o_comparison_spend": total_gpt4o_spend,
        },
        "avg_pipeline_duration_s": avg_pipeline_duration,
        "stages": stage_breakdown,
        "repos": repos,
        "jobs": formatted_jobs,
    }


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

    unique_users = set(c.get("user_id") for c in conversations if c.get("user_id"))

    latencies: List[int] = []
    total_tool_calls = 0
    total_citations = 0
    tools_frequency: Dict[str, int] = defaultdict(int)
    citations_frequency: Dict[str, int] = defaultdict(int)

    models_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "latencies": [],
    })

    daily_timeline: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "date": "",
        "conversations": 0,
        "messages": 0,
        "tokens": 0,
        "cost": 0.0,
    })

    repo_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "repository_id": "",
        "conversation_count": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
    })

    users_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "user_id": "",
        "conversation_count": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "last_active": 0,
    })

    for c in conversations:
        u_id = c.get("user_id") or "anonymous"
        users_usage[u_id]["user_id"] = u_id
        users_usage[u_id]["conversation_count"] += 1
        users_usage[u_id]["total_tokens"] += c.get("total_tokens", 0)
        users_usage[u_id]["total_cost"] += c.get("total_cost", 0.0)
        users_usage[u_id]["last_active"] = max(users_usage[u_id]["last_active"], c.get("updated_at", 0))

        rep_ids = c.get("repository_ids", [])
        for r in rep_ids:
            if r:
                repo_usage[r]["repository_id"] = r
                repo_usage[r]["conversation_count"] += 1
                repo_usage[r]["total_tokens"] += c.get("total_tokens", 0)
                repo_usage[r]["total_cost"] += c.get("total_cost", 0.0)

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

        # Tool calls & citations extraction and accurate aggregation
        tools_list = meta.get("tool_calls") or payload.get("tool_calls") or m.get("tool_calls") or []
        citations_list = meta.get("citations") or payload.get("citations") or m.get("citations") or []

        tc_count = meta.get("tool_calls_count")
        if tc_count is None or tc_count == 0:
            tc_count = len(tools_list)
        total_tool_calls += tc_count

        cit_count = meta.get("citations_count")
        if cit_count is None or cit_count == 0:
            cit_count = len(citations_list)
        total_citations += cit_count

        for t in tools_list:
            if isinstance(t, dict):
                t_name = t.get("name") or t.get("tool_name") or "tool"
                tools_frequency[t_name] += 1
            elif isinstance(t, str):
                tools_frequency[t] += 1

        for cit in citations_list:
            if isinstance(cit, dict):
                raw_f = cit.get("file") or cit.get("file_path") or cit.get("element_name")
                if raw_f:
                    f_str = str(raw_f)
                    if ".jarvis_workspace" in f_str:
                        parts = f_str.split(".jarvis_workspace/")
                        if len(parts) > 1 and "/" in parts[1]:
                            f_str = parts[1].split("/", 1)[1]
                    citations_frequency[f_str] += 1

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

    models_summary = []
    for model_name, m_data in models_usage.items():
        m_lats = m_data.pop("latencies", [])
        m_data["model"] = model_name
        m_data["total_cost"] = round(m_data["total_cost"], 6)
        m_data["avg_latency_ms"] = round(sum(m_lats) / len(m_lats), 1) if m_lats else 0.0
        models_summary.append(m_data)
    models_summary.sort(key=lambda x: x["call_count"], reverse=True)

    timeline_list = sorted(daily_timeline.values(), key=lambda x: x["date"])
    for item in timeline_list:
        item["cost"] = round(item["cost"], 5)

    repos_summary = list(repo_usage.values())
    for r in repos_summary:
        r["total_cost"] = round(r["total_cost"], 5)
    repos_summary.sort(key=lambda x: x["conversation_count"], reverse=True)

    users_summary = list(users_usage.values())
    for u in users_summary:
        u["total_cost"] = round(u["total_cost"], 5)
    users_summary.sort(key=lambda x: x["total_cost"], reverse=True)

    costliest_turns = []
    for m in messages:
        if m.get("role") == "assistant":
            pl = m.get("payload") or {}
            st = pl.get("stats") or {}
            mt = pl.get("metadata") or {}
            cst = st.get("cost", 0.0)
            if cst > 0 or st.get("total_tokens", 0) > 0:
                t_list = mt.get("tool_calls") or pl.get("tool_calls") or []
                c_list = mt.get("citations") or pl.get("citations") or []
                costliest_turns.append({
                    "msg_id": m.get("msg_id") or m.get("id"),
                    "conversation_id": m.get("conversation_id"),
                    "cost": round(cst, 6),
                    "total_tokens": st.get("total_tokens", 0),
                    "input_tokens": st.get("input_tokens", 0),
                    "output_tokens": st.get("output_tokens", 0),
                    "latency_ms": mt.get("latency_ms"),
                    "model": mt.get("model", "gpt-4o"),
                    "tool_calls_count": mt.get("tool_calls_count", len(t_list)),
                    "citations_count": mt.get("citations_count", len(c_list)),
                    "tool_names": [t.get("name") if isinstance(t, dict) else str(t) for t in t_list],
                    "created_at": m.get("created_at"),
                })
    costliest_turns.sort(key=lambda x: x["cost"], reverse=True)
    costliest_turns = costliest_turns[:10]

    recent_convs = []
    for c in conversations[:20]:
        conv_id = c.get("conversation_id") or c.get("id")
        conv_tools = c.get("total_tool_calls")
        if conv_tools is None:
            conv_tools = sum(
                (msg.get("payload", {}).get("metadata", {}).get("tool_calls_count") or len(msg.get("payload", {}).get("metadata", {}).get("tool_calls", [])))
                for msg in messages if msg.get("conversation_id") == conv_id
            )
        conv_cits = c.get("total_citations")
        if conv_cits is None:
            conv_cits = sum(
                (msg.get("payload", {}).get("metadata", {}).get("citations_count") or len(msg.get("payload", {}).get("metadata", {}).get("citations", [])))
                for msg in messages if msg.get("conversation_id") == conv_id
            )
        recent_convs.append({
            "conversation_id": conv_id,
            "user_id": c.get("user_id"),
            "title": c.get("title"),
            "repository_ids": c.get("repository_ids", []),
            "turn_count": c.get("turn_count", 0),
            "total_tokens": c.get("total_tokens", 0),
            "total_cost": round(c.get("total_cost", 0.0), 5),
            "total_tool_calls": conv_tools,
            "total_citations": conv_cits,
            "status": c.get("status", "active"),
            "is_deleted": c.get("is_deleted", False),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        })

    # Fetch Parsing & Indexing Telemetry
    parsing_metrics = fetch_parsing_metrics()
    parsing_spend = parsing_metrics.get("costs", {}).get("total_cost", 0.0)
    parsing_tokens = parsing_metrics.get("tokens", {}).get("total_tokens", 0)

    combined_platform_spend = round(total_cost + parsing_spend, 5)
    combined_platform_tokens = total_tokens + parsing_tokens

    top_citations_list = sorted(
        [{"file": k, "count": v} for k, v in citations_frequency.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:15]

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
            "tools_breakdown": dict(tools_frequency),
            "top_citations": top_citations_list,
            # Platform overall
            "combined_platform_spend": combined_platform_spend,
            "combined_platform_tokens": combined_platform_tokens,
            "parsing_spend": parsing_spend,
            "chat_spend": round(total_cost, 6),
        },
        "database": {
            "database_name": all_data.get("database", "jarvis-conversations"),
            "is_connected": all_data.get("is_connected", False),
            "endpoint": all_data.get("endpoint", "Local Fallback Store"),
            "conversations_count": total_convs,
            "messages_count": total_msgs,
        },
        "parsing": parsing_metrics,
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
  <title>JARVIS Platform Telemetry & Analytics</title>
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
      --amber: #f59e0b;
      --indigo: #6366f1;
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
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .pill-blue { background: rgba(0, 120, 212, 0.15); color: var(--cyan); border: 1px solid rgba(0, 120, 212, 0.3); }
    .pill-green { background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.3); }
    .pill-orange { background: rgba(249, 115, 22, 0.15); color: var(--orange); border: 1px solid rgba(249, 115, 22, 0.3); }
    .pill-purple { background: rgba(168, 85, 247, 0.15); color: var(--purple); border: 1px solid rgba(168, 85, 247, 0.3); }
    .pill-indigo { background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); }
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
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
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
      font-size: 26px;
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
      overflow-x: auto;
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
      white-space: nowrap;
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
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    td {
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: var(--text);
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    code, .mono { font-family: 'Fira Code', monospace; }

    .bar-wrapper {
      background: rgba(255, 255, 255, 0.04);
      height: 24px;
      border-radius: 4px;
      overflow: hidden;
      padding: 0 4px;
      display: flex;
      align-items: center;
    }
    .bar-fill {
      height: 100%;
      border-radius: 3px;
      transition: width 0.3s ease;
    }
  </style>
</head>
<body>

  <div class="header">
    <div>
      <div class="header-title">
        <span style="font-size: 24px;">📊</span>
        <h1>JARVIS Platform Telemetry & Analytics</h1>
        <span class="pill pill-blue">Cosmos DB Live</span>
        <span class="pill pill-green" id="parserStatusPill">⚡ Parser Online</span>
      </div>
      <p style="font-size: 13px; color: var(--muted);">
        Enterprise analytics dashboard monitoring conversational sessions, code graph indexing, citations, autonomous tool calls, and platform spend.
      </p>
    </div>

    <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
      <a href="/explorer" target="_blank" class="btn">
        <span>🪐 Cosmos Explorer</span> ↗
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
      <span style="color: var(--muted); margin: 0 8px;">·</span>
      <span id="parserEndpoint">Parser: http://localhost:8001</span>
    </div>
    <div class="mono" style="font-size: 11px; color: var(--faint);" id="dbEndpoint">Endpoint: Local / Azure Cosmos DB</div>
  </div>

  <!-- Primary Top KPI Grid (9 Metric Cards) -->
  <div class="grid-kpis" id="kpiGrid">
    <div class="card" style="border-color: rgba(249, 115, 22, 0.4); background: linear-gradient(180deg, rgba(249,115,22,0.06), var(--card-bg));">
      <div class="card-top" style="color: var(--orange);"><span>Total Platform Investment</span><span>💰</span></div>
      <div class="card-value" id="kpiTotalPlatformSpend">$0.0000</div>
      <div class="card-sub" id="kpiPlatformSpendBreakdown">Chat: $0.00 · Parsing: $0.00</div>
    </div>
    <div class="card" style="border-color: rgba(168, 85, 247, 0.3);">
      <div class="card-top" style="color: var(--purple);"><span>Parsing & Indexing Spend</span><span>⚡</span></div>
      <div class="card-value" id="kpiParsingSpend">$0.0000</div>
      <div class="card-sub" id="kpiParsingTokens">0 tokens · gpt-4o-mini</div>
    </div>
    <div class="card" style="border-color: rgba(0, 120, 212, 0.3);">
      <div class="card-top" style="color: var(--cyan);"><span>Chat Conversation Spend</span><span>💬</span></div>
      <div class="card-value" id="kpiChatSpend">$0.0000</div>
      <div class="card-sub" id="kpiAvgCost">Avg $0.0000 / conv</div>
    </div>
    <div class="card" style="border-color: rgba(56, 189, 248, 0.35);">
      <div class="card-top" style="color: var(--cyan);"><span>Tool Calls & Citations</span><span>🔍</span></div>
      <div class="card-value"><span id="kpiTools">0</span> <span style="font-size: 16px; color: var(--muted);">calls</span> · <span id="kpiCitations" style="color: var(--orange);">0</span> <span style="font-size: 16px; color: var(--muted);">cites</span></div>
      <div class="card-sub" id="kpiToolsSub">Autonomous executions & code provenance</div>
    </div>
    <div class="card" style="border-color: rgba(16, 185, 129, 0.3);">
      <div class="card-top" style="color: var(--green);"><span>Code Nodes & Graph</span><span>🕸️</span></div>
      <div class="card-value" id="kpiNodesIndexed">0</div>
      <div class="card-sub" id="kpiEdgesIndexed">0 relationships · 0 errors</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Conversations</span><span>💬</span></div>
      <div class="card-value" id="kpiConvs">0</div>
      <div class="card-sub" id="kpiConvsBreakdown">0 active · 0 deleted</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Total Messages</span><span>📨</span></div>
      <div class="card-value" id="kpiMsgs">0</div>
      <div class="card-sub" id="kpiMsgsBreakdown">0 user · 0 assistant</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Avg Indexing Pipeline</span><span>⏳</span></div>
      <div class="card-value" id="kpiAvgPipeline">0.0s</div>
      <div class="card-sub" id="kpiJobsCount">0 indexing jobs run</div>
    </div>
    <div class="card">
      <div class="card-top"><span>Avg Chat Latency</span><span>⏱️</span></div>
      <div class="card-value" id="kpiLatency">0.0s</div>
      <div class="card-sub" id="kpiLatencyMs">0 ms average</div>
    </div>
  </div>

  <!-- Navigation Tabs -->
  <div class="tabs">
    <button class="tab-btn active" id="btnTabOverview" onclick="switchTab('overview')">📈 Overview & Trends</button>
    <button class="tab-btn" id="btnTabParsing" onclick="switchTab('parsing')">⚡ Parsing & Indexing Telemetry</button>
    <button class="tab-btn" id="btnTabConversations" onclick="switchTab('conversations')">💬 Conversations Audit</button>
    <button class="tab-btn" id="btnTabCosts" onclick="switchTab('costs')">💳 Costliest LLM Turns</button>
    <button class="tab-btn" id="btnTabRepos" onclick="switchTab('repos')">📁 Repositories & Developers</button>
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

    <!-- Dual-Card: Tool Invocations & Citations Intelligence Grid -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px;">
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <h3 style="font-size: 15px;">Autonomous Tool Invocations</h3>
          <span class="pill pill-purple" id="totalToolsBadge">0 calls</span>
        </div>
        <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Agent ReAct tool usage frequency across conversations</p>
        <div id="toolsContainer" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>

      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <h3 style="font-size: 15px;">Source Code Citations & Provenance</h3>
          <span class="pill pill-orange" id="totalCitationsBadge">0 cites</span>
        </div>
        <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Most frequently referenced source files and code entities</p>
        <div id="citationsContainer" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>
    </div>
  </div>

  <!-- Tab 2: Parsing & Indexing Telemetry -->
  <div id="tabParsing" style="display: none;">
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px;">
      <div class="card" style="border-left: 3px solid var(--purple);">
        <div class="card-top"><span>Indexing Jobs Health</span><span>📦</span></div>
        <div class="card-value" id="parseJobsHealth">0 / 0</div>
        <div class="card-sub" id="parseJobsHealthSub">0 completed · 0 failed · 0 running</div>
      </div>
      <div class="card" style="border-left: 3px solid var(--green);">
        <div class="card-top"><span>AST Parse Health</span><span>🛡️</span></div>
        <div class="card-value" id="parseErrorsTotal" style="color: var(--green);">0 Errors</div>
        <div class="card-sub" id="parseErrorsSub">100% clean AST tree extraction</div>
      </div>
      <div class="card" style="border-left: 3px solid var(--cyan);">
        <div class="card-top"><span>Token Breakdown</span><span>🪙</span></div>
        <div class="card-value" id="parseTotalTokens">0</div>
        <div class="card-sub" id="parseTokensSub">0 LLM tokens · 0 Embedding tokens</div>
      </div>
      <div class="card" style="border-left: 3px solid var(--orange);">
        <div class="card-top"><span>Model Cost Ratio</span><span>⚖️</span></div>
        <div class="card-value" id="parseModelRatio">$0.00 / $0.00</div>
        <div class="card-sub">gpt-4o-mini actual vs gpt-4o comparison</div>
      </div>
    </div>

    <!-- Pipeline Stage Latency Breakdown -->
    <div class="card" style="margin-bottom: 24px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
        <div>
          <h3 style="font-size: 15px;">Pipeline Stage Latency & Duration Breakdown</h3>
          <p style="font-size: 12px; color: var(--muted);">Average execution time and proportional runtime across 7-stage indexing pipeline</p>
        </div>
        <span class="pill pill-purple">7-Stage Micro-Pipeline</span>
      </div>
      <div id="stagesContainer" style="display: flex; flex-direction: column; gap: 12px;"></div>
    </div>

    <!-- Active Repositories in Graph -->
    <div class="card" style="margin-bottom: 24px;">
      <h3 style="font-size: 15px; margin-bottom: 4px;">Knowledge Graph Repositories</h3>
      <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Current active repositories parsed into Neo4j graph and Milvus vector collections</p>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Cluster</th>
              <th>Branch</th>
              <th>Graph Nodes</th>
              <th>Relationships</th>
              <th>Est. Index Spend</th>
              <th>Last Indexed</th>
            </tr>
          </thead>
          <tbody id="reposIndexedTbody"></tbody>
        </table>
      </div>
    </div>

    <!-- Indexing Jobs Audit Table -->
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
        <div>
          <h3 style="font-size: 15px;">Indexing Jobs Execution Audit</h3>
          <p style="font-size: 12px; color: var(--muted);">Comprehensive record of all indexing pipeline triggers, durations, and costs</p>
        </div>
        <input type="text" id="jobFilter" placeholder="Filter jobs by repo or status…" oninput="renderJobsTable()" style="padding: 8px 12px; border-radius: 8px; background: rgba(255,255,255,0.04); border: 1px solid var(--card-border); color: #fff; font-size: 12px; width: 280px; outline: none;">
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Repository</th>
              <th>Cluster</th>
              <th>Nodes</th>
              <th>Relationships</th>
              <th>Parse Errors</th>
              <th>Duration</th>
              <th>Est. Spend ($)</th>
              <th>Status</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody id="jobsAuditTbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Tab 3: Conversations -->
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
              <th>Tools / Citations</th>
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

  <!-- Tab 4: Costliest Turns -->
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
              <th>Tools / Citations</th>
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

  <!-- Tab 5: Repositories & Developers -->
  <div id="tabRepos" style="display: none;">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div class="card">
        <h3 style="font-size: 15px; margin-bottom: 4px;">Top Repositories (Chat Activity)</h3>
        <p style="font-size: 12px; color: var(--muted); margin-bottom: 16px;">Sessions and tokens consumed per codebase</p>
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

      // Parser status pill
      const p = d.parsing || {};
      const parserPill = document.getElementById('parserStatusPill');
      if (p.is_connected) {
        parserPill.textContent = '⚡ Parser Online (' + p.total_jobs + ' jobs)';
        parserPill.className = 'pill pill-green';
        document.getElementById('parserEndpoint').textContent = 'Parser: ' + p.endpoint;
      } else {
        parserPill.textContent = '⚡ Parser Offline';
        parserPill.className = 'pill pill-red';
      }

      // Top KPIs
      const combSpend = d.overview.combined_platform_spend || (d.overview.total_cost + (p.costs ? p.costs.total_cost : 0));
      document.getElementById('kpiTotalPlatformSpend').textContent = '$' + combSpend.toFixed(4);
      document.getElementById('kpiPlatformSpendBreakdown').textContent = 
        'Chat: $' + d.overview.total_cost.toFixed(4) + ' · Parsing: $' + (p.costs ? p.costs.total_cost.toFixed(4) : '0.00');

      document.getElementById('kpiParsingSpend').textContent = '$' + (p.costs ? p.costs.total_cost.toFixed(4) : '0.00');
      document.getElementById('kpiParsingTokens').textContent = 
        (p.tokens ? p.tokens.total_tokens.toLocaleString() : '0') + ' tokens · ' + (p.costs ? p.costs.llm_model : 'gpt-4o-mini');

      document.getElementById('kpiChatSpend').textContent = '$' + d.overview.total_cost.toFixed(4);
      document.getElementById('kpiAvgCost').textContent = 'Avg $' + d.overview.avg_cost_per_conv + ' / conv';

      // Tool calls and citations
      document.getElementById('kpiTools').textContent = d.overview.total_tool_calls;
      document.getElementById('kpiCitations').textContent = d.overview.total_citations;
      document.getElementById('kpiToolsSub').textContent = 
        d.overview.total_tool_calls + ' tool executions · ' + d.overview.total_citations + ' code citations';

      document.getElementById('kpiNodesIndexed').textContent = (p.total_nodes_indexed || 0).toLocaleString();
      document.getElementById('kpiEdgesIndexed').textContent = 
        (p.total_relationships || 0).toLocaleString() + ' relationships · ' + (p.total_parse_errors || 0) + ' errors';

      document.getElementById('kpiConvs').textContent = d.overview.total_conversations;
      document.getElementById('kpiConvsBreakdown').textContent = d.overview.active_conversations + ' active · ' + d.overview.deleted_conversations + ' soft-deleted';

      document.getElementById('kpiMsgs').textContent = d.overview.total_messages;
      document.getElementById('kpiMsgsBreakdown').textContent = d.overview.user_messages + ' user · ' + d.overview.assistant_messages + ' assistant';

      document.getElementById('kpiAvgPipeline').textContent = (p.avg_pipeline_duration_s || 0).toFixed(1) + 's';
      document.getElementById('kpiJobsCount').textContent = (p.total_jobs || 0) + ' indexing jobs run';

      document.getElementById('kpiLatency').textContent = (d.overview.avg_latency_ms / 1000).toFixed(2) + 's';
      document.getElementById('kpiLatencyMs').textContent = d.overview.avg_latency_ms.toLocaleString() + ' ms average';

      // Render Tab 1: Overview Timeline
      const tContainer = document.getElementById('timelineContainer');
      if (d.timeline.length === 0) {
        tContainer.innerHTML = '<div style="color: var(--faint); font-size: 12px;">No historical records yet.</div>';
      } else {
        const maxTokens = Math.max(...d.timeline.map(x => x.tokens), 1);
        tContainer.innerHTML = d.timeline.map(x => {
          const pct = Math.min(100, Math.max(8, (x.tokens / maxTokens) * 100));
          return `
            <div style="display: flex; align-items: center; gap: 10px; font-size: 12px;">
              <span class="mono" style="width: 85px; color: var(--muted);">${x.date}</span>
              <div class="bar-wrapper" style="flex: 1;">
                <div class="bar-fill" style="width: ${pct}%; background: linear-gradient(90deg, #0078d4, #38bdf8);"></div>
              </div>
              <span class="mono" style="width: 90px; text-align: right; font-weight: 600;">${x.tokens.toLocaleString()} toks</span>
              <span class="mono" style="width: 70px; text-align: right; color: var(--orange);">$${x.cost.toFixed(4)}</span>
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

      // Tools Breakdown
      document.getElementById('totalToolsBadge').textContent = d.overview.total_tool_calls + ' calls';
      const toolsContainer = document.getElementById('toolsContainer');
      const toolsObj = d.overview.tools_breakdown || {};
      const toolKeys = Object.keys(toolsObj);
      if (toolKeys.length === 0) {
        toolsContainer.innerHTML = `
          <div style="padding: 14px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border); font-size: 12px; color: var(--muted);">
            Available Tools registered: <code class="mono" style="color: var(--cyan);">search_graph_rag</code>, <code class="mono" style="color: var(--cyan);">search_by_name</code>, <code class="mono" style="color: var(--cyan);">read_file</code>, <code class="mono" style="color: var(--cyan);">list_directory</code>, <code class="mono" style="color: var(--cyan);">get_file_summary</code>.<br>
            <span style="color: var(--faint); font-size: 11px; margin-top: 4px; display: inline-block;">(No active calls recorded yet in prior turns)</span>
          </div>
        `;
      } else {
        const maxToolCalls = Math.max(...Object.values(toolsObj), 1);
        toolsContainer.innerHTML = toolKeys.map(k => {
          const cnt = toolsObj[k];
          const pct = Math.max(10, Math.min(100, (cnt / maxToolCalls) * 100));
          return `
            <div style="display: flex; align-items: center; gap: 10px; font-size: 12px;">
              <span class="mono" style="width: 140px; color: var(--cyan); font-weight: 500;">⚡ ${k}</span>
              <div class="bar-wrapper" style="flex: 1;">
                <div class="bar-fill" style="width: ${pct}%; background: linear-gradient(90deg, #6366f1, #a855f7);"></div>
              </div>
              <span class="mono" style="width: 60px; text-align: right; font-weight: 600;">${cnt} calls</span>
            </div>
          `;
        }).join('');
      }

      // Citations Breakdown
      document.getElementById('totalCitationsBadge').textContent = d.overview.total_citations + ' cites';
      const citContainer = document.getElementById('citationsContainer');
      const topCitations = d.overview.top_citations || [];
      if (topCitations.length === 0) {
        citContainer.innerHTML = `
          <div style="padding: 14px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border); font-size: 12px; color: var(--muted);">
            Code citations link AI assertions back to Neo4j nodes and repo files.<br>
            <span style="color: var(--faint); font-size: 11px; margin-top: 4px; display: inline-block;">(Citations are tracked per turn from hybrid retrieval and tool execution)</span>
          </div>
        `;
      } else {
        citContainer.innerHTML = topCitations.map(c => `
          <div style="padding: 10px 12px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center;">
            <div class="mono" style="font-size: 12px; color: var(--orange); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80%;">
              📎 ${c.file}
            </div>
            <span class="pill pill-orange" style="font-size: 10px;">${c.count} cites</span>
          </div>
        `).join('');
      }

      // Render Tab 2: Parsing Telemetry
      renderParsingTab(p);

      // Render Tab 3: Conversations
      renderConversations();

      // Render Tab 4: Costliest turns
      const cTbody = document.getElementById('costliestTbody');
      cTbody.innerHTML = d.costliest_turns.map(t => {
        const toolBadges = (t.tool_names && t.tool_names.length)
          ? t.tool_names.map(name => `<span class="pill pill-purple" style="font-size: 9px; margin-right: 4px;">⚡ ${name}</span>`).join('')
          : (t.tool_calls_count > 0 ? `<span class="pill pill-purple" style="font-size: 9px;">⚡ ${t.tool_calls_count}</span>` : '<span style="color: var(--faint); font-size: 11px;">None</span>');
        const citBadge = t.citations_count > 0
          ? `<span class="pill pill-orange" style="font-size: 9px; margin-left: 4px;">📎 ${t.citations_count}</span>`
          : '';
        return `
          <tr>
            <td class="mono" style="color: var(--muted); font-size: 11px;">${t.msg_id.slice(0, 8)}…</td>
            <td style="color: var(--cyan); font-weight: 500;">${t.model}</td>
            <td>${toolBadges}${citBadge}</td>
            <td class="mono" style="color: var(--muted);">${t.input_tokens.toLocaleString()}</td>
            <td class="mono" style="color: var(--muted);">${t.output_tokens.toLocaleString()}</td>
            <td class="mono" style="font-weight: 600;">${t.total_tokens.toLocaleString()}</td>
            <td class="mono">${t.latency_ms ? (t.latency_ms / 1000).toFixed(2) + 's' : '—'}</td>
            <td class="mono" style="color: var(--orange); font-weight: 700;">$${t.cost.toFixed(5)}</td>
          </tr>
        `;
      }).join('');

      // Render Tab 5: Repos & Users
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

    function renderParsingTab(p) {
      if (!p) return;

      document.getElementById('parseJobsHealth').textContent = p.completed_jobs + ' / ' + p.total_jobs;
      document.getElementById('parseJobsHealthSub').textContent = 
        p.completed_jobs + ' completed · ' + p.failed_jobs + ' failed · ' + p.running_jobs + ' running';

      const errs = p.total_parse_errors || 0;
      const errElem = document.getElementById('parseErrorsTotal');
      errElem.textContent = errs === 0 ? '0 Errors' : errs + ' Errors';
      errElem.style.color = errs === 0 ? 'var(--green)' : 'var(--red)';
      document.getElementById('parseErrorsSub').textContent = 
        errs === 0 ? '100% clean AST tree extraction across all files' : errs + ' file syntax/parse exceptions';

      const pToks = p.tokens || {};
      document.getElementById('parseTotalTokens').textContent = (pToks.total_tokens || 0).toLocaleString();
      document.getElementById('parseTokensSub').textContent = 
        (pToks.llm_total_tokens || 0).toLocaleString() + ' LLM toks · ' + (pToks.embedding_tokens || 0).toLocaleString() + ' Emb toks';

      const pCosts = p.costs || {};
      document.getElementById('parseModelRatio').textContent = 
        '$' + (pCosts.total_cost || 0).toFixed(4) + ' / $' + (pCosts.gpt4o_comparison_spend || 0).toFixed(4);

      const stagesContainer = document.getElementById('stagesContainer');
      const stages = p.stages || [];
      if (stages.length === 0) {
        stagesContainer.innerHTML = '<div style="color: var(--faint); font-size: 12px;">No stage execution records found.</div>';
      } else {
        const stageColors = {
          'Git Clone': '#38bdf8',
          'AST Parsing': '#10b981',
          'Graph Building': '#0078d4',
          'Neo4j Write': '#f59e0b',
          'Cross-Repo Linking': '#a855f7',
          'LLM Descriptions': '#f97316',
          'Milvus Embeddings': '#ec4899',
        };

        stagesContainer.innerHTML = stages.map(s => {
          const col = stageColors[s.name] || '#38bdf8';
          const pctWidth = Math.max(6, Math.min(100, s.percentage));
          return `
            <div style="display: flex; flex-direction: column; gap: 4px; font-size: 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: ${col}; display: flex; align-items: center; gap: 6px;">
                  <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${col};"></span>
                  ${s.name}
                </span>
                <span class="mono" style="color: var(--muted); font-size: 11px;">
                  avg <strong>${s.avg_duration_s.toFixed(2)}s</strong> (total ${s.total_duration_s.toFixed(1)}s over ${s.run_count} runs) · <strong style="color: #fff;">${s.percentage}%</strong>
                </span>
              </div>
              <div class="bar-wrapper">
                <div class="bar-fill" style="width: ${pctWidth}%; background: ${col};"></div>
              </div>
            </div>
          `;
        }).join('');
      }

      const reposTbody = document.getElementById('reposIndexedTbody');
      const repos = p.repos || [];
      if (repos.length === 0) {
        reposTbody.innerHTML = '<tr><td colspan="7" style="color: var(--faint);">No active repositories indexed.</td></tr>';
      } else {
        reposTbody.innerHTML = repos.map(r => {
          const spend = ((r.node_count || 0) * 0.000058).toFixed(4);
          const dt = r.indexed_at ? new Date(r.indexed_at * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : '—';
          return `
            <tr>
              <td class="mono" style="color: var(--cyan); font-weight: 600;">${r.repository_id}</td>
              <td><span class="pill pill-blue">${r.cluster_id || 'default'}</span></td>
              <td class="mono" style="color: var(--muted);">${r.branch || 'main'}</td>
              <td class="mono" style="font-weight: 600;">${(r.node_count || 0).toLocaleString()}</td>
              <td class="mono" style="color: var(--muted);">${(r.relationship_count || 0).toLocaleString()}</td>
              <td class="mono" style="color: var(--orange); font-weight: 600;">$${spend}</td>
              <td style="font-size: 11px; color: var(--muted);">${dt}</td>
            </tr>
          `;
        }).join('');
      }

      renderJobsTable();
    }

    function renderJobsTable() {
      if (!globalData || !globalData.parsing) return;
      const q = (document.getElementById('jobFilter').value || '').toLowerCase().trim();
      let jobs = globalData.parsing.jobs || [];
      if (q) {
        jobs = jobs.filter(j => 
          (j.repository_id || '').toLowerCase().includes(q) ||
          (j.cluster_id || '').toLowerCase().includes(q) ||
          (j.status || '').toLowerCase().includes(q) ||
          (j.job_id || '').toLowerCase().includes(q)
        );
      }
      const tbody = document.getElementById('jobsAuditTbody');
      if (jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="color: var(--faint);">No matching indexing jobs found.</td></tr>';
        return;
      }
      tbody.innerHTML = jobs.map(j => {
        const shortId = (j.job_id || '').slice(0, 8);
        const stPill = j.status === 'done' ? 'pill-green' : (j.status === 'failed' ? 'pill-red' : 'pill-orange');
        const dt = j.created_at ? new Date(j.created_at * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : '—';
        return `
          <tr>
            <td class="mono" style="color: var(--muted); font-size: 11px;" title="${j.job_id}">${shortId}…</td>
            <td class="mono" style="font-weight: 500; color: var(--cyan);">${j.repository_id}</td>
            <td><span class="pill pill-blue" style="font-size: 9px;">${j.cluster_id || 'default'}</span></td>
            <td class="mono" style="font-weight: 600;">${(j.node_count || 0).toLocaleString()}</td>
            <td class="mono" style="color: var(--muted);">${(j.relationship_count || 0).toLocaleString()}</td>
            <td>
              <span class="pill ${j.parse_errors > 0 ? 'pill-red' : 'pill-green'}" style="font-size: 10px;">
                ${j.parse_errors} errors
              </span>
            </td>
            <td class="mono">${j.duration_s ? j.duration_s + 's' : '—'}</td>
            <td class="mono" style="color: var(--orange); font-weight: 600;">$${(j.estimated_cost || 0).toFixed(4)}</td>
            <td><span class="pill ${stPill}">${j.status || 'queued'}</span></td>
            <td style="font-size: 11px; color: var(--muted);">${dt}</td>
          </tr>
        `;
      }).join('');
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
          <td style="max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500;">
            ${c.title || 'Untitled Session'}
          </td>
          <td style="color: var(--muted); font-size: 12px;">${c.user_id}</td>
          <td>
            ${(c.repository_ids || []).map(r => `<span class="pill pill-blue" style="font-size: 9px; margin-right: 4px;">${r}</span>`).join('') || '<span style="color: var(--faint);">None</span>'}
          </td>
          <td class="mono">${c.turn_count}</td>
          <td>
            <span class="pill pill-purple" style="font-size: 10px; margin-right: 4px;">⚡ ${c.total_tool_calls || 0}</span>
            <span class="pill pill-orange" style="font-size: 10px;">📎 ${c.total_citations || 0}</span>
          </td>
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
      
      const tabBtnMap = {
        'overview': 'btnTabOverview',
        'parsing': 'btnTabParsing',
        'conversations': 'btnTabConversations',
        'costs': 'btnTabCosts',
        'repos': 'btnTabRepos'
      };
      const activeBtn = document.getElementById(tabBtnMap[tabId]);
      if (activeBtn) activeBtn.classList.add('active');

      document.getElementById('tabOverview').style.display = tabId === 'overview' ? 'block' : 'none';
      document.getElementById('tabParsing').style.display = tabId === 'parsing' ? 'block' : 'none';
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
