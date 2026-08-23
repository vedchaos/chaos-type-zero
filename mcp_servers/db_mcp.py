#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — DB Server (SQLite operations)"""
import json, sqlite3, sys
from pathlib import Path

CTZ_ROOT = Path(__file__).parent.parent

TOOLS = [
    {"name": "ctz_db_query", "description": "Execute a SELECT query on SQLite database", "inputSchema": {"type": "object", "properties": {"db_path": {"type": "string"}, "query": {"type": "string"}, "params": {"type": "array", "items": {}, "default": []}}, "required": ["db_path", "query"]}},
    {"name": "ctz_db_execute", "description": "Execute a write query (INSERT/UPDATE/DELETE)", "inputSchema": {"type": "object", "properties": {"db_path": {"type": "string"}, "query": {"type": "string"}, "params": {"type": "array", "items": {}, "default": []}}, "required": ["db_path", "query"]}},
    {"name": "ctz_db_tables", "description": "List all tables in a database", "inputSchema": {"type": "object", "properties": {"db_path": {"type": "string"}}, "required": ["db_path"]}},
    {"name": "ctz_db_schema", "description": "Get table schema", "inputSchema": {"type": "object", "properties": {"db_path": {"type": "string"}, "table": {"type": "string"}}, "required": ["db_path", "table"]}},
    {"name": "ctz_db_count", "description": "Count rows in a table", "inputSchema": {"type": "object", "properties": {"db_path": {"type": "string"}, "table": {"type": "string"}}, "required": ["db_path", "table"]}},
    {"name": "ctz_db_list_dbs", "description": "List all CTZ SQLite databases", "inputSchema": {"type": "object", "properties": {}}},
]

def _resolve_db(db_path):
    if os.path.exists(db_path): return db_path
    for sub in ["data/memory", "data/context", "data/cache", "data/automation", "data/vault"]:
        p = CTZ_ROOT / sub / db_path
        if p.exists(): return str(p)
    return db_path


def _validate_table(cursor, table):
    """
    SECURITY: table names used to be string-interpolated straight into SQL
    (e.g. f"SELECT COUNT(*) FROM [{args['table']}]"), which let a caller
    inject arbitrary SQL via the 'table' argument (e.g.
    "x] ; ATTACH DATABASE ... --"). We now only ever allow a value that
    exactly matches a real table already present in sqlite_master.
    """
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,))
    if cursor.fetchone() is None:
        raise ValueError(f"Unknown table: {table!r}")
    return table

import os

def handle_request(request):
    method, params, req_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-db", "version": "1.0.0"}}}
    if method == "notifications/initialized": return None
    if method == "tools/list": return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        try:
            if name == "ctz_db_list_dbs":
                dbs = []
                for sub in ["data/memory", "data/context", "data/cache", "data/automation", "data/vault"]:
                    d = CTZ_ROOT / sub
                    if d.exists():
                        for f in d.glob("*.db"):
                            dbs.append({"name": f.name, "path": str(f), "size": f.stat().st_size})
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(dbs, indent=2)}]}}
            
            db_path = _resolve_db(args["db_path"])
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            if name == "ctz_db_query":
                c.execute(args["query"], args.get("params", []))
                cols = [d[0] for d in c.description] if c.description else []
                rows = [dict(zip(cols, row)) for row in c.fetchall()]
                conn.close()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(rows[:100], indent=2, default=str)}]}}
            elif name == "ctz_db_execute":
                c.execute(args["query"], args.get("params", []))
                conn.commit()
                conn.close()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"affected_rows": c.rowcount})}]}}
            elif name == "ctz_db_tables":
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in c.fetchall()]
                conn.close()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(tables)}]}}
            elif name == "ctz_db_schema":
                table = _validate_table(c, args["table"])
                c.execute(f'PRAGMA table_info("{table}")')
                cols = [{"name": r[1], "type": r[2], "notnull": bool(r[3]), "default": r[4], "pk": bool(r[5])} for r in c.fetchall()]
                conn.close()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(cols, indent=2)}]}}
            elif name == "ctz_db_count":
                table = _validate_table(c, args["table"])
                c.execute(f'SELECT COUNT(*) FROM "{table}"')
                count = c.fetchone()[0]
                conn.close()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"count": count})}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown method"}}

if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = handle_request(json.loads(line.strip()))
            if r: sys.stdout.write(json.dumps(r) + "\n"); sys.stdout.flush()
        except: pass
