#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Report Generation Server"""

import json
import sys
import os
import platform
try:
    import psutil
except ImportError:
    psutil = None
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TOOLS = [
    {"name": "ctz_report_system", "description": "Generate a system status report", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ctz_report_memory", "description": "Generate a memory usage report", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ctz_report_project", "description": "Generate project stats (file count, LOC, etc)", "inputSchema": {"type": "object", "properties": {"directory": {"type": "string", "default": "."}}}},
]


def _count_loc(directory):
    total, py_files = 0, 0
    base = PROJECT_ROOT / directory if not os.path.isabs(directory) else Path(directory)
    for f in base.rglob("*.py"):
        try:
            total += sum(1 for _ in f.open(encoding="utf-8", errors="replace"))
            py_files += 1
        except:
            pass
    return {"python_files": py_files, "total_lines": total}


def _count_files(directory):
    base = PROJECT_ROOT / directory if not os.path.isabs(directory) else Path(directory)
    exts = {}
    for f in base.rglob("*"):
        if f.is_file():
            ext = f.suffix.lower() or "no_ext"
            exts[ext] = exts.get(ext, 0) + 1
    return exts


def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-report", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            if name == "ctz_report_system":
                report = {
                    "timestamp": datetime.now().isoformat(),
                    "platform": platform.system(),
                    "platform_release": platform.release(),
                    "python_version": sys.version.split()[0],
                    "cpu_count": psutil.cpu_count() if psutil else os.cpu_count(),
                    "cpu_percent": psutil.cpu_percent(interval=1) if psutil else 0.0,
                    "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat() if psutil else "unknown (install psutil)",
                    "note": "Install psutil for accurate CPU percentages" if not psutil else "psutil active",
                }
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(report, indent=2)}]}}
            elif name == "ctz_report_memory":
                if psutil:
                    vm = psutil.virtual_memory()
                    swap = psutil.swap_memory()
                    report = {
                        "timestamp": datetime.now().isoformat(),
                        "total_ram_gb": round(vm.total / (1024**3), 2),
                        "used_ram_gb": round(vm.used / (1024**3), 2),
                        "available_ram_gb": round(vm.available / (1024**3), 2),
                        "ram_percent": vm.percent,
                        "swap_total_gb": round(swap.total / (1024**3), 2),
                        "swap_used_gb": round(swap.used / (1024**3), 2),
                        "swap_percent": swap.percent,
                    }
                else:
                    report = {
                        "timestamp": datetime.now().isoformat(),
                        "status": "partial",
                        "note": "psutil not installed. Run 'pip install psutil' for detailed RAM metrics.",
                        "platform": platform.system()
                    }
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(report, indent=2)}]}}
            elif name == "ctz_report_project":
                directory = args.get("directory", ".")
                report = {
                    "timestamp": datetime.now().isoformat(),
                    "directory": directory,
                    "file_types": _count_files(directory),
                    "lines_of_code": _count_loc(directory),
                }
                report["total_files"] = sum(report["file_types"].values())
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(report, indent=2)}]}}
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
