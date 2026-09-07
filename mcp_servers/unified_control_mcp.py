#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Unified Control Server"""

import json
import sys
import os
import time
import platform
import subprocess
try:
    import psutil
except ImportError:
    psutil = None
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MCP_DIR = Path(__file__).parent
START_TIME = time.time()
TOOLS = [
    {"name": "ctz_control_status", "description": "Get overall CTZ system status", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ctz_control_restart_mcp", "description": "Log a restart request for a specific MCP server", "inputSchema": {"type": "object", "properties": {"server": {"type": "string"}}, "required": ["server"]}},
    {"name": "ctz_control_run_all", "description": "Run a health check on all MCP servers", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ctz_control_dashboard", "description": "Return full dashboard data (status, memory, servers)", "inputSchema": {"type": "object", "properties": {}}},
]


def _check_servers():
    results = []
    for f in sorted(MCP_DIR.glob("*_mcp.py")):
        name = f.stem.replace("_mcp", "")
        try:
            p = subprocess.run([sys.executable, "-m", "py_compile", str(f)], capture_output=True, text=True, timeout=10)
            tool_count = sum(1 for _ in open(f, encoding="utf-8") if '"name": "ctz_')
            results.append({"name": name, "file": f.name, "tools": tool_count, "compiles": p.returncode == 0, "status": "healthy" if p.returncode == 0 else "unhealthy"})
        except Exception as e:
            results.append({"name": name, "status": "error", "error": str(e)})
    return results


def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-control", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            if name == "ctz_control_status":
                servers = _check_servers()
                healthy = sum(1 for s in servers if s["status"] == "healthy")
                ram_percent = psutil.virtual_memory().percent if psutil else 0.0
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"timestamp": datetime.now().isoformat(), "platform": platform.system(), "uptime_seconds": round(time.time() - START_TIME, 1), "ram_percent": ram_percent, "mcp_servers": {"total": len(servers), "healthy": healthy, "unhealthy": len(servers) - healthy}, "overall": "healthy" if healthy == len(servers) else "degraded"}, indent=2)}]}}
            elif name == "ctz_control_restart_mcp":
                server = args["server"]
                log_dir = PROJECT_ROOT / "data" / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                entry = {"timestamp": datetime.now().isoformat(), "action": "restart_requested", "server": server, "status": "logged"}
                with open(log_dir / "restart_requests.jsonl", "a") as f:
                    f.write(json.dumps(entry) + "\n")
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"server": server, "restart_logged": True, "note": "Restart request logged. Manual restart required."})}]}}
            elif name == "ctz_control_run_all":
                servers = _check_servers()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"timestamp": datetime.now().isoformat(), "servers": servers, "total": len(servers), "healthy": sum(1 for s in servers if s["status"] == "healthy")}, indent=2)}]}}
            elif name == "ctz_control_dashboard":
                servers = _check_servers()
                healthy = sum(1 for s in servers if s["status"] == "healthy")
                if psutil:
                    vm = psutil.virtual_memory()
                    swap = psutil.swap_memory()
                    mem_data = {"ram_total_gb": round(vm.total / (1024**3), 2), "ram_used_gb": round(vm.used / (1024**3), 2), "ram_percent": vm.percent, "swap_percent": swap.percent}
                else:
                    mem_data = {"note": "Install psutil for real-time memory stats", "ram_percent": 0.0}
                dashboard = {
                    "timestamp": datetime.now().isoformat(),
                    "system": {"platform": platform.system(), "python": sys.version.split()[0], "uptime_seconds": round(time.time() - START_TIME, 1)},
                    "memory": mem_data,
                    "mcp_servers": {"total": len(servers), "healthy": healthy, "unhealthy": len(servers) - healthy, "servers": servers},
                    "overall_status": "healthy" if healthy == len(servers) else "degraded",
                }
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(dashboard, indent=2)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown method"}}


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = handle_request(json.loads(line.strip()))
            if r:
                sys.stdout.write(json.dumps(r) + "\n")
                sys.stdout.flush()
        except:
            pass
