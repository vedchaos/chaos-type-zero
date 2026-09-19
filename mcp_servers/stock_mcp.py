#!/usr/bin/env python3
"""
CHAOS TYPE ZERO - Stock Market MCP Tool
Live stock quotes via Yahoo Finance public API (no key required).
Usage: from mcp_servers.stock_mcp import stock_quote; stock_quote("AAPL")
"""

import json
import urllib.request

# Symbol -> display name map for common tickers
KNOWN = {
    "AAPL": "Apple Inc.",
    "TSLA": "Tesla Inc.",
    "MSFT": "Microsoft Corp.",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "NVDA": "NVIDIA Corp.",
    "META": "Meta Platforms Inc.",
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "RELIANCE": "Reliance Industries",
    "NIFTY": "NIFTY 50",
}


def stock_quote(symbol: str = "AAPL") -> dict:
    """Fetch a live quote for the given symbol (Yahoo Finance)."""
    symbol = (symbol or "AAPL").strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        day_high = meta.get("regularMarketDayHigh")
        day_low = meta.get("regularMarketDayLow")
        currency = meta.get("currency", "USD")
        name = meta.get("longName") or KNOWN.get(symbol, symbol)

        change = None
        change_pct = None
        if price is not None and prev_close:
            change = round(price - prev_close, 2)
            change_pct = round((change / prev_close) * 100, 2)

        return {
            "symbol": symbol,
            "name": name,
            "price": round(price, 2) if price is not None else "N/A",
            "currency": currency,
            "day_high": round(day_high, 2) if day_high is not None else "N/A",
            "day_low": round(day_low, 2) if day_low is not None else "N/A",
            "change": change,
            "change_pct": change_pct,
            "source": "Yahoo Finance",
        }
    except Exception as e:
        return {
            "symbol": symbol,
            "name": KNOWN.get(symbol, symbol),
            "price": "N/A",
            "currency": "USD",
            "day_high": "N/A",
            "day_low": "N/A",
            "change": None,
            "change_pct": None,
            "error": str(e),
            "source": "Yahoo Finance",
        }


if __name__ == "__main__":
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(json.dumps(stock_quote(sym), indent=2))