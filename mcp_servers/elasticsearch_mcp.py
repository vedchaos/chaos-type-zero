#!/usr/bin/env python3
"""CTZ MCP — Elasticsearch"""
import json, sys, subprocess

SERVER_INFO = {"name": "elasticsearch-mcp", "version": "1.0.0"}
BASE_URL = "http://localhost:9200"

TOOLS = [
    {"name": "es_search", "description": "Search an index. Pass a simple query string or a full Query DSL JSON body string.", "inputSchema": {"type": "object", "properties": {"index": {"type": "string"}, "query": {"type": "string"}, "size": {"type": "integer", "default": 10}}, "required": ["index", "query"]}},
    {"name": "es_index", "description": "Index (create) a document (document is a JSON object string).", "inputSchema": {"type": "object", "properties": {"index": {"type": "string"}, "document": {"type": "string"}}, "required": ["index", "document"]}},
    {"name": "es_delete", "description": "Delete a document by id.", "inputSchema": {"type": "object", "properties": {"index": {"type": "string"}, "id": {"type": "string"}}, "required": ["index", "id"]}},
    {"name": "es_mapping", "description": "Get index mapping.", "inputSchema": {"type": "object", "properties": {"index": {"type": "string"}}, "required": ["index"]}},
    {"name": "es_cluster_health", "description": "Cluster health status.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "es_cat_indices", "description": "List indices with docs count and size (_cat/indices?v).", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


def _run(args, timeout=30):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def _es(method, path, body=None, timeout=30):
    cmd = ["curl", "-s", "-X", method]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    cmd.append(BASE_URL + path)
    out = _run(cmd, timeout)
    if isinstance(out, dict) and out.get("returncode") == 0:
        raw = out.get("stdout", "")
        if raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw[:8000]}
        return {"raw": "", "note": "Empty response"}
    return out


def es_search(index, query, size=10):
    try:
        if isinstance(query, str) and query.strip().startswith("{"):
            body = json.loads(query)
        else:
            body = {"query": {"query_string": {"query": str(query)}}, "size": int(size)}
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid query JSON: {exc}"}
    return _es("POST", f"/{index}/_search", body)


def es_index(index, document):
    try:
        doc = json.loads(document) if isinstance(document, str) else document
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid document JSON: {exc}"}
    return _es("POST", f"/{index}/_doc", doc)


def es_delete(index, id):
    return _es("DELETE", f"/{index}/_doc/{id}")


def es_mapping(index):
    return _es("GET", f"/{index}/_mapping")


def es_cluster_health():
    return _es("GET", "/_cluster/health")


def es_cat_indices():
    return _es("GET", "/_cat/indices?v")


HANDLERS = {
    "es_search": es_search,
    "es_index": es_index,
    "es_delete": es_delete,
    "es_mapping": es_mapping,
    "es_cluster_health": es_cluster_health,
    "es_cat_indices": es_cat_indices,
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
