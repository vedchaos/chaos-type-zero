#!/usr/bin/env python3
"""CTZ MCP — Censys"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "censys-mcp", "version": "1.0.0"}
BASE_URL = "https://search.censys.io/api/v2"

TOOLS = [
    {"name": "censys_search_hosts", "description": "Search internet-exposed hosts (Censys query syntax).", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "per_page": {"type": "integer", "default": 25}}, "required": ["query"]}},
    {"name": "censys_get_host", "description": "Full host details for an IP (services, software, AS, location).", "inputSchema": {"type": "object", "properties": {"ip": {"type": "string"}}, "required": ["ip"]}},
    {"name": "censys_search_certificates", "description": "Search X.509 certificates in Censys.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "per_page": {"type": "integer", "default": 25}}, "required": ["query"]}},
]


def _auth_header():
    api_id = os.environ.get("CENSYS_API_ID")
    secret = os.environ.get("CENSYS_API_SECRET")
    if not api_id or not secret:
        return None
    raw = f"{api_id}:{secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _req(method, path, data=None):
    auth = _auth_header()
    if auth is None:
        return {"error": "Set CENSYS_API_ID and CENSYS_API_SECRET environment variables"}
    headers = {"Authorization": auth, "Accept": "application/json",
               "Content-Type": "application/json", "User-Agent": "ctz-censys-mcp/1.0"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE_URL + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = detail[:400] or f"HTTP {exc.code}"
        if exc.code == 401:
            msg = "Invalid Censys credentials (401)"
        elif exc.code == 403:
            msg = "Forbidden: account lacks access to this endpoint (403)"
        elif exc.code == 429:
            msg = "Censys rate limit exceeded (429)"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def censys_search_hosts(query, per_page=25):
    body = {"q": query, "per_page": min(int(per_page), 100), "virtual_hosts": "EXCLUDE"}
    result = _req("POST", "/hosts/search", body)
    inner = result.get("result") if isinstance(result, dict) else None
    hits = (inner or {}).get("hits")
    if not isinstance(hits, list):
        return result
    trimmed = []
    for h in hits[:int(per_page)]:
        loc = h.get("location") or {}
        services = [{"port": s.get("port"), "protocol": s.get("transport_protocol"),
                     "service_name": s.get("service_name")} for s in (h.get("services") or [])[:10]]
        trimmed.append({"ip": h.get("ip"),
                        "last_update_time": h.get("last_update_time"),
                        "country": loc.get("country"), "city": loc.get("city"),
                        "autonomous_system": (h.get("autonomous_system") or {}).get("description"),
                        "services_preview": services})
    return {"total": (inner or {}).get("total"), "returned": len(trimmed), "hits": trimmed}


def censys_get_host(ip):
    result = _req("GET", "/hosts/" + urllib.parse.quote(str(ip)))
    if not isinstance(result, dict) or "error" in result:
        return result
    data = result.get("result") or {}
    services = []
    for s in (data.get("services") or [])[:20]:
        sws = [sw.get("product") for sw in (s.get("software") or [])[:5] if isinstance(sw, dict)]
        cves = [v.get("cve") for v in (s.get("vulnerabilities") or [])[:10] if isinstance(v, dict) and v.get("cve")]
        services.append({"service_name": s.get("service_name"), "port": s.get("port"),
                         "transport_protocol": s.get("transport_protocol"),
                         "observed_at": s.get("observed_at"), "software": sws,
                         "vulnerabilities": cves})
    dns_block = data.get("dns") or {}
    return {"ip": ip, "location": data.get("location"),
            "autonomous_system": data.get("autonomous_system"),
            "dns_names": (dns_block.get("names") or []),
            "service_count": len(data.get("services") or []),
            "services": services}


def censys_search_certificates(query, per_page=25):
    body = {"q": query, "per_page": min(int(per_page), 100)}
    result = _req("POST", "/certificates/search", body)
    inner = result.get("result") if isinstance(result, dict) else None
    hits = (inner or {}).get("hits")
    if not isinstance(hits, list):
        return result
    trimmed = [{"fingerprint_sha256": h.get("fingerprint_sha256") or h.get("id"),
                "names": (h.get("names") or [])[:10],
                "issuer_cn": ((h.get("issuer") or {}).get("common_name") or [None])[0] if isinstance((h.get("issuer") or {}).get("common_name"), list) else (h.get("issuer") or {}).get("common_name"),
                "added_at": h.get("added_at")} for h in hits[:int(per_page)]]
    return {"total": (inner or {}).get("total"), "returned": len(trimmed), "hits": trimmed}


HANDLERS = {
    "censys_search_hosts": censys_search_hosts,
    "censys_get_host": censys_get_host,
    "censys_search_certificates": censys_search_certificates,
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
