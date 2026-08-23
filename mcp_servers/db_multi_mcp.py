#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Multi-Database Connectors Server"""

import json
import sys
import datetime
import os

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.sql
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

try:
    import pymongo
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

TOOLS = [
    {"name": "ctz_db_postgres_query", "description": "Execute a read-only PostgreSQL query", "inputSchema": {"type": "object", "properties": {"host": {"type": "string", "default": "localhost"}, "port": {"type": "integer", "default": 5432}, "database": {"type": "string"}, "user": {"type": "string", "default": "postgres"}, "password": {"type": "string", "default": ""}, "query": {"type": "string"}, "params": {"type": "array", "items": {"type": "string"}, "default": []}, "limit": {"type": "integer", "default": 100}}, "required": ["database", "query"]}},
    {"name": "ctz_db_postgres_tables", "description": "List tables in a PostgreSQL database", "inputSchema": {"type": "object", "properties": {"host": {"type": "string", "default": "localhost"}, "port": {"type": "integer", "default": 5432}, "database": {"type": "string"}, "user": {"type": "string", "default": "postgres"}, "password": {"type": "string", "default": ""}, "schema": {"type": "string", "default": "public"}}, "required": ["database"]}},
    {"name": "ctz_db_mongo_query", "description": "Query a MongoDB collection", "inputSchema": {"type": "object", "properties": {"uri": {"type": "string", "default": "mongodb://localhost:27017"}, "database": {"type": "string"}, "collection": {"type": "string"}, "filter": {"type": "object", "default": {}}, "projection": {"type": "object", "default": {}}, "limit": {"type": "integer", "default": 100}, "sort": {"type": "array", "default": []}}, "required": ["database", "collection"]}},
    {"name": "ctz_db_mongo_collections", "description": "List collections in a MongoDB database", "inputSchema": {"type": "object", "properties": {"uri": {"type": "string", "default": "mongodb://localhost:27017"}, "database": {"type": "string"}}, "required": ["database"]}},
    {"name": "ctz_db_redis_get", "description": "Redis GET key", "inputSchema": {"type": "object", "properties": {"host": {"type": "string", "default": "localhost"}, "port": {"type": "integer", "default": 6379}, "password": {"type": "string", "default": ""}, "db": {"type": "integer", "default": 0}, "key": {"type": "string"}}, "required": ["key"]}},
    {"name": "ctz_db_redis_set", "description": "Redis SET key-value", "inputSchema": {"type": "object", "properties": {"host": {"type": "string", "default": "localhost"}, "port": {"type": "integer", "default": 6379}, "password": {"type": "string", "default": ""}, "db": {"type": "integer", "default": 0}, "key": {"type": "string"}, "value": {"type": "string"}, "ex": {"type": "integer", "default": 0, "description": "Expiry in seconds (0=no expiry)"}}, "required": ["key", "value"]}},
    {"name": "ctz_db_redis_keys", "description": "Redis KEYS pattern match", "inputSchema": {"type": "object", "properties": {"host": {"type": "string", "default": "localhost"}, "port": {"type": "integer", "default": 6379}, "password": {"type": "string", "default": ""}, "db": {"type": "integer", "default": 0}, "pattern": {"type": "string", "default": "*"}, "limit": {"type": "integer", "default": 100}}, "required": []}},
    {"name": "ctz_db_multi_backup", "description": "Backup all configured databases (Postgres dumps, Mongo dumps, Redis BGSAVE)", "inputSchema": {"type": "object", "properties": {"output_dir": {"type": "string", "default": "./backups"}, "postgres": {"type": "object", "default": None}, "mongo": {"type": "object", "default": None}, "redis": {"type": "object", "default": None}}}},
]


def pg_connect(args):
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")
    return psycopg2.connect(host=args.get("host", "localhost"), port=args.get("port", 5432), dbname=args["database"], user=args.get("user", "postgres"), password=args.get("password", ""))


def pg_query(args):
    conn = pg_connect(args)
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = args["query"].strip()
        limit = args.get("limit", 100)
        lower = query.lower()
        if not any(lower.startswith(kw) for kw in ["select", "with", "show", "explain"]):
            return {"error": "Only SELECT / WITH / SHOW / EXPLAIN queries allowed (read-only mode)"}
        if "limit" not in lower and "show" not in lower and "explain" not in lower:
            query = query.rstrip(";") + f" LIMIT {limit};"
        params = tuple(args.get("params", []))
        cur.execute(query, params)
        rows = cur.fetchall()
        return {"columns": [desc[0] for desc in cur.description], "rows": [dict(r) for r in rows], "row_count": len(rows)}
    finally:
        conn.close()


def pg_tables(args):
    conn = pg_connect(args)
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        schema = args.get("schema", "public")
        cur.execute("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name", (schema,))
        tables = [{"name": r["table_name"], "type": r["table_type"]} for r in cur.fetchall()]
        for t in tables:
            try:
                # SECURITY: schema/table names used to be interpolated with
                # plain % string formatting, which let a caller inject SQL
                # via the 'schema' argument. psycopg2.sql.Identifier quotes
                # identifiers safely (equivalent to parameterizing a query,
                # which Postgres doesn't allow for identifiers).
                query = psycopg2.sql.SQL("SELECT COUNT(*) as cnt FROM {}.{}").format(
                    psycopg2.sql.Identifier(schema), psycopg2.sql.Identifier(t["name"])
                )
                cur.execute(query)
                t["row_count"] = cur.fetchone()["cnt"]
            except Exception:
                t["row_count"] = -1
        return {"schema": schema, "tables": tables, "count": len(tables)}
    finally:
        conn.close()


def mongo_query(args):
    if not HAS_PYMONGO:
        raise RuntimeError("pymongo not installed. Run: pip install pymongo")
    uri = args.get("uri", "mongodb://localhost:27017")
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[args["database"]]
        coll = db[args["collection"]]
        filter_q = args.get("filter", {})
        projection = args.get("projection", {})
        limit = args.get("limit", 100)
        sort = args.get("sort", [])
        cursor = coll.find(filter_q, projection).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        docs = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            docs.append(doc)
        return {"database": args["database"], "collection": args["collection"], "documents": docs, "count": len(docs)}
    finally:
        client.close()


def mongo_collections(args):
    if not HAS_PYMONGO:
        raise RuntimeError("pymongo not installed. Run: pip install pymongo")
    uri = args.get("uri", "mongodb://localhost:27017")
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[args["database"]]
        collections = []
        for name in db.list_collection_names():
            count = db[name].count_documents({})
            indexes = list(db[name].list_indexes())
            collections.append({"name": name, "document_count": count, "indexes": len(indexes)})
        return {"database": args["database"], "collections": collections, "count": len(collections)}
    finally:
        client.close()


def redis_get(args):
    if not HAS_REDIS:
        raise RuntimeError("redis not installed. Run: pip install redis")
    r = redis.Redis(host=args.get("host", "localhost"), port=args.get("port", 6379), password=args.get("password", "") or None, db=args.get("db", 0), decode_responses=True)
    r.ping()
    key = args["key"]
    val = r.get(key)
    if val is None:
        return {"key": key, "exists": False, "value": None}
    ttl = r.ttl(key)
    key_type = r.type(key)
    return {"key": key, "exists": True, "type": key_type, "value": val, "ttl": ttl}


def redis_set(args):
    if not HAS_REDIS:
        raise RuntimeError("redis not installed. Run: pip install redis")
    r = redis.Redis(host=args.get("host", "localhost"), port=args.get("port", 6379), password=args.get("password", "") or None, db=args.get("db", 0), decode_responses=True)
    r.ping()
    ex = args.get("ex", 0)
    ok = r.set(args["key"], args["value"], ex=ex if ex > 0 else None)
    return {"key": args["key"], "set": bool(ok), "ttl": ex if ex > 0 else "none"}


def redis_keys(args):
    if not HAS_REDIS:
        raise RuntimeError("redis not installed. Run: pip install redis")
    r = redis.Redis(host=args.get("host", "localhost"), port=args.get("port", 6379), password=args.get("password", "") or None, db=args.get("db", 0), decode_responses=True)
    r.ping()
    pattern = args.get("pattern", "*")
    limit = args.get("limit", 100)
    keys = []
    for k in r.scan_iter(match=pattern, count=limit):
        keys.append({"key": k, "type": r.type(k), "ttl": r.ttl(k)})
        if len(keys) >= limit:
            break
    return {"pattern": pattern, "keys": keys, "count": len(keys)}


def multi_backup(args):
    output_dir = args.get("output_dir", "./backups")
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {}
    pg_conf = args.get("postgres")
    if pg_conf and HAS_PSYCOPG2:
        try:
            import subprocess
            db = pg_conf.get("database", "")
            host = pg_conf.get("host", "localhost")
            port = pg_conf.get("port", 5432)
            user = pg_conf.get("user", "postgres")
            dump_file = os.path.join(output_dir, f"postgres_{db}_{ts}.sql")
            env = os.environ.copy()
            if pg_conf.get("password"):
                env["PGPASSWORD"] = pg_conf["password"]
            cmd = ["pg_dump", "-h", host, "-p", str(port), "-U", user, "-d", db, "-f", dump_file]
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
            results["postgres"] = {"status": "success" if proc.returncode == 0 else "error", "file": dump_file, "stderr": proc.stderr[:200] if proc.stderr else ""}
        except Exception as e:
            results["postgres"] = {"status": "error", "error": str(e)}
    elif pg_conf:
        results["postgres"] = {"status": "skipped", "reason": "psycopg2 not installed"}
    mongo_conf = args.get("mongo")
    if mongo_conf and HAS_PYMONGO:
        try:
            import subprocess
            uri = mongo_conf.get("uri", "mongodb://localhost:27017")
            db = mongo_conf.get("database", "")
            dump_dir = os.path.join(output_dir, f"mongo_{db}_{ts}")
            cmd = ["mongodump", f"--uri={uri}", f"--db={db}", f"--out={dump_dir}"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            results["mongo"] = {"status": "success" if proc.returncode == 0 else "error", "dir": dump_dir, "stderr": proc.stderr[:200] if proc.stderr else ""}
        except FileNotFoundError:
            results["mongo"] = {"status": "error", "error": "mongodump not found in PATH"}
        except Exception as e:
            results["mongo"] = {"status": "error", "error": str(e)}
    elif mongo_conf:
        results["mongo"] = {"status": "skipped", "reason": "pymongo not installed"}
    redis_conf = args.get("redis")
    if redis_conf and HAS_REDIS:
        try:
            r = redis.Redis(host=redis_conf.get("host", "localhost"), port=redis_conf.get("port", 6379), password=redis_conf.get("password", "") or None, db=redis_conf.get("db", 0))
            r.bgsave()
            results["redis"] = {"status": "bgsave_triggered", "note": "RDB snapshot will be saved by Redis background process"}
        except Exception as e:
            results["redis"] = {"status": "error", "error": str(e)}
    elif redis_conf:
        results["redis"] = {"status": "skipped", "reason": "redis-py not installed"}
    if not any([pg_conf, mongo_conf, redis_conf]):
        results = {"message": "No database configurations provided. Pass postgres, mongo, or redis objects.", "available_drivers": {"psycopg2": HAS_PSYCOPG2, "pymongo": HAS_PYMONGO, "redis": HAS_REDIS}}
    else:
        results["available_drivers"] = {"psycopg2": HAS_PSYCOPG2, "pymongo": HAS_PYMONGO, "redis": HAS_REDIS}
    return results


def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-db-multi", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            if name == "ctz_db_postgres_query":
                r = pg_query(args)
            elif name == "ctz_db_postgres_tables":
                r = pg_tables(args)
            elif name == "ctz_db_mongo_query":
                r = mongo_query(args)
            elif name == "ctz_db_mongo_collections":
                r = mongo_collections(args)
            elif name == "ctz_db_redis_get":
                r = redis_get(args)
            elif name == "ctz_db_redis_set":
                r = redis_set(args)
            elif name == "ctz_db_redis_keys":
                r = redis_keys(args)
            elif name == "ctz_db_multi_backup":
                r = multi_backup(args)
            else:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r, indent=2, default=str)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown method"}}


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = handle_request(json.loads(line.strip()))
            if r:
                sys.stdout.write(json.dumps(r) + "\n")
                sys.stdout.flush()
        except: pass
