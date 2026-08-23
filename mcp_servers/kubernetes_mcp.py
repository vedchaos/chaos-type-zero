#!/usr/bin/env python3
"""CTZ MCP — Kubernetes"""
import json, sys, subprocess

SERVER_INFO = {"name": "kubernetes-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "k8s_get_pods", "description": "List pods. Omit namespace for all namespaces.", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}, "required": []}},
    {"name": "k8s_get_services", "description": "List services. Omit namespace for all namespaces.", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}, "required": []}},
    {"name": "k8s_get_deployments", "description": "List deployments. Omit namespace for all namespaces.", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}, "required": []}},
    {"name": "k8s_get_nodes", "description": "List cluster nodes with status and versions.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "k8s_logs", "description": "Fetch recent logs from a pod (default tail 100).", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}, "pod": {"type": "string"}, "lines": {"type": "integer", "default": 100}}, "required": ["namespace", "pod"]}},
    {"name": "k8s_describe", "description": "Describe a resource by type and name.", "inputSchema": {"type": "object", "properties": {"resource": {"type": "string"}, "name": {"type": "string"}, "namespace": {"type": "string"}}, "required": ["resource", "name"]}},
    {"name": "k8s_apply", "description": "Apply a YAML/JSON manifest file.", "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}}, "required": ["file"]}},
    {"name": "k8s_delete", "description": "Delete a resource by type and name.", "inputSchema": {"type": "object", "properties": {"resource": {"type": "string"}, "name": {"type": "string"}, "namespace": {"type": "string"}}, "required": ["resource", "name"]}},
    {"name": "k8s_scale", "description": "Scale a deployment to N replicas.", "inputSchema": {"type": "object", "properties": {"deployment": {"type": "string"}, "replicas": {"type": "integer"}, "namespace": {"type": "string"}}, "required": ["deployment", "replicas"]}},
    {"name": "k8s_rollout_status", "description": "Show rollout status of a deployment.", "inputSchema": {"type": "object", "properties": {"deployment": {"type": "string"}, "namespace": {"type": "string"}}, "required": ["deployment"]}},
    {"name": "k8s_top_nodes", "description": "Node CPU/memory usage via metrics-server.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "k8s_top_pods", "description": "Pod CPU/memory usage; defaults to all namespaces.", "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}, "required": []}},
    {"name": "k8s_config_current", "description": "Current kubectl context plus minified cluster details.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


def _run(args, timeout=30):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def _ns(ns):
    return ["-n", ns] if ns else ["-A"]


def k8s_get_pods(namespace=None):
    return _run(["kubectl", "get", "pods"] + _ns(namespace) + ["-o", "wide"])


def k8s_get_services(namespace=None):
    return _run(["kubectl", "get", "services"] + _ns(namespace) + ["-o", "wide"])


def k8s_get_deployments(namespace=None):
    return _run(["kubectl", "get", "deployments"] + _ns(namespace) + ["-o", "wide"])


def k8s_get_nodes():
    return _run(["kubectl", "get", "nodes", "-o", "wide"], timeout=60)


def k8s_logs(namespace, pod, lines=100):
    return _run(["kubectl", "logs", pod, "-n", namespace, "--tail", str(int(lines))], timeout=60)


def k8s_describe(resource, name, namespace=None):
    cmd = ["kubectl", "describe", resource, name]
    if namespace:
        cmd += ["-n", namespace]
    return _run(cmd, timeout=60)


def k8s_apply(file):
    return _run(["kubectl", "apply", "-f", file], timeout=120)


def k8s_delete(resource, name, namespace=None):
    cmd = ["kubectl", "delete", resource, name]
    if namespace:
        cmd += ["-n", namespace]
    return _run(cmd, timeout=60)


def k8s_scale(deployment, replicas, namespace=None):
    cmd = ["kubectl", "scale", "deployment", deployment, "--replicas", str(int(replicas))]
    if namespace:
        cmd += ["-n", namespace]
    return _run(cmd, timeout=60)


def k8s_rollout_status(deployment, namespace=None):
    cmd = ["kubectl", "rollout", "status", "deployment", deployment]
    if namespace:
        cmd += ["-n", namespace]
    return _run(cmd, timeout=180)


def k8s_top_nodes():
    return _run(["kubectl", "top", "nodes"], timeout=60)


def k8s_top_pods(namespace=None):
    cmd = ["kubectl", "top", "pods"]
    if namespace:
        cmd += ["-n", namespace]
    else:
        cmd += ["-A"]
    return _run(cmd, timeout=60)


def k8s_config_current():
    ctx = _run(["kubectl", "config", "current-context"])
    view = _run(["kubectl", "config", "view", "--minify", "-o", "json"])
    return {"current_context": ctx, "minified_config_json": view}


HANDLERS = {
    "k8s_get_pods": k8s_get_pods,
    "k8s_get_services": k8s_get_services,
    "k8s_get_deployments": k8s_get_deployments,
    "k8s_get_nodes": k8s_get_nodes,
    "k8s_logs": k8s_logs,
    "k8s_describe": k8s_describe,
    "k8s_apply": k8s_apply,
    "k8s_delete": k8s_delete,
    "k8s_scale": k8s_scale,
    "k8s_rollout_status": k8s_rollout_status,
    "k8s_top_nodes": k8s_top_nodes,
    "k8s_top_pods": k8s_top_pods,
    "k8s_config_current": k8s_config_current,
}


def handle_request(request):
    method = request.get("method", "")
    rid = request.get("id")
    if method.startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            params = request.get("params") or {}
            result = {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name", "")
            args = params.get("arguments") or {}
            fn = HANDLERS.get(name)
            if fn is None:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
            try:
                out = fn(**args)
                is_error = isinstance(out, dict) and "error" in out
            except Exception as exc:
                out = {"error": f"{type(exc).__name__}: {exc}"}
                is_error = True
            result = {"content": [{"type": "text", "text": json.dumps(out, indent=2, default=str)}]}
            if is_error:
                result["isError"] = True
        else:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            print(json.dumps(resp))
            sys.stdout.flush()
