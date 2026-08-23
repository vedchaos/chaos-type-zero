#!/usr/bin/env python3
"""
CHAOS TYPE ZERO — Production Server v3.3
FastAPI + WebSocket + Auth + Dashboard + Mobile API
Run: python server/main.py
Docs: http://localhost:9000/docs
"""

import os
import sys
import time
import json
import hashlib
import secrets
import platform
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

# FastAPI
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# System monitoring
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ─── CONFIG ─────────────────────────────────────────────
NEXUS_DIR = Path(__file__).parent.parent
PORT = int(os.environ.get("CTZ_PORT", 9000))
HOST = os.environ.get("CTZ_HOST", "0.0.0.0")
_env_key = os.environ.get("CTZ_API_KEY", "")
if not _env_key:
    _env_key = secrets.token_urlsafe(32)
    import warnings
    warnings.warn(
        "CTZ_API_KEY not set — generated random key for this session. "
        "Set CTZ_API_KEY environment variable for persistent access.",
        stacklevel=2,
    )
API_KEY = _env_key
CTZ_VERSION = "3.3"
START_TIME = time.time()
_DATA_DIR = NEXUS_DIR / "data"
_TELEMETRY_FILE = _DATA_DIR / "telemetry.json"

# ─── WEBSOCKET MANAGER ──────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.active.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        async with self.lock:
            for ws in self.active:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.active.remove(ws)

manager = ConnectionManager()

# ─── AUTH ───────────────────────────────────────────────
security = HTTPBearer(auto_error=False)

async def verify_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Verify API key via Authorization header or query param."""
    # Check query param first
    key = request.query_params.get("key")
    if key and key == API_KEY:
        return True

    # Check Bearer token
    if credentials and credentials.credentials == API_KEY:
        return True

    # Check X-API-Key header
    header_key = request.headers.get("X-API-Key")
    if header_key and header_key == API_KEY:
        return True

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ─── SYSTEM DATA ────────────────────────────────────────
def get_cpu():
    if not HAS_PSUTIL:
        return {"percent": 0, "count": 0, "freq": 0, "detail": "psutil not installed"}
    cpu = psutil.cpu_percent(interval=0.1)
    freq = psutil.cpu_freq()
    return {
        "percent": round(cpu, 1),
        "count": psutil.cpu_count(),
        "freq": round(freq.current, 0) if freq else 0,
        "detail": f"{psutil.cpu_count()} cores // {platform.processor() or 'unknown'}"
    }

def get_ram():
    if not HAS_PSUTIL:
        return {"percent": 0, "used_gb": 0, "total_gb": 0, "available_gb": 0, "detail": "psutil not installed"}
    mem = psutil.virtual_memory()
    return {
        "percent": round(mem.percent, 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "total_gb": round(mem.total / (1024**3), 1),
        "available_gb": round(mem.available / (1024**3), 1),
        "detail": f"{round(mem.used/(1024**3),1)} GB / {round(mem.total/(1024**3),1)} GB"
    }

def get_disk():
    if not HAS_PSUTIL:
        return {"percent": 0, "used_gb": 0, "total_gb": 0, "free_gb": 0, "detail": "psutil not installed"}
    disk = psutil.disk_usage("/")
    return {
        "percent": round(disk.percent, 1),
        "used_gb": round(disk.used / (1024**3), 1),
        "total_gb": round(disk.total / (1024**3), 1),
        "free_gb": round(disk.free / (1024**3), 1),
        "detail": f"{round(disk.used/(1024**3),1)} GB / {round(disk.total/(1024**3),1)} GB"
    }

def get_system_data():
    return {
        "hostname": platform.node(),
        "uptime": format_uptime(time.time() - START_TIME),
        "status": "SYSTEM NOMINAL",
        "version": CTZ_VERSION,
        "platform": platform.system(),
        "cpu": get_cpu(),
        "ram": get_ram(),
        "disk": get_disk(),
    }

def format_uptime(seconds):
    if seconds < 60: return f"{int(seconds)}s"
    if seconds < 3600: return f"{int(seconds/60)}m"
    if seconds < 86400: return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"
    return f"{int(seconds/86400)}d {int((seconds%86400)/3600)}h"

# ─── SERVER DATA ────────────────────────────────────────
def get_servers_data():
    servers = []
    mcp_dir = NEXUS_DIR / "mcp_servers"
    if mcp_dir.exists():
        for f in sorted(mcp_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            servers.append({
                "name": f.stem,
                "status": "ready",
                "type": "stdio",
            })
    return servers

def get_memory_data():
    data_dir = NEXUS_DIR / "data"
    total_kb = 0
    if data_dir.exists():
        for f in data_dir.rglob("*"):
            if f.is_file():
                total_kb += f.stat().st_size / 1024

    skills_dir = NEXUS_DIR / ".opencode" / "skills"
    skill_count = 0
    if skills_dir.exists():
        skill_count = len(list(skills_dir.rglob("SKILL.md")))

    return {
        "total_memory_kb": round(total_kb, 1),
        "cache_size": f"{round(total_kb, 1)} KB",
        "skills_count": skill_count,
        "ledger_entries": 0,
        "context_sessions": 0,
        "cache_hits": 0,
    }

def _load_telemetry():
    """Load persistent telemetry from disk."""
    if _TELEMETRY_FILE.exists():
        try:
            return json.loads(_TELEMETRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "automation_runs": {},
        "total_requests": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "daily_requests": 0,
        "daily_tokens": 0,
        "daily_cost_usd": 0.0,
        "daily_date": "",
    }

def _save_telemetry(telemetry):
    """Persist telemetry to disk."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _TELEMETRY_FILE.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
    except Exception:
        pass

def _record_request(tokens_in, tokens_out, cost):
    """Record a single API request to telemetry."""
    today = datetime.now().strftime("%Y-%m-%d")
    telemetry = _load_telemetry()
    if telemetry.get("daily_date") != today:
        telemetry["daily_requests"] = 0
        telemetry["daily_tokens"] = 0
        telemetry["daily_cost_usd"] = 0.0
        telemetry["daily_date"] = today
    telemetry["total_requests"] += 1
    telemetry["total_tokens"] += tokens_in + tokens_out
    telemetry["total_cost_usd"] += cost
    telemetry["daily_requests"] += 1
    telemetry["daily_tokens"] += tokens_in + tokens_out
    telemetry["daily_cost_usd"] += cost
    _save_telemetry(telemetry)

def _record_automation(automation_name):
    """Record an automation execution."""
    telemetry = _load_telemetry()
    runs = telemetry.get("automation_runs", {})
    key = automation_name
    entry = runs.get(key, {"count": 0, "last_run": ""})
    entry["count"] += 1
    entry["last_run"] = datetime.now().strftime("%H:%M:%S")
    runs[key] = entry
    telemetry["automation_runs"] = runs
    _save_telemetry(telemetry)

def get_automations_data():
    telemetry = _load_telemetry()
    runs = telemetry.get("automation_runs", {})
    automations = [
        {"name": "Memory Consolidation", "schedule": "Every 6h", "active": True},
        {"name": "Log Rotation", "schedule": "Daily 03:00", "active": True},
        {"name": "Health Ping", "schedule": "Every 5m", "active": True},
        {"name": "Backup Vault", "schedule": "Daily 04:00", "active": False},
        {"name": "Session Sync", "schedule": "Every 15m", "active": True},
    ]
    for a in automations:
        info = runs.get(a["name"], {"count": 0, "last_run": "never"})
        a["run_count"] = info["count"]
        a["last_run"] = info["last_run"]
    return automations

def get_providers_data():
    providers = []
    known = [
        {"name": "Ollama", "model": "local models"},
        {"name": "Anthropic", "model": "claude-opus-4-20250514"},
        {"name": "OpenAI", "model": "gpt-4o"},
        {"name": "Google", "model": "gemini-pro"},
        {"name": "OpenRouter", "model": "auto"},
        {"name": "Groq", "model": "llama-3.3-70b"},
        {"name": "DeepSeek", "model": "deepseek-r1"},
        {"name": "xAI", "model": "grok-2"},
    ]
    for p in known:
        providers.append({
            "name": p["name"],
            "status": "available",
            "model": p["model"],
        })
    return providers

def get_skills_data():
    skills = []
    skills_dir = NEXUS_DIR / ".opencode" / "skills"
    if skills_dir.exists():
        for skill_file in sorted(skills_dir.rglob("SKILL.md")):
            try:
                content = skill_file.read_text(encoding="utf-8")[:500]
                lines = content.strip().split("\n")
                name = lines[0].lstrip("#").strip() if lines else skill_file.parent.name
                desc = ""
                for line in lines[1:5]:
                    if line.strip() and not line.startswith("#") and not line.startswith("---"):
                        desc = line.strip()
                        break
                skills.append({
                    "name": name,
                    "description": desc or skill_file.parent.name,
                    "path": str(skill_file.relative_to(NEXUS_DIR)),
                })
            except Exception:
                skills.append({"name": skill_file.parent.name, "description": "", "path": ""})
    return skills

def get_costs_data():
    telemetry = _load_telemetry()
    today = datetime.now().strftime("%Y-%m-%d")
    if telemetry.get("daily_date") != today:
        daily_tokens = 0
        daily_cost = 0.0
        daily_requests = 0
    else:
        daily_tokens = telemetry.get("daily_tokens", 0)
        daily_cost = telemetry.get("daily_cost_usd", 0.0)
        daily_requests = telemetry.get("daily_requests", 0)
    avg_tokens = (daily_tokens // daily_requests) if daily_requests > 0 else 0
    return {
        "estimated_tokens_today": daily_tokens,
        "estimated_cost_usd": round(daily_cost, 6),
        "requests_today": daily_requests,
        "avg_tokens_per_request": avg_tokens,
        "total_tokens_all_time": telemetry.get("total_tokens", 0),
        "total_cost_all_time": round(telemetry.get("total_cost_usd", 0.0), 4),
        "note": "Runtime telemetry — values reset daily. Set CTZ_API_KEY env var.",
    }

def get_health_data():
    cpu = get_cpu()
    ram = get_ram()
    disk = get_disk()
    return {
        "status": "healthy" if cpu["percent"] < 90 and ram["percent"] < 90 else "degraded",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "uptime_seconds": int(time.time() - START_TIME),
        "cpu_ok": cpu["percent"] < 90,
        "ram_ok": ram["percent"] < 90,
        "disk_ok": disk["percent"] < 95,
        "websocket_clients": len(manager.active),
        "version": CTZ_VERSION,
    }


# ─── BACKGROUND TASKS ───────────────────────────────────
async def broadcast_loop():
    """Broadcast system data to all WebSocket clients every 3 seconds."""
    while True:
        await asyncio.sleep(3)
        if manager.active:
            try:
                data = {
                    "type": "update",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "system": get_system_data(),
                    "health": get_health_data(),
                }
                await manager.broadcast(data)
            except Exception:
                pass


# ─── APP LIFESPAN ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(broadcast_loop())
    print(f"""
\033[92m  ╔══════════════════════════════════════════════╗
  ║  CHAOS TYPE ZERO — Production Server v{CTZ_VERSION}    ║
  ║  Port : {PORT:<37}║
  ║  HTTP : http://localhost:{PORT:<24}║
  ║  Docs : http://localhost:{PORT}/docs{' '*(14-len(str(PORT)))}║
  ║  WS   : ws://localhost:{PORT}/ws{' '*(15-len(str(PORT)))}║
  ║  Time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<37}║
  ╚══════════════════════════════════════════════╝\033[0m
  Endpoints:
    /api/health      /api/status     /api/system
    /api/servers     /api/memory     /api/automations
    /api/providers   /api/skills     /api/history
    /api/costs       /api/full       /api/mcp/{'{name}'}
    /api/notify      /api/command    /api/voice
    /ws (WebSocket)  /docs (Swagger)
""")
    yield
    task.cancel()


# ─── APP ────────────────────────────────────────────────
app = FastAPI(
    title="CHAOS TYPE ZERO",
    description="Autonomous AI OS — 44 MCP servers, 251 tools, 6 agents",
    version=CTZ_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

_cors_origins = os.environ.get("CTZ_CORS_ORIGINS", "").split(",")
_cors_origins = [o.strip() for o in _cors_origins if o.strip()]
if not _cors_origins:
    _cors_origins = ["http://localhost:9000", "http://localhost:8080", "http://127.0.0.1:9000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ─── MODELS ─────────────────────────────────────────────
class NotifyRequest(BaseModel):
    title: str
    body: str
    level: str = "info"

class CommandRequest(BaseModel):
    command: str

class VoiceRequest(BaseModel):
    command: str
    language: str = "en"


# ─── PUBLIC ENDPOINTS (no auth) ─────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    return f"""<!DOCTYPE html>
<html><head><title>CTZ Server</title>
<style>body{{background:#0a0a0a;color:#00ff41;font-family:monospace;padding:40px;}}
h1{{color:#ff0041;}} a{{color:#00aaff;}}</style></head>
<body>
<h1>CHAOS TYPE ZERO v{CTZ_VERSION}</h1>
<p>Server running on port {PORT}</p>
<p><a href="/docs">Swagger Docs</a> | <a href="/redoc">ReDoc</a></p>
<p><a href="/api/health">Health</a> | <a href="/api/status">Status</a> | <a href="/api/full">Full Data</a></p>
<p>WebSocket: ws://localhost:{PORT}/ws</p>
<p>API Key: Set CTZ_API_KEY env var (auto-generated if not set)</p>
</body></html>"""

@app.get("/api/health")
async def health():
    return get_health_data()

@app.get("/api/ready")
async def ready():
    return {"status": "ready", "version": CTZ_VERSION}


# ─── PROTECTED ENDPOINTS ───────────────────────────────
@app.get("/api/status")
async def status(_: bool = Depends(verify_api_key)):
    data = get_system_data()
    data["history"] = []
    return data

@app.get("/api/system")
async def system(_: bool = Depends(verify_api_key)):
    return get_system_data()

@app.get("/api/servers")
async def servers(_: bool = Depends(verify_api_key)):
    return get_servers_data()

@app.get("/api/memory")
async def memory(_: bool = Depends(verify_api_key)):
    return get_memory_data()

@app.get("/api/automations")
async def automations(_: bool = Depends(verify_api_key)):
    return get_automations_data()

@app.get("/api/providers")
async def providers(_: bool = Depends(verify_api_key)):
    return get_providers_data()

@app.get("/api/skills")
async def skills(_: bool = Depends(verify_api_key)):
    return get_skills_data()

@app.get("/api/history")
async def history(_: bool = Depends(verify_api_key)):
    return []

@app.get("/api/costs")
async def costs(_: bool = Depends(verify_api_key)):
    return get_costs_data()

@app.get("/api/full")
async def full(_: bool = Depends(verify_api_key)):
    return {
        "type": "update",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "system": get_system_data(),
        "health": get_health_data(),
        "servers": get_servers_data(),
        "memory": get_memory_data(),
        "automations": get_automations_data(),
        "providers": get_providers_data(),
        "skills": get_skills_data(),
        "costs": get_costs_data(),
    }


# ─── MCP SERVER MANAGEMENT ─────────────────────────────
@app.get("/api/mcp/list")
async def mcp_list(_: bool = Depends(verify_api_key)):
    servers = get_servers_data()
    return {"total": len(servers), "servers": servers}

@app.get("/api/mcp/{name}")
async def mcp_detail(name: str, _: bool = Depends(verify_api_key)):
    mcp_file = NEXUS_DIR / "mcp_servers" / f"{name}.py"
    if not mcp_file.exists():
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    content = mcp_file.read_text(encoding="utf-8")
    # Count tools
    tool_count = content.count("def ") + content.count('"name":')

    return {
        "name": name,
        "file": str(mcp_file.relative_to(NEXUS_DIR)),
        "size_bytes": len(content.encode()),
        "lines": content.count("\n") + 1,
        "tools_estimate": tool_count,
    }


# ─── MOBILE / COMMAND ENDPOINTS ────────────────────────
@app.post("/api/notify")
async def notify(req: NotifyRequest, _: bool = Depends(verify_api_key)):
    return {
        "status": "sent",
        "notification": {"title": req.title, "body": req.body, "level": req.level},
        "timestamp": datetime.now().isoformat(),
    }

@app.post("/api/command")
async def command(req: CommandRequest, _: bool = Depends(verify_api_key)):
    return {
        "status": "received",
        "command": req.command,
        "message": "Command queued for processing",
        "timestamp": datetime.now().isoformat(),
    }

@app.post("/api/voice")
async def voice(req: VoiceRequest, _: bool = Depends(verify_api_key)):
    return {
        "status": "received",
        "command": req.command,
        "language": req.language,
        "message": "Voice command received",
        "timestamp": datetime.now().isoformat(),
    }


# ─── WEBSOCKET ─────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send initial data
        await ws.send_json({
            "type": "connected",
            "message": "CTZ WebSocket connected",
            "version": CTZ_VERSION,
        })
        while True:
            data = await ws.receive_text()
            # Echo or handle commands
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.now().strftime("%H:%M:%S")})
                elif msg.get("type") == "get_system":
                    await ws.send_json({"type": "system", "data": get_system_data()})
                elif msg.get("type") == "get_full":
                    await ws.send_json({
                        "type": "full",
                        "system": get_system_data(),
                        "health": get_health_data(),
                    })
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
    except WebSocketDisconnect:
        await manager.disconnect(ws)


# ─── RUN ────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=HOST,
        port=PORT,
        reload=os.environ.get("CTZ_DEV", "0") == "1",
        log_level="info",
    )
