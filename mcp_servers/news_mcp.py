#!/usr/bin/env python3
"""CTZ MCP — News (RSS aggregators)"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
# SECURITY: swapped stdlib ET for defusedxml to prevent XXE/billion-laughs
# attacks from malicious RSS/Atom feeds (this parses untrusted network data)
import defusedxml.ElementTree as ET

SERVER_INFO = {"name": "news-mcp", "version": "1.0.0"}

FEEDS = {
    "top": [
        ("BBC", "https://feeds.bbci.co.uk/news/rss.xml"),
        ("CNN", "http://rss.cnn.com/rss/cnn_topstories.rss"),
        ("NPR", "https://feeds.npr.org/1001/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/world/rss"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ],
    "world": [
        ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("The Guardian", "https://www.theguardian.com/world/rss"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ],
    "business": [
        ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ],
    "technology": [
        ("BBC", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/uk/technology/rss"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ],
    "science": [
        ("BBC", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml"),
        ("Phys.org", "https://phys.org/rss-feed/"),
    ],
    "sports": [
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
        ("ESPN", "https://www.espn.com/espn/rss/news"),
        ("Sky Sports", "https://www.skysports.com/rss/12040"),
    ],
    "politics": [
        ("NPR", "https://feeds.npr.org/1014/rss.xml"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"),
        ("The Guardian", "https://www.theguardian.com/politics/rss"),
    ],
    "health": [
        ("BBC", "https://feeds.bbci.co.uk/news/health/rss.xml"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml"),
    ],
    "entertainment": [
        ("BBC", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"),
        ("NYT Arts", "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml"),
        ("Variety", "https://variety.com/feed/"),
    ],
}

TOOLS = [
    {"name": "news_headlines", "description": "Top headlines per category from major sources. Categories: " + ", ".join(FEEDS), "inputSchema": {"type": "object", "properties": {"category": {"type": "string", "default": "top"}, "limit_per_source": {"type": "integer", "default": 5}}, "required": []}},
    {"name": "news_search", "description": "Search news articles across sources via Google News RSS.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 15}}, "required": ["query"]}},
    {"name": "news_sources", "description": "List all configured news categories and feed URLs.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


def _fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ctz-news-mcp/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_feed(data, limit):
    root = ET.fromstring(data)
    local = lambda tag: tag.rsplit("}", 1)[-1]
    items = [el for el in root.iter() if local(el.tag) in ("item", "entry")]
    out = []
    for it in items[:limit]:
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
                text = (el.text or "").strip()
                if href and el.get("rel", "alternate") == "alternate":
                    link = href
                    break
                if href and not link:
                    link = href
                elif text and not link:
                    link = text
        out.append({"title": g("title"), "link": link,
                    "summary": g("description", "summary", "content")[:300],
                    "published": g("pubDate", "published", "updated", "date")})
    return out


def news_headlines(category="top", limit_per_source=5):
    cat = str(category).lower().strip()
    feeds = FEEDS.get(cat)
    if feeds is None:
        for k in FEEDS:
            if k in cat:
                feeds = FEEDS[k]
                break
    if feeds is None:
        return {"error": f"Unknown category '{category}'. Available: {', '.join(sorted(FEEDS))}"}
    headlines = []
    errors = []
    for source, url in feeds:
        try:
            data = _fetch(url)
            for item in _parse_feed(data, int(limit_per_source)):
                item["source"] = source
                headlines.append(item)
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    return {"category": cat, "sources_ok": len(feeds) - len(errors), "headlines": headlines[:40], "source_errors": errors}


def news_search(query, limit=15):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        data = _fetch(url, timeout=20)
        items = _parse_feed(data, int(limit))
        return {"query": query, "count": len(items), "articles": items}
    except Exception as exc:
        return {"error": str(exc)}


def news_sources():
    return {"categories": {k: [{"source": s, "url": u} for s, u in v] for k, v in FEEDS.items()}}


HANDLERS = {
    "news_headlines": news_headlines,
    "news_search": news_search,
    "news_sources": news_sources,
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
