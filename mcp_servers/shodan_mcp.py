#!/usr/bin/env python3
"""CTZ MCP — Shodan"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "shodan-mcp", "version": "1.0.0"}
BASE_URL = "https://api.shodan.io"

TOOLS = [
    {"name": "shodan_host_info", "description": "All known info/banner history for an IP.", "inputSchema": {"type": "object", "properties": {"ip": {"type": "string"}}, "required": ["ip"]}},
    {"name": "shodan_search", "description": "Search Shodan banner index (e.g. 'apache country:DE').", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}},
    {"name": "shodan_dns_lookup", "description": "Reverse DNS for an IP via Shodan DNS service.", "inputSchema": {"type": "object", "properties": {"ip": {"type": "string"}}, "required": ["ip"]}},
    {"name": "shodan_my_ip", "description": "Your current public IP as seen by Shodan.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "shodan_api_info", "description": "API plan info: query credits, scan credits, HTTPS enabled.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


def _get(path, extra_params=None):
    key = os.environ.get("SHODAN_API_KEY")
    if not key:
        return {"error": "SHODAN_API_KEY environment variable is not set"}
    params = {"key": key}
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ctz-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        try:
            detail = json.loads(body)
            msg = detail.get("error") or detail
        except json.JSONDecodeError:
            msg = body[:500] or f"HTTP {exc.code}"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def shodan_host_info(ip):
    return _get(f"/shodan/host/{urllib.parse.quote(ip)}")


def shodan_search(query, limit=10):
    data = _get("/shodan/host/search", {"query": query})
    matches = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(matches, list):
        return data
    trimmed = []
    for m in matches[:int(limit)]:
        loc = m.get("location") or {}
        trimmed.append({
            "ip_str": m.get("ip_str"), "port": m.get("port"), "transport": m.get("transport"),
            "product": m.get("product"), "version": m.get("version"), "os": m.get("os"),
            "org": m.get("org"), "isp": m.get("isp"), "asn": m.get("asn"),
            "hostnames": m.get("hostnames", [])[:5], "domains": m.get("domains", [])[:5],
            "country": loc.get("country_name"), "city": loc.get("city"),
            "timestamp": m.get("timestamp"), "data_preview": (m.get("data") or "")[:300],
        })
    return {"total": data.get("total"), "returned": len(trimmed), "matches": trimmed}


def shodan_dns_lookup(ip):
    return _get("/dns/reverse", {"ips": ip})


def shodan_my_ip():
    return _get("/tools/myip")


def shodan_api_info():
    return _get("/api-info")


HANDLERS = {
    "shodan_host_info": shodan_host_info,
    "shodan_search": shodan_search,
    "shodan_dns_lookup": shodan_dns_lookup,
    "shodan_my_ip": shodan_my_ip,
    "shodan_api_info": shodan_api_info,
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
