#!/usr/bin/env python3
"""CTZ MCP — Redis"""
import json, sys, subprocess

SERVER_INFO = {"name": "redis-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "redis_get", "description": "GET a string key.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
    {"name": "redis_set", "description": "SET a string key with optional EX seconds expiry.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}, "ex": {"type": "integer"}}, "required": ["key", "value"]}},
    {"name": "redis_del", "description": "DEL one or more keys.", "inputSchema": {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}}}, "required": ["keys"]}},
    {"name": "redis_keys", "description": "KEYS pattern match.", "inputSchema": {"type": "object", "properties": {"pattern": {"type": "string", "default": "*"}}, "required": []}},
    {"name": "redis_hget", "description": "HGET field from hash.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "field": {"type": "string"}}, "required": ["key", "field"]}},
    {"name": "redis_hset", "description": "HSET field in hash.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "field": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "field", "value"]}},
    {"name": "redis_lpush", "description": "LPUSH values onto list head.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "values": {"type": "array", "items": {"type": "string"}}}, "required": ["key", "values"]}},
    {"name": "redis_lpop", "description": "LPOP first element of list.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
    {"name": "redis_sadd", "description": "SADD members to set.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "values": {"type": "array", "items": {"type": "string"}}}, "required": ["key", "values"]}},
    {"name": "redis_smembers", "description": "SMEMBERS all members of set.", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
    {"name": "redis_info", "description": "Redis server INFO stats.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "redis_ping", "description": "PING the server.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "redis_db_size", "description": "DBSIZE number of keys in current database.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


def _run(args, timeout=15):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def _cli(*args):
    return _run(["redis-cli"] + list(args))


def redis_get(key):
    return _cli("GET", key)


def redis_set(key, value, ex=None):
    args = ["SET", key, str(value)]
    if ex:
        args += ["EX", str(int(ex))]
    return _cli(*args)


def redis_del(keys):
    return _cli("DEL", *keys)


def redis_keys(pattern="*"):
    return _cli("KEYS", pattern)


def redis_hget(key, field):
    return _cli("HGET", key, field)


def redis_hset(key, field, value):
    return _cli("HSET", key, field, str(value))


def redis_lpush(key, values):
    return _cli("LPUSH", key, *[str(v) for v in values])


def redis_lpop(key):
    return _cli("LPOP", key)


def redis_sadd(key, values):
    return _cli("SADD", key, *[str(v) for v in values])


def redis_smembers(key):
    return _cli("SMEMBERS", key)


def redis_info():
    return _cli("INFO")


def redis_ping():
    return _cli("PING")


def redis_db_size():
    return _cli("DBSIZE")


HANDLERS = {
    "redis_get": redis_get,
    "redis_set": redis_set,
    "redis_del": redis_del,
    "redis_keys": redis_keys,
    "redis_hget": redis_hget,
    "redis_hset": redis_hset,
    "redis_lpush": redis_lpush,
    "redis_lpop": redis_lpop,
    "redis_sadd": redis_sadd,
    "redis_smembers": redis_smembers,
    "redis_info": redis_info,
    "redis_ping": redis_ping,
    "redis_db_size": redis_db_size,
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
