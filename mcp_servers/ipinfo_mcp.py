#!/usr/bin/env python3
"""CTZ MCP — IP Info"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "ipinfo-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "ipinfo_lookup", "description": "Lookup details (geo, ASN, org) for a single IP.", "inputSchema": {"type": "object", "properties": {"ip": {"type": "string"}}, "required": ["ip"]}},
    {"name": "ipinfo_bulk", "description": "Bulk lookup up to 100 IPs (comma/space separated string or JSON array). Requires a paid ipinfo token for /batch.", "inputSchema": {"type": "object", "properties": {"ips": {}}, "required": ["ips"]}},
    {"name": "ipinfo_my_ip", "description": "Details of your own public IP.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


def _token():
    return os.environ.get("IPINFO_TOKEN") or os.environ.get("IPINFO_APIKEY") or ""


def _get(path, params=None):
    p = dict(params or {})
    tok = _token()
    if tok:
        p["token"] = tok
    url = "https://ipinfo.io" + path
    if p:
        url += "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": "ctz-ipinfo-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw[:4000]}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = detail[:300] or f"HTTP {exc.code}"
        if exc.code in (401, 403):
            msg = f"ipinfo rejected the request ({exc.code}); token may be missing/insufficient"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def ipinfo_lookup(ip):
    return _get(f"/{urllib.parse.quote(str(ip))}/json")


def ipinfo_bulk(ips):
    if isinstance(ips, str):
        items = [x.strip() for x in ips.replace(",", " ").split() if x.strip()]
    else:
        items = [str(x).strip() for x in list(ips)[:100]]
    if not items:
        return {"error": "No valid IPs provided"}
    tok = _token()
    url = "https://ipinfo.io/batch"
    if tok:
        url += "?token=" + urllib.parse.quote(tok)
    req = urllib.request.Request(url, data=json.dumps(items).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "ctz-ipinfo-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"error": detail[:300] or f"HTTP {exc.code} (/batch requires a paid ipinfo token)", "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def ipinfo_my_ip():
    return _get("/json")


HANDLERS = {
    "ipinfo_lookup": ipinfo_lookup,
    "ipinfo_bulk": ipinfo_bulk,
    "ipinfo_my_ip": ipinfo_my_ip,
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
