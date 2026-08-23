#!/usr/bin/env python3
"""CTZ MCP — PostgreSQL"""
import json, os, sys, subprocess

SERVER_INFO = {"name": "postgres-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "pg_query", "description": "Run an arbitrary SQL query against a database.", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}, "query": {"type": "string"}}, "required": ["database", "query"]}},
    {"name": "pg_list_databases", "description": "List all databases with encoding and size.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "pg_list_tables", "description": "List tables/views/sequences in a database (\\dt output plus row counts).", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}}, "required": ["database"]}},
    {"name": "pg_describe_table", "description": "Describe table structure including indexes (\\d+ output).", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}, "table": {"type": "string"}}, "required": ["database", "table"]}},
    {"name": "pg_stats", "description": "Top tables by live-tuple count from pg_stat_user_tables.", "inputSchema": {"type": "object", "properties": {"database": {"type": "string"}}, "required": ["database"]}},
]


def _run(args, timeout=60, database=None):
    try:
        env = os.environ.copy()
        if database:
            env["PGDATABASE"] = database
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def pg_query(database, query):
    return _run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", database, "-c", query], database=database, timeout=120)


def pg_list_databases():
    sql = ("SELECT datname AS database, pg_encoding_to_char(encoding) AS encoding, "
           "pg_size_pretty(pg_database_size(datname)) AS size "
           "FROM pg_database WHERE NOT datistemplate ORDER BY datname;")
    return _run(["psql", "-X", "-c", sql])


def pg_list_tables(database):
    counts = ("SELECT n.nspname AS schema, c.relname AS name, CASE c.relkind WHEN 'r' THEN 'table' "
              "WHEN 'v' THEN 'view' WHEN 'm' THEN 'matview' WHEN 'S' THEN 'sequence' ELSE c.relkind::text END AS kind, "
              "COALESCE(s.n_live_tup, 0) AS approx_rows FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
              "LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid WHERE c.relkind IN ('r','v','m','S') "
              "AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2;")
    meta = _run(["psql", "-X", "-c", "\\dt"], database=database)
    detail = _run(["psql", "-X", "-c", counts], database=database)
    return {"tables_meta": meta.get("stdout", ""), "detail_stdout": detail.get("stdout", ""), "stderr": (meta.get("stderr", "") + detail.get("stderr", ""))[:2000], "returncode": max(meta.get("returncode", 1), detail.get("returncode", 1))}


def pg_describe_table(database, table):
    safe = table.replace('"', '')
    return _run(["psql", "-X", "-d", database, "-c", f"\\d+ \"{safe}\""], database=database)


def pg_stats(database):
    sql = ("SELECT schemaname || '.' || relname AS table_name, seq_scan, idx_scan, n_live_tup, n_dead_tup, "
           "last_autovacuum FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;")
    return _run(["psql", "-X", "-c", sql], database=database)


HANDLERS = {
    "pg_query": pg_query,
    "pg_list_databases": pg_list_databases,
    "pg_list_tables": pg_list_tables,
    "pg_describe_table": pg_describe_table,
    "pg_stats": pg_stats,
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
