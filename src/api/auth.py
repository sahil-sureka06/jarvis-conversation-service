"""
Admin Authentication and Access Control for JARVIS Conversation Service & Analytics.
Only admins with the Master Admin Password (default: Sahil@0612) can access analytics and data explorer.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

ADMIN_PASSWORD = os.getenv("ADMIN_MASTER_PASSWORD", "Sahil@0612").strip()
SECRET_SALT = os.getenv("AUTH_SECRET", "jarvis-admin-telemetry-secret-key-2026")

admin_auth_router = APIRouter(tags=["admin-auth"])


class AdminAuthRequest(BaseModel):
    password: str


def make_admin_token() -> str:
    timestamp = str(int(time.time()))
    signature = hmac.new(
        f"{SECRET_SALT}:{ADMIN_PASSWORD}".encode(),
        f"admin:{timestamp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{timestamp}.{signature}"


def is_valid_admin_token(token: Optional[str]) -> bool:
    if not token or "." not in token:
        return False
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        timestamp_str, signature = parts
        timestamp = int(timestamp_str)
        # Token valid for 7 days
        if time.time() - timestamp > 7 * 86400:
            return False
        expected = hmac.new(
            f"{SECRET_SALT}:{ADMIN_PASSWORD}".encode(),
            f"admin:{timestamp_str}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def is_admin_authenticated(request: Request) -> bool:
    # 1. Check session cookie
    cookie_token = request.cookies.get("jarvis_admin_session")
    if is_valid_admin_token(cookie_token):
        return True

    # 2. Check header
    header_pass = request.headers.get("X-Admin-Password")
    if header_pass and header_pass == ADMIN_PASSWORD:
        return True

    # 3. Check query param
    query_auth = request.query_params.get("auth")
    if query_auth and (query_auth == ADMIN_PASSWORD or is_valid_admin_token(query_auth)):
        return True

    return False


def require_admin_api(request: Request):
    """Dependency for JSON API endpoints: returns 401 if unauthenticated."""
    if not is_admin_authenticated(request):
        raise HTTPException(
            status_code=401,
            detail="Admin access required. Provide valid admin credentials.",
        )


@admin_auth_router.post("/api/admin/auth", summary="Authenticate Admin")
async def admin_auth(payload: AdminAuthRequest, response: Response):
    submitted_pass = payload.password.strip()
    if submitted_pass != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect admin master password.")

    token = make_admin_token()
    res = JSONResponse(content={"success": True, "token": token})
    res.set_cookie(
        key="jarvis_admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=7 * 86400,
        path="/",
    )
    return res


@admin_auth_router.post("/api/admin/logout", summary="Logout Admin")
async def admin_logout(response: Response):
    res = JSONResponse(content={"success": True, "message": "Admin logged out"})
    res.delete_cookie("jarvis_admin_session", path="/")
    return res


def render_admin_gatekeeper(portal_name: str, return_url: str) -> str:
    """Renders a sleek security challenge screen when visiting /analytics or /explorer."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>JARVIS Admin Security Gate</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background: radial-gradient(ellipse at 50% 20%, rgba(239, 68, 68, 0.08) 0%, #08090d 75%);
      color: #f3f4f6;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      width: 100%;
      max-width: 420px;
      background: rgba(17, 20, 28, 0.92);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 20px;
      padding: 36px 32px;
      box-shadow: 0 25px 60px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.04);
      text-align: center;
    }}
    .icon {{
      width: 58, height: 58px;
      width: 58px;
      height: 58px;
      border-radius: 16px;
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 18px;
      color: #ef4444;
      box-shadow: 0 0 30px rgba(239, 68, 68, 0.2);
    }}
    h1 {{
      font-size: 21px;
      font-weight: 600;
      color: #f9fafb;
      margin-bottom: 8px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 20px;
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.25);
      color: #f87171;
      font-size: 11px;
      font-weight: 600;
      margin-bottom: 12px;
    }}
    p {{
      font-size: 13px;
      color: #9ca3af;
      line-height: 1.5;
      margin-bottom: 24px;
    }}
    .input-group {{
      margin-bottom: 18px;
      text-align: left;
    }}
    label {{
      display: block;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #cbd5e1;
      margin-bottom: 8px;
    }}
    input {{
      width: 100%;
      background: rgba(10, 12, 16, 0.85);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 10px;
      padding: 12px 14px;
      color: #fff;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
    }}
    input:focus {{
      border-color: #ef4444;
      box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2);
    }}
    button {{
      width: 100%;
      background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%);
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 13px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
      transition: opacity 0.2s;
    }}
    button:disabled {{
      opacity: 0.6;
      cursor: not-allowed;
    }}
    .err-msg {{
      display: none;
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #fca5a5;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 12px;
      margin-bottom: 16px;
      text-align: left;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
      </svg>
    </div>
    <h1>Admin Security Gate</h1>
    <div class="badge">🔒 RESTRICTED: {portal_name.upper()}</div>
    <p>This portal contains sensitive platform telemetry, conversation stores, and database controls. Enter the Master Admin Password to continue.</p>

    <div id="errMsg" class="err-msg"></div>

    <form id="adminForm" onsubmit="handleAdminLogin(event)">
      <div class="input-group">
        <label for="adminPass">Master Admin Password</label>
        <input id="adminPass" type="password" placeholder="Enter admin password…" autofocus required autocomplete="current-password" />
      </div>
      <button id="btnSubmit" type="submit">Unlock Admin Portal →</button>
    </form>
  </div>

  <script>
    async function handleAdminLogin(e) {{
      e.preventDefault();
      const pass = document.getElementById("adminPass").value;
      const errBox = document.getElementById("errMsg");
      const btn = document.getElementById("btnSubmit");

      errBox.style.display = "none";
      btn.disabled = true;
      btn.innerText = "Authenticating…";

      try {{
        const res = await fetch("/api/admin/auth", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ password: pass }})
        }});

        if (!res.ok) {{
          const data = await res.json().catch(() => ({{}}));
          throw new Error(data.detail || "Invalid admin password. Access denied.");
        }}

        // Success: Reload current page
        window.location.href = "{return_url}";
      }} catch (err) {{
        errBox.innerText = err.message || "Access denied.";
        errBox.style.display = "block";
        btn.disabled = false;
        btn.innerText = "Unlock Admin Portal →";
      }}
    }}
  </script>
</body>
</html>"""
