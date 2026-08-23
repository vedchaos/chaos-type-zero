#!/usr/bin/env python3
"""CTZ MCP — Stocks (Yahoo Finance public endpoints)"""
import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "stock-mcp", "version": "1.0.0"}
BASE_URL = "https://query1.finance.yahoo.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ctz-stock-mcp/1.0"}

PERIOD_RANGES = {
    "1d": ("1d", "5m"), "5d": ("5d", "30m"), "1mo": ("1mo", "1d"), "3mo": ("3mo", "1d"),
    "6mo": ("6mo", "1d"), "1y": ("1y", "1d"), "2y": ("2y", "1wk"), "5y": ("5y", "1wk"), "max": ("max", "1mo"),
}

SECTOR_ETFS = {
    "technology": ["XLK", "VGT"],
    "communication services": ["XLC", "VOX"],
    "financial services": ["XLF", "VFH"],
    "financials": ["XLF", "VFH"],
    "healthcare": ["XLV", "VHT"],
    "consumer cyclical": ["XLY", "VCR"],
    "consumer defensive": ["XLP", "VDC"],
    "energy": ["XLE", "VDE"],
    "industrials": ["XLI", "VIS"],
    "basic materials": ["XLB", "VAW"],
    "real estate": ["XLRE", "VNQ"],
    "utilities": ["XLU", "VPU"],
}

TOOLS = [
    {"name": "stock_quote", "description": "Current quote snapshot for a symbol.", "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "stock_history", "description": "Historical OHLCV bars. period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,max.", "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}, "period": {"type": "string", "default": "1mo"}}, "required": ["symbol"]}},
    {"name": "stock_info", "description": "Instrument info from Yahoo chart metadata (name, type, exchange, 52w range).", "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "stock_search", "description": "Search Yahoo Finance for symbols matching a query.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "stock_sector", "description": "Quotes for sector ETF proxies (e.g. 'Technology', 'Energy').", "inputSchema": {"type": "object", "properties": {"sector": {"type": "string"}}, "required": ["sector"]}},
]


def _yf_get(path, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = body[:300] or f"HTTP {exc.code}"
        if exc.code == 429:
            msg = "Yahoo rate-limited the request (429); retry shortly"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def _chart(symbol, rng="1d", interval="1d"):
    sym = urllib.parse.quote(symbol.strip())
    data = _yf_get(f"/v8/finance/chart/{sym}", {"range": rng, "interval": interval})
    if isinstance(data, dict) and "error" in data:
        return None, data
    results = ((data.get("chart") or {}).get("result")) or []
    if not results:
        err = (data.get("chart") or {}).get("error") or f"No data for symbol '{symbol}'"
        return None, {"error": err}
    meta = results[0].get("meta") or {}
    return results[0], meta


def stock_quote(symbol):
    _, meta = _chart(symbol)
    if meta and "error" in meta:
        return meta
    return {
        "symbol": meta.get("symbol"),
        "name": meta.get("longName") or meta.get("shortName"),
        "price": meta.get("regularMarketPrice"),
        "previous_close": meta.get("previousClose") or meta.get("chartPreviousClose"),
        "day_high": meta.get("regularMarketDayHigh"),
        "day_low": meta.get("regularMarketDayLow"),
        "volume": meta.get("regularMarketVolume"),
        "52w_high": meta.get("fiftyTwoWeekHigh"),
        "52w_low": meta.get("fiftyTwoWeekLow"),
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName"),
    }


def stock_history(symbol, period="1mo"):
    rng, interval = PERIOD_RANGES.get(str(period).lower(), PERIOD_RANGES["1mo"])
    res, meta = _chart(symbol, rng=rng, interval=interval)
    if res is None:
        return meta
    timestamps = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for i, ts in enumerate(timestamps):
        close = (quote.get("close") or [None] * len(timestamps))[i]
        if close is None:
            continue
        rows.append({
            "date": datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "open": (quote.get("open") or [None] * len(timestamps))[i],
            "high": (quote.get("high") or [None] * len(timestamps))[i],
            "low": (quote.get("low") or [None] * len(timestamps))[i],
            "close": close,
            "volume": (quote.get("volume") or [None] * len(timestamps))[i],
        })
    return {"symbol": meta.get("symbol"), "range": rng, "interval": interval, "bars": len(rows), "history": rows[:250]}


def stock_info(symbol):
    _, meta = _chart(symbol)
    if meta and "error" in meta:
        return meta
    return {
        "symbol": meta.get("symbol"),
        "full_name": meta.get("longName"),
        "short_name": meta.get("shortName"),
        "instrument_type": meta.get("instrumentType"),
        "exchange": meta.get("fullExchangeName"),
        "timezone": meta.get("exchangeTimezoneName"),
        "currency": meta.get("currency"),
        "price_hint": meta.get("priceHint"),
        "regular_market_price": meta.get("regularMarketPrice"),
        "52w_range": [meta.get("fiftyTwoWeekLow"), meta.get("fiftyTwoWeekHigh")],
        "source": "Yahoo Finance chart metadata",
    }


def stock_search(query):
    data = _yf_get("/v1/finance/search", {"q": query, "quotesCount": 10, "newsCount": 0})
    if isinstance(data, dict) and "error" in data:
        return data
    quotes = []
    for q in (data.get("quotes") or [])[:10]:
        quotes.append({
            "symbol": q.get("symbol"), "name": q.get("shortname") or q.get("longname"),
            "exchange": q.get("exchDisp") or q.get("exchange"), "type": q.get("quoteType"),
        })
    return {"query": query, "count": len(quotes), "results": quotes}


def stock_sector(sector):
    s = str(sector).strip().lower()
    etfs = SECTOR_ETFS.get(s)
    if not etfs:
        for k, v in SECTOR_ETFS.items():
            if k in s or s in k:
                etfs = v
                break
    if not etfs:
        return {"error": f"Unknown sector '{sector}'. Known sectors: " + ", ".join(sorted(set(SECTOR_ETFS)))}
    members = []
    for sym in etfs:
        q = stock_quote(sym)
        members.append({"proxy_etf": sym, **(q if isinstance(q, dict) else {})})
    return {"sector": sector, "members": members}


HANDLERS = {
    "stock_quote": stock_quote,
    "stock_history": stock_history,
    "stock_info": stock_info,
    "stock_search": stock_search,
    "stock_sector": stock_sector,
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
