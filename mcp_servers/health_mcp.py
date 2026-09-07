#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Health Monitoring Server"""

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
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MCP_DIR = Path(__file__).parent
TOOLS = [
    {"name": "ctz_health_check", "description": "Full health check of all CTZ systems", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ctz_health_db", "description": "Check database health (SQLite files)", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ctz_health_memory", "description": "Check memory usage of CTZ processes", "inputSchema": {"type": "object", "properties": {}}},
]


def _check_mcp_servers():
    results = []
    for f in sorted(MCP_DIR.glob("*_mcp.py")):
        name = f.stem.replace("_mcp", "")
        try:
            p = subprocess.run([sys.executable, "-m", "py_compile", str(f)], capture_output=True, text=True, timeout=10)
            results.append({"server": name, "compiles": p.returncode == 0, "status": "healthy" if p.returncode == 0 else "unhealthy"})
        except Exception as e:
            results.append({"server": name, "compiles": False, "status": "error", "error": str(e)})
    return results


def _check_databases():
    dbs = []
    for f in PROJECT_ROOT.rglob("*.db"):
        try:
            size_mb = round(f.stat().st_size / (1024 * 1024), 2)
            dbs.append({"path": str(f.relative_to(PROJECT_ROOT)), "size_mb": size_mb, "status": "ok"})
        except Exception as e:
            dbs.append({"path": str(f), "status": "error", "error": str(e)})
    for f in PROJECT_ROOT.rglob("*.sqlite"):
        try:
            size_mb = round(f.stat().st_size / (1024 * 1024), 2)
            dbs.append({"path": str(f.relative_to(PROJECT_ROOT)), "size_mb": size_mb, "status": "ok"})
        except Exception as e:
            dbs.append({"path": str(f), "status": "error", "error": str(e)})
    return {"databases": dbs, "count": len(dbs)}


def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-health", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            if name == "ctz_health_check":
                if psutil:
                    vm = psutil.virtual_memory()
                    ram_percent = vm.percent
                    ram_avail = round(vm.available / (1024**3), 2)
                else:
                    ram_percent = 0.0
                    ram_avail = 0.0
                mcp_results = _check_mcp_servers()
                healthy = sum(1 for r in mcp_results if r["status"] == "healthy")
                report = {
                    "timestamp": datetime.now().isoformat(),
                    "platform": platform.system(),
                    "python": sys.version.split()[0],
                    "ram_percent": ram_percent,
                    "ram_available_gb": ram_avail,
                    "mcp_servers": {"total": len(mcp_results), "healthy": healthy, "unhealthy": len(mcp_results) - healthy, "details": mcp_results},
                    "databases": _check_databases(),
                    "overall": "healthy" if healthy == len(mcp_results) else "degraded",
                    "note": "psutil optional for detailed RAM tracking" if not psutil else "psutil active",
                }
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(report, indent=2)}]}}
            elif name == "ctz_health_db":
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(_check_databases(), indent=2)}]}}
            elif name == "ctz_health_memory":
                if psutil:
                    vm = psutil.virtual_memory()
                    swap = psutil.swap_memory()
                    procs = []
                    for p in psutil.process_iter(["pid", "name", "memory_percent", "memory_info"]):
                        try:
                            info = p.info
                            if info.get("memory_percent", 0) > 0.5:
                                procs.append({"pid": info["pid"], "name": info["name"], "mem_percent": round(info["memory_percent"], 2), "mem_mb": round(info.memory_info.rss / (1024**2), 1)})
                        except:
                            pass
                    procs.sort(key=lambda x: x["mem_percent"], reverse=True)
                    mem_data = {"ram_total_gb": round(vm.total / (1024**3), 2), "ram_used_gb": round(vm.used / (1024**3), 2), "ram_percent": vm.percent, "swap_percent": swap.percent, "top_processes": procs[:10]}
                else:
                    mem_data = {"status": "ok", "note": "psutil not installed. Run 'pip install psutil' for process memory metrics.", "platform": platform.system()}
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(mem_data, indent=2)}]}}
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
