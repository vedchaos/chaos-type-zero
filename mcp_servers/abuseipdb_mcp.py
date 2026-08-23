#!/usr/bin/env python3
"""CTZ MCP — AbuseIPDB"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "abuseipdb-mcp", "version": "1.0.0"}
BASE_URL = "https://api.abuseipdb.com/api/v2"

TOOLS = [
    {"name": "abuse_check", "description": "Check an IP's abuse confidence score and reports (max_age_in_days up to 365).", "inputSchema": {"type": "object", "properties": {"ip": {"type": "string"}, "max_age_in_days": {"type": "integer", "default": 90}}, "required": ["ip"]}},
    {"name": "abuse_check_block", "description": "Check multiple IPs/CIDRs (comma/space separated). Plain IPs use /check, CIDRs use /check-block.", "inputSchema": {"type": "object", "properties": {"ip_list": {"type": "string"}, "max_age_in_days": {"type": "integer", "default": 30}}, "required": ["ip_list"]}},
    {"name": "abuse_blacklist", "description": "Fetch recently reported abusive IPs (limit max 10000; optional country filter like 'DE').", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 100}, "country": {"type": "string"}}, "required": []}},
]


def _headers():
    key = os.environ.get("ABUSEIPDB_API_KEY")
    if not key:
        return None
    return {"Key": key, "Accept": "application/json", "User-Agent": "ctz-mcp/1.0"}


def _get(path, params=None):
    headers = _headers()
    if not headers:
        return {"error": "ABUSEIPDB_API_KEY environment variable is not set"}
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        err = payload.get("errors")
        if err:
            return {"error": err[0].get("detail", str(err)) if isinstance(err, list) else str(err)}
        return payload.get("data", payload)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        try:
            detail = json.loads(body)
            errs = detail.get("errors") or []
            msg = errs[0].get("detail", body[:300]) if errs else (body[:300] or f"HTTP {exc.code}")
        except json.JSONDecodeError:
            msg = body[:500] or f"HTTP {exc.code}"
        if exc.code == 401:
            msg = "Invalid AbuseIPDB API key (401)"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def abuse_check(ip, max_age_in_days=90):
    days = min(max(int(max_age_in_days), 1), 365)
    return _get("/check", {"ipAddress": ip, "maxAgeInDays": days, "verbose": ""})


def abuse_check_block(ip_list, max_age_in_days=30):
    entries = [e.strip() for e in ip_list.replace(",", " ").split() if e.strip()]
    results = []
    days = min(max(int(max_age_in_days), 1), 365)
    for entry in entries[:25]:
        if "/" in entry:
            res = _get("/check-block", {"ipAddress": entry, "maxAgeInDays": days})
        else:
            res = _get("/check", {"ipAddress": entry, "maxAgeInDays": days, "verbose": ""})
        results.append({"target": entry, "result": res})
    return {"checked": len(results), "results": results}


def abuse_blacklist(limit=100, country=None):
    capped = min(int(limit), 10000)
    data = _get("/blacklist", {"confidenceMinimum": "100", "limit": capped})
    if isinstance(data, dict) and "error" in data:
        return data
    addresses = data.get("blacklistedIPs", []) if isinstance(data, dict) else []
    if country:
        cc = country.strip().upper()
        addresses = [a for a in addresses if (a.get("countryCode") or "").upper() == cc]
    return {"meta": data.get("meta"), "count": len(addresses), "blacklisted_ips": addresses[:capped]}


HANDLERS = {
    "abuse_check": abuse_check,
    "abuse_check_block": abuse_check_block,
    "abuse_blacklist": abuse_blacklist,
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
