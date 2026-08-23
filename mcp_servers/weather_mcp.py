#!/usr/bin/env python3
"""CTZ MCP — Weather (wttr.in)"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "weather-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "weather_current", "description": "Current weather conditions for a city.", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}},
    {"name": "weather_forecast", "description": "Multi-day forecast (wttr.in provides 3 days).", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}, "days": {"type": "integer", "default": 3}}, "required": ["city"]}},
    {"name": "weather_alerts", "description": "Active weather alerts via US National Weather Service (uses coordinates resolved by wttr.in; non-US areas may have no coverage).", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}},
]


def _j1(city):
    url = f"https://wttr.in/{urllib.parse.quote(str(city))}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0 ctz-weather-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code} for '{city}'"}
    except Exception as exc:
        return {"error": str(exc)}


def _area(data):
    areas = data.get("nearest_area") or []
    if not areas:
        return None
    a = areas[0]
    names = [x.get("value") for x in (a.get("areaName") or []) if isinstance(x, dict)]
    region = [x.get("value") for x in (a.get("region") or []) if isinstance(x, dict)]
    country = [x.get("value") for x in (a.get("country") or []) if isinstance(x, dict)]
    return {"name": next(iter(names), ""), "region": next(iter(region), ""),
            "country": next(iter(country), ""), "latitude": a.get("latitude"), "longitude": a.get("longitude")}


def weather_current(city):
    data = _j1(city)
    if isinstance(data, dict) and "error" in data:
        return data
    conds = data.get("current_condition") or []
    if not conds:
        return {"error": "No current conditions returned"}
    cc = conds[0]
    desc_list = cc.get("weatherDesc") or [{}]
    area = _area(data) or {}
    return {
        "location": area,
        "observed": cc.get("localObsDateTime"),
        "temp_c": cc.get("temp_C"),
        "temp_f": cc.get("temp_F"),
        "feels_like_c": cc.get("FeelsLikeC"),
        "condition": (desc_list[0] or {}).get("value"),
        "humidity_pct": cc.get("humidity"),
        "wind_kmph": cc.get("windspeedKmph"),
        "wind_dir": cc.get("winddir16Point"),
        "precip_mm": cc.get("precipMM"),
        "pressure_hpa": cc.get("pressure"),
        "cloud_cover_pct": cc.get("cloudcover"),
        "uv_index": cc.get("uvIndex"),
        "visibility_km": cc.get("visibility"),
    }


def weather_forecast(city, days=3):
    data = _j1(city)
    if isinstance(data, dict) and "error" in data:
        return data
    days_data = data.get("weather") or []
    picked = days_data[:max(1, min(int(days), len(days_data)))]
    out = []
    for d in picked:
        hourly = []
        for h in d.get("hourly", []):
            wd = (h.get("weatherDesc") or [{}])[0].get("value")
            hourly.append({"time": h.get("time"), "temp_c": h.get("tempC"), "condition": wd,
                           "chance_of_rain_pct": h.get("chanceofrain"), "wind_kmph": h.get("windspeedKmph")})
        astro = (d.get("astronomy") or [{}])[0]
        out.append({"date": d.get("date"), "max_temp_c": d.get("maxtempC"), "min_temp_c": d.get("mintempC"),
                    "sunrise": astro.get("sunrise"), "sunset": astro.get("sunset"), "hourly": hourly})
    return {"location": _area(data), "days": len(out), "forecast": out}


def weather_alerts(city):
    data = _j1(city)
    if isinstance(data, dict) and "error" in data:
        return data
    area = _area(data)
    lat, lon = (area or {}).get("latitude"), (area or {}).get("longitude")
    if lat is None or lon is None:
        return {"error": "Could not resolve coordinates for city"}
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}&limit=20"
    req = urllib.request.Request(url, headers={"User-Agent": "(ctz-weather-mcp, contact: local)", "Accept": "application/geo+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return {"error": f"NWS returned HTTP {exc.code}", "note": "Alerts are US-only via api.weather.gov"}
    except Exception as exc:
        return {"error": str(exc)}
    alerts = []
    for feat in payload.get("features", []):
        props = feat.get("properties") or {}
        alerts.append({"event": props.get("event"), "severity": props.get("severity"),
                       "headline": props.get("headline"), "areas": props.get("areaDesc"),
                       "onset": props.get("onset"), "ends": props.get("ends")})
    return {"location": area, "source": "api.weather.gov", "alert_count": len(alerts), "alerts": alerts}


HANDLERS = {
    "weather_current": weather_current,
    "weather_forecast": weather_forecast,
    "weather_alerts": weather_alerts,
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
