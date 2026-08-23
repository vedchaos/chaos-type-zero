#!/usr/bin/env python3
"""CTZ MCP — Pinecone Vector DB"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "pinecone-mcp", "version": "1.0.0"}
API_VERSION = "2024-07"

TOOLS = [
    {"name": "pc_list_indexes", "description": "List all indexes in the project.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "pc_create_index", "description": "Create a serverless index (aws/us-east-1 default).", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "dimension": {"type": "integer"}, "metric": {"type": "string", "default": "cosine"}}, "required": ["name", "dimension"]}},
    {"name": "pc_delete_index", "description": "Delete an index by name.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "pc_describe_index", "description": "Describe an index (dimension, metric, host, status).", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "pc_upsert", "description": "Upsert vectors into an index. vectors: JSON array [{\"id\":\"1\",\"values\":[0.1,0.2],\"metadata\":{}}] or JSON string.", "inputSchema": {"type": "object", "properties": {"index_name": {"type": "string"}, "vectors": {}, "namespace": {"type": "string", "default": ""}}, "required": ["index_name", "vectors"]}},
    {"name": "pc_query", "description": "Query an index with a vector (JSON array of floats). Returns top_k nearest with metadata.", "inputSchema": {"type": "object", "properties": {"index_name": {"type": "string"}, "vector": {}, "top_k": {"type": "integer", "default": 5}, "namespace": {"type": "string", "default": ""}}, "required": ["index_name", "vector"]}},
]


def _api_key():
    key = os.environ.get("PINECONE_API_KEY")
    if not key:
        return None, {"error": "PINECONE_API_KEY environment variable is not set"}
    return key, None


def _ctrl_req(method, path, data=None):
    key, err = _api_key()
    if err:
        return err
    headers = {"Api-Key": key, "X-Pinecone-API-Version": API_VERSION,
               "Accept": "application/json", "User-Agent": "ctz-pinecone-mcp/1.0"}
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request("https://api.pinecone.io" + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = detail[:400] or f"HTTP {exc.code}"
        if exc.code == 401:
            msg = "Invalid Pinecone API key (401)"
        elif exc.code == 404:
            msg = f"Index not found: {path}"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def _data_req(host, path, data):
    key, err = _api_key()
    if err:
        return err
    url = f"https://{host}{path}"
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST",
                                 headers={"Api-Key": key, "X-Pinecone-API-Version": API_VERSION,
                                          "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"error": detail[:400] or f"HTTP {exc.code}", "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def _host_of(index_name):
    desc = pc_describe_index(index_name)
    host = desc.get("host") if isinstance(desc, dict) else None
    if not host:
        raise LookupError(f"Cannot resolve host for index '{index_name}': {desc}")
    return host


def pc_list_indexes():
    return _ctrl_req("GET", "/indexes")


def pc_create_index(name, dimension, metric="cosine"):
    spec = {"serverless": {"cloud": "aws", "region": "us-east-1"}}
    env = os.environ.get("PINECONE_ENV")
    m = re.match(r"^([a-z]{2}-[a-z]+-\d+)-(aws|gcp|azure)$", env or "")
    if m:
        spec["serverless"] = {"region": m.group(1), "cloud": m.group(2)}
    body = {"name": name, "dimension": int(dimension), "metric": metric, "spec": spec}
    result = _ctrl_req("POST", "/indexes", body)
    if isinstance(result, dict) and not result.get("error"):
        result["note"] = "Creation is async; poll pc_describe_index until ready."
    return result


def pc_delete_index(name):
    res = _ctrl_req("DELETE", "/indexes/" + urllib.parse.quote(name))
    if isinstance(res, dict) and not res.get("error"):
        return {"deleted": name}
    return res


def pc_describe_index(name):
    return _ctrl_req("GET", "/indexes/" + urllib.parse.quote(name))


def pc_upsert(index_name, vectors, namespace=""):
    try:
        vecs = json.loads(vectors) if isinstance(vectors, str) else vectors
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid vectors JSON: {exc}"}
    if isinstance(vecs, dict):
        vecs = vecs.get("vectors", [])
    if not isinstance(vecs, list):
        return {"error": "vectors must be a JSON array of {id, values, metadata?}"}
    host = _host_of(index_name)
    body = {"vectors": vecs, "namespace": namespace or ""}
    return _data_req(host, "/vectors/upsert", body)


def pc_query(index_name, vector, top_k=5, namespace=""):
    try:
        vec = json.loads(vector) if isinstance(vector, str) else vector
        if isinstance(vec, dict):
            vec = vec.get("values") or vec.get("vector")
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid vector JSON: {exc}"}
    if not isinstance(vec, list):
        return {"error": "vector must be a JSON array of floats"}
    host = _host_of(index_name)
    body = {"vector": vec, "topK": int(top_k), "includeMetadata": True, "namespace": namespace or ""}
    return _data_req(host, "/query", body)


HANDLERS = {
    "pc_list_indexes": pc_list_indexes,
    "pc_create_index": pc_create_index,
    "pc_delete_index": pc_delete_index,
    "pc_describe_index": pc_describe_index,
    "pc_upsert": pc_upsert,
    "pc_query": pc_query,
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
