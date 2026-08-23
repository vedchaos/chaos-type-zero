#!/usr/bin/env python3
"""CTZ MCP — Docker Container Management"""
import json, sys, subprocess

TOOLS = [
    {"name": "docker_ps", "description": "List running containers", "inputSchema": {"type": "object", "properties": {"all": {"type": "boolean", "default": False}}, "required": []}},
    {"name": "docker_images", "description": "List Docker images", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "docker_logs", "description": "Get container logs", "inputSchema": {"type": "object", "properties": {"container": {"type": "string"}, "lines": {"type": "number", "default": 100}}, "required": ["container"]}},
    {"name": "docker_stop", "description": "Stop a container", "inputSchema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
    {"name": "docker_start", "description": "Start a container", "inputSchema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
    {"name": "docker_restart", "description": "Restart a container", "inputSchema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
    {"name": "docker_inspect", "description": "Inspect a container", "inputSchema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
    {"name": "docker_exec", "description": "Execute command in container", "inputSchema": {"type": "object", "properties": {"container": {"type": "string"}, "command": {"type": "string"}}, "required": ["container", "command"]}},
    {"name": "docker_stats", "description": "Container resource usage", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "docker_compose_up", "description": "Docker compose up", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "detach": {"type": "boolean", "default": True}}, "required": []}},
    {"name": "docker_compose_down", "description": "Docker compose down", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}, "required": []}},
    {"name": "docker_network_list", "description": "List Docker networks", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "docker_volume_list", "description": "List Docker volumes", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "docker_remove", "description": "Remove a container", "inputSchema": {"type": "object", "properties": {"container": {"type": "string"}, "force": {"type": "boolean", "default": False}}, "required": ["container"]}},
]

def _run(args, timeout=30, cwd=None):
    try:
        r = subprocess.run(["docker"] + args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"Timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": "Docker not installed"}

HANDLERS = {
    "docker_ps": lambda p: {"output": _run(["ps", "-a" if p.get("all") else "", "--format", "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"]).get("stdout", "")},
    "docker_images": lambda p: {"output": _run(["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"]).get("stdout", "")},
    "docker_logs": lambda p: {"output": _run(["logs", "--tail", str(p.get("lines", 100)), p["container"]]).get("stdout", "")[:6000]},
    "docker_stop": lambda p: {"status": "stopped", "output": _run(["stop", p["container"]]).get("stdout", "")},
    "docker_start": lambda p: {"status": "started", "output": _run(["start", p["container"]]).get("stdout", "")},
    "docker_restart": lambda p: {"status": "restarted", "output": _run(["restart", p["container"]]).get("stdout", "")},
    "docker_inspect": lambda p: {"output": _run(["inspect", "--format", "{{json .}}", p["container"]]).get("stdout", "")[:6000]},
    "docker_exec": lambda p: {"output": _run(["exec", p["container"]] + p["command"].split()).get("stdout", "")[:6000]},
    "docker_stats": lambda p: {"output": _run(["stats", "--no-stream", "--format", "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"]).get("stdout", "")},
    "docker_compose_up": lambda p: {"output": _run(["compose", "up", "-d" if p.get("detach", True) else ""], cwd=p.get("path", ".")).get("stdout", "")},
    "docker_compose_down": lambda p: {"output": _run(["compose", "down"], cwd=p.get("path", ".")).get("stdout", "")},
    "docker_network_list": lambda p: {"output": _run(["network", "ls", "--format", "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"]).get("stdout", "")},
    "docker_volume_list": lambda p: {"output": _run(["volume", "ls", "--format", "table {{.Name}}\t{{.Driver}}\t{{.Mountpoint}}"]).get("stdout", "")},
    "docker_remove": lambda p: {"status": "removed", "output": _run(["rm", "-f" if p.get("force") else "", p["container"]]).get("stdout", "")},
}

def handle_request(request):
    method, params, req_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-docker", "version": "1.0.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        tool_name = params.get("name", "")
        handler = HANDLERS.get(tool_name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        try:
            result = handler(params.get("arguments", {}))
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = json.loads(line.strip())
            print(json.dumps(handle_request(r))); sys.stdout.flush()
        except json.JSONDecodeError: continue
