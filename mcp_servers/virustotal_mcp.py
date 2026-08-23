#!/usr/bin/env python3
"""CTZ MCP — VirusTotal"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "virustotal-mcp", "version": "1.0.0"}
BASE_URL = "https://www.virustotal.com/api/v3"

TOOLS = [
    {"name": "vt_scan_url", "description": "Submit a URL for scanning; returns an analysis id.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "vt_scan_file", "description": "Trigger a rescan/analysis of a known file by SHA256 hash.", "inputSchema": {"type": "object", "properties": {"file_hash": {"type": "string"}}, "required": ["file_hash"]}},
    {"name": "vt_url_report", "description": "Get a URL's analysis report (reputation, categories, last scan stats).", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "vt_ip_report", "description": "Get an IP address report (as-owner, resolutions, detected files).", "inputSchema": {"type": "object", "properties": {"ip": {"type": "string"}}, "required": ["ip"]}},
    {"name": "vt_domain_report", "description": "Get a domain report (DNS records, subdomains, categories).", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
]


def _req(path, method="GET", form=None):
    key = os.environ.get("VIRUSTOTAL_API_KEY")
    if not key:
        return {"error": "VIRUSTOTAL_API_KEY environment variable is not set"}
    headers = {"x-apikey": key, "Accept": "application/json", "User-Agent": "ctz-mcp/1.0"}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        try:
            detail = json.loads(body)
            msg = detail.get("error", {}).get("message") or detail
        except json.JSONDecodeError:
            msg = body[:500] or f"HTTP {exc.code}"
        if exc.code == 401:
            msg = "Invalid VirusTotal API key (401)"
        elif exc.code == 429:
            msg = "Rate limit / quota exceeded (429)"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def vt_scan_url(url):
    return _req("/urls", method="POST", form={"url": url})


def vt_scan_file(file_hash):
    return _req(f"/files/{urllib.parse.quote(file_hash)}/analyse", method="POST")


def vt_url_report(url):
    url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return _req(f"/urls/{url_id}")


def vt_ip_report(ip):
    return _req(f"/ip_addresses/{urllib.parse.quote(ip)}")


def vt_domain_report(domain):
    return _req(f"/domains/{urllib.parse.quote(domain)}")


HANDLERS = {
    "vt_scan_url": vt_scan_url,
    "vt_scan_file": vt_scan_file,
    "vt_url_report": vt_url_report,
    "vt_ip_report": vt_ip_report,
    "vt_domain_report": vt_domain_report,
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
