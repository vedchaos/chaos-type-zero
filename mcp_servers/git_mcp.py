#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Git Server"""
import json, subprocess, sys

TOOLS = [
    {"name": "ctz_git_status", "description": "Get git status of a repo", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}}},
    {"name": "ctz_git_log", "description": "Get recent git commits", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "count": {"type": "integer", "default": 10}}}},
    {"name": "ctz_git_diff", "description": "Get git diff", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "staged": {"type": "boolean", "default": False}}}},
    {"name": "ctz_git_commit", "description": "Stage all and commit", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "message": {"type": "string"}}, "required": ["message"]}},
    {"name": "ctz_git_push", "description": "Push to remote", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "remote": {"type": "string", "default": "origin"}, "branch": {"type": "string", "default": "main"}}}},
    {"name": "ctz_git_pull", "description": "Pull from remote", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "remote": {"type": "string", "default": "origin"}}}},
    {"name": "ctz_git_branches", "description": "List all branches", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}}},
]

def _run(cmd, path="."):
    try:
        r = subprocess.run(cmd, cwd=path, capture_output=True, text=True, timeout=30)
        return {"stdout": r.stdout[:3000], "stderr": r.stderr[:500], "code": r.returncode}
    except Exception as e:
        return {"error": str(e), "code": -1}

def handle_request(request):
    method, params, req_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-git", "version": "1.0.0"}}}
    if method == "notifications/initialized": return None
    if method == "tools/list": return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        p = args.get("path", ".")
        try:
            if name == "ctz_git_status": r = _run(["git", "status", "--short"], p)
            elif name == "ctz_git_log": r = _run(["git", "log", f"--oneline", f"-{args.get('count', 10)}"], p)
            elif name == "ctz_git_diff": r = _run(["git", "diff", "--staged" if args.get("staged") else "HEAD"], p)
            elif name == "ctz_git_commit": add_res = _run(["git", "add", "."], p); r = _run(["git", "commit", "-m", args["message"]], p) if add_res.get("code") == 0 else add_res
            elif name == "ctz_git_push": r = _run(["git", "push", args.get("remote", "origin"), args.get("branch", "main")], p)
            elif name == "ctz_git_pull": r = _run(["git", "pull", args.get("remote", "origin")], p)
            elif name == "ctz_git_branches": r = _run(["git", "branch", "-a"], p)
            else: return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown tool"}}
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown method"}}

if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = handle_request(json.loads(line.strip()))
            if r: sys.stdout.write(json.dumps(r) + "\n"); sys.stdout.flush()
        except: pass
