#!/usr/bin/env python3
"""CTZ MCP — DNS (dig/nslookup)"""
import json
import sys
import subprocess

SERVER_INFO = {"name": "dns-mcp", "version": "1.0.0"}

VALID_TYPES = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "SRV", "PTR", "CAA", "ANY"]

TOOLS = [
    {"name": "dns_lookup", "description": f"Look up DNS records of a type ({', '.join(VALID_TYPES)}). Uses dig, falls back to nslookup.", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}, "record_type": {"type": "string", "default": "A"}}, "required": ["domain"]}},
    {"name": "dns_reverse", "description": "Reverse DNS (PTR) lookup for an IP.", "inputSchema": {"type": "object", "properties": {"ip": {"type": "string"}}, "required": ["ip"]}},
    {"name": "dns_zone_transfer", "description": "Attempt an AXFR zone transfer (usually refused by servers).", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
    {"name": "dns_mx", "description": "MX record lookup for a domain.", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
    {"name": "dns_txt", "description": "TXT record lookup (SPF/DKIM/verification) for a domain.", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
]


def _run(args, timeout=20):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def _dig_ok(res):
    if res.get("returncode") != 0:
        return False
    out = res.get("stdout", "")
    return bool(out.strip()) and "Tool not installed" not in str(res.get("error", ""))


def dns_lookup(domain, record_type="A"):
    rtype = str(record_type).strip().upper()
    if rtype not in VALID_TYPES:
        return {"error": f"Unsupported record type '{record_type}'. Valid: {', '.join(VALID_TYPES)}"}
    res = _run(["dig", "+short", str(domain), rtype])
    if _dig_ok(res):
        res["tool"] = "dig"
        res["records"] = [l.strip() for l in res["stdout"].splitlines() if l.strip()]
        return res
    alt = _run(["nslookup", "-type=" + rtype, str(domain)])
    if alt.get("returncode") == 0:
        alt["tool"] = "nslookup"
        return alt
    return res


def dns_reverse(ip):
    res = _run(["dig", "+short", "-x", str(ip)])
    if _dig_ok(res):
        res["tool"] = "dig"
        res["hostnames"] = [l.strip() for l in res["stdout"].splitlines() if l.strip()]
        return res
    alt = _run(["nslookup", str(ip)], timeout=15)
    if alt.get("returncode") == 0:
        alt["tool"] = "nslookup"
        return alt
    return res


def dns_zone_transfer(domain):
    res = _run(["dig", str(domain), "AXFR"], timeout=45)
    if "Tool not installed" in str(res.get("error", "")):
        return {"error": "dig not installed; nslookup cannot perform AXFR"}
    lines = [l.strip() for l in res.get("stdout", "").splitlines() if l.strip()]
    transferred = any(l.upper().endswith(("SOA", "NS")) and l.count("\t") > 0 for l in lines) and res.get("returncode") == 0
    return {"domain": domain, "transfer_succeeded": bool(transferred and res.get("returncode") == 0 and len(lines) > 5), "records_found": len(lines), "output_lines": lines[:100], "stderr": res.get("stderr", "")}


def dns_mx(domain):
    return dns_lookup(domain, "MX")


def dns_txt(domain):
    res = dns_lookup(domain, "TXT")
    if isinstance(res, dict) and "stdout" in res:
        joined = " | ".join(l.replace('"', '').strip() for l in res["stdout"].splitlines() if l.strip())
        res["joined"] = joined[:4000]
    return res


HANDLERS = {
    "dns_lookup": dns_lookup,
    "dns_reverse": dns_reverse,
    "dns_zone_transfer": dns_zone_transfer,
    "dns_mx": dns_mx,
    "dns_txt": dns_txt,
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
