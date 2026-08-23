#!/usr/bin/env python3
"""CTZ MCP — MongoDB"""
import json, sys, subprocess

SERVER_INFO = {"name": "mongo-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "mongo_find", "description": "Query documents from a collection (query is a JSON filter object string).", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}, "collection": {"type": "string"}, "query": {"type": "string", "default": "{}"}, "limit": {"type": "integer", "default": 20}}, "required": ["database", "collection"]}},
    {"name": "mongo_insert", "description": "Insert one document (document is a JSON object string).", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}, "collection": {"type": "string"}, "document": {"type": "string"}}, "required": ["database", "collection", "document"]}},
    {"name": "mongo_update", "description": "Update ALL documents matching filter (filter/update are JSON object strings).", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}, "collection": {"type": "string"}, "filter": {"type": "string", "default": "{}"}, "update": {"type": "string"}}, "required": ["database", "collection", "update"]}},
    {"name": "mongo_delete", "description": "Delete ALL documents matching filter (filter is a JSON object string).", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}, "collection": {"type": "string"}, "filter": {"type": "string", "default": "{}"}}, "required": ["database", "collection"]}},
    {"name": "mongo_list_collections", "description": "List collections in a database.", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}}, "required": ["database"]}},
    {"name": "mongo_db_stats", "description": "Database statistics (db.stats()).", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}}, "required": ["database"]}},
]


def _run(args, timeout=30):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def _eval(js, timeout=60):
    out = _run(["mongosh", "--quiet", "--eval", js], timeout)
    if isinstance(out, dict) and out.get("returncode") == 0:
        try:
            return json.loads(out["stdout"])
        except (json.JSONDecodeError, KeyError):
            return out
    return out


def mongo_find(database, collection, query="{}", limit=20):
    js = (f'print(JSON.stringify(db.getSiblingDB({json.dumps(database)}).'
          f'getCollection({json.dumps(collection)}).find({query}).limit({int(limit)}).toArray()))')
    return _eval(js)


def mongo_insert(database, collection, document):
    js = (f'const r = db.getSiblingDB({json.dumps(database)}).getCollection({json.dumps(collection)})'
          f'.insertOne({document}); print(JSON.stringify({{acknowledged: r.acknowledged, insertedId: String(r.insertedId)}}))')
    return _eval(js)


def mongo_update(database, collection, update, filter="{}"):
    js = (f'const r = db.getSiblingDB({json.dumps(database)}).getCollection({json.dumps(collection)})'
          f'.updateMany({filter}, {update}); '
          'print(JSON.stringify({matched: r.matchedCount, modified: r.modifiedCount, acknowledged: r.acknowledged}))')
    return _eval(js)


def mongo_delete(database, collection, filter="{}"):
    js = (f'const r = db.getSiblingDB({json.dumps(database)}).getCollection({json.dumps(collection)})'
          '.deleteMany(' + filter + '); print(JSON.stringify({deleted: r.deletedCount, acknowledged: r.acknowledged}))')
    return _eval(js)


def mongo_list_collections(database):
    js = (f'print(JSON.stringify(db.getSiblingDB({json.dumps(database)}).getCollectionNames()))')
    return _eval(js)


def mongo_db_stats(database):
    js = f'print(JSON.stringify(db.getSiblingDB({json.dumps(database)}).stats()))'
    return _eval(js)


HANDLERS = {
    "mongo_find": mongo_find,
    "mongo_insert": mongo_insert,
    "mongo_update": mongo_update,
    "mongo_delete": mongo_delete,
    "mongo_list_collections": mongo_list_collections,
    "mongo_db_stats": mongo_db_stats,
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
