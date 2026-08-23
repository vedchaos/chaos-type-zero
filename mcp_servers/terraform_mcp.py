#!/usr/bin/env python3
"""CTZ MCP — Terraform IaC"""
import json, sys, subprocess, os

TOOLS = [
    {"name": "tf_init", "description": "Initialize Terraform", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}}, "required": []}},
    {"name": "tf_plan", "description": "Plan Terraform changes", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}}, "required": []}},
    {"name": "tf_apply", "description": "Apply Terraform changes", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}, "auto_approve": {"type": "boolean", "default": False}}, "required": []}},
    {"name": "tf_destroy", "description": "Destroy Terraform resources", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}, "auto_approve": {"type": "boolean", "default": False}}, "required": []}},
    {"name": "tf_validate", "description": "Validate Terraform config", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}}, "required": []}},
    {"name": "tf_fmt", "description": "Format Terraform files", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}}, "required": []}},
    {"name": "tf_state_list", "description": "List Terraform state resources", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}}, "required": []}},
    {"name": "tf_state_show", "description": "Show Terraform resource details", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}, "resource": {"type": "string"}}, "required": ["resource"]}},
    {"name": "tf_output", "description": "Show Terraform outputs", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}}, "required": []}},
    {"name": "tf_workspace_list", "description": "List Terraform workspaces", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}}, "required": []}},
    {"name": "tf_workspace_select", "description": "Select Terraform workspace", "inputSchema": {"type": "object", "properties": {"dir": {"type": "string", "default": "."}, "name": {"type": "string"}}, "required": ["name"]}},
]

def _run(args, timeout=60, cwd=None):
    try:
        r = subprocess.run(["terraform"] + args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"Timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": "Terraform not installed. Install: https://terraform.io/downloads"}

HANDLERS = {
    "tf_init": lambda p: {"output": _run(["init"], cwd=p.get("dir", ".")).get("stdout", "")},
    "tf_plan": lambda p: {"output": _run(["plan"], cwd=p.get("dir", ".")).get("stdout", "")[:6000]},
    "tf_apply": lambda p: {"output": _run(["apply", "-auto-approve"] if p.get("auto_approve") else ["plan"], cwd=p.get("dir", ".")).get("stdout", "")[:6000]},
    "tf_destroy": lambda p: {"output": _run(["destroy", "-auto-approve"] if p.get("auto_approve") else ["destroy"], cwd=p.get("dir", ".")).get("stdout", "")[:6000]},
    "tf_validate": lambda p: {"output": _run(["validate"], cwd=p.get("dir", ".")).get("stdout", "")},
    "tf_fmt": lambda p: {"output": _run(["fmt", "-recursive"], cwd=p.get("dir", ".")).get("stdout", "")},
    "tf_state_list": lambda p: {"output": _run(["state", "list"], cwd=p.get("dir", ".")).get("stdout", "")[:6000]},
    "tf_state_show": lambda p: {"output": _run(["state", "show", p["resource"]], cwd=p.get("dir", ".")).get("stdout", "")[:6000]},
    "tf_output": lambda p: {"output": _run(["output"], cwd=p.get("dir", ".")).get("stdout", "")[:6000]},
    "tf_workspace_list": lambda p: {"output": _run(["workspace", "list"], cwd=p.get("dir", ".")).get("stdout", "")},
    "tf_workspace_select": lambda p: {"output": _run(["workspace", "select", p["name"]], cwd=p.get("dir", ".")).get("stdout", "")},
}

def handle_request(request):
    method, params, req_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-terraform", "version": "1.0.0"}}}
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
