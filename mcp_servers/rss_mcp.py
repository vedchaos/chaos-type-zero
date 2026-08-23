#!/usr/bin/env python3
"""CTZ MCP — RSS Feeds"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

SERVER_INFO = {"name": "rss-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "rss_parse", "description": "Fetch and parse an RSS/Atom feed URL; returns items.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["url"]}},
    {"name": "rss_discover", "description": "Discover RSS/Atom feed links declared in an HTML page.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "rss_search", "description": "Search news via Google News RSS.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, "required": ["query"]}},
]


def _fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ctz-rss-mcp/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.geturl()


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_feed(data, limit):
    root = ET.fromstring(data)
    local = lambda tag: tag.rsplit("}", 1)[-1]
    root_kind = local(root.tag)
    if root_kind in ("rss", "RDF"):
        items = [el for el in root.iter() if local(el.tag) == "item"]
        feed_title_el = next((el for el in root.iter() if local(el.tag) == "title"), None)
        kind = "rss"
    else:
        items = [el for el in root.iter() if local(el.tag) == "entry"]
        feed_title_el = next((el for el in root.iter() if local(el.tag) == "title"), None)
        kind = "atom"
    out = []
    for it in items[:int(limit)]:
        def g(*names):
            for n in names:
                for el in it.iter():
                    if local(el.tag) == n and (el.text or "").strip():
                        return _clean(el.text)
            return ""
        link = ""
        for el in it.iter():
            if local(el.tag) == "link":
                href = el.get("href")
                rel = el.get("rel", "alternate")
                text = (el.text or "").strip()
                if href and rel == "alternate":
                    link = href
                    break
                if href and not link:
                    link = href
                elif text and not link:
                    link = text
        out.append({
            "title": g("title"),
            "link": link,
            "summary": g("description", "summary", "content")[:500],
            "published": g("pubDate", "published", "updated", "date"),
        })
    return {"feed_title": _clean(feed_title_el.text) if feed_title_el is not None else "", "kind": kind, "count": len(out), "items": out}


def rss_parse(url, limit=10):
    try:
        data, final_url = _fetch(url)
        result = _parse_feed(data, limit)
        result["url"] = final_url
        return result
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code} fetching {url}"}
    except ET.ParseError:
        return {"error": "Response is not valid XML/RSS (page may be HTML or blocked)"}
    except Exception as exc:
        return {"error": str(exc)}


def rss_discover(url):
    try:
        data, final_url = _fetch(url)
        html = data.decode("utf-8", errors="replace")
        pattern = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
        feeds = []
        seen = set()
        for m in pattern.finditer(html):
            tag = m.group(0)
            tmatch = re.search(r'type\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
            hmatch = re.search(r'href\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if not tmatch or not hmatch:
                continue
            mime = tmatch.group(1).lower()
            if any(x in mime for x in ("rss+xml", "atom+xml", "feed+json")):
                href = urljoin(final_url, hmatch.group(1).strip())
                if href not in seen:
                    seen.add(href)
                    feeds.append({"type": mime, "href": href})
        return {"page": final_url, "feeds_found": len(feeds), "feeds": feeds}
    except Exception as exc:
        return {"error": str(exc)}


def rss_search(query, limit=20):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        data, _ = _fetch(url)
        result = _parse_feed(data, limit)
        result["query"] = query
        return result
    except Exception as exc:
        return {"error": str(exc)}


HANDLERS = {
    "rss_parse": rss_parse,
    "rss_discover": rss_discover,
    "rss_search": rss_search,
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
