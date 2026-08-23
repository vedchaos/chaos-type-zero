#!/usr/bin/env python3
"""CHAOS TYPE ZERO — Playwright Browser Automation (Real)"""
import json, sys, os, asyncio, hashlib, time

TOOLS = [
    {"name": "ctz_pw_open", "description": "Open URL in real browser", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "headless": {"type": "boolean", "default": True}}, "required": ["url"]}},
    {"name": "ctz_pw_click", "description": "Click element by CSS selector", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "selector": {"type": "string"}}, "required": ["url", "selector"]}},
    {"name": "ctz_pw_type", "description": "Type text into input field", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["url", "selector", "text"]}},
    {"name": "ctz_pw_scrape", "description": "Scrape page content", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "selector": {"type": "string", "default": "body"}}, "required": ["url"]}},
    {"name": "ctz_pw_screenshot", "description": "Take screenshot of page", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "output": {"type": "string"}}, "required": ["url"]}},
    {"name": "ctz_pw_fill_form", "description": "Fill form fields", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "fields": {"type": "object"}}, "required": ["url", "fields"]}},
    {"name": "ctz_pw_wait", "description": "Wait for element to appear", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "selector": {"type": "string"}, "timeout": {"type": "integer", "default": 10000}}, "required": ["url", "selector"]}},
    {"name": "ctz_pw_execute_js", "description": "Execute JavaScript on page", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "script": {"type": "string"}}, "required": ["url", "script"]}},
    {"name": "ctz_pw_navigate", "description": "Navigate to URL", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "goto": {"type": "string"}}, "required": ["url", "goto"]}},
    {"name": "ctz_pw_get_text", "description": "Get text content of element", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "selector": {"type": "string", "default": "body"}}, "required": ["url"]}},
]

# Check if Playwright is available
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Persistent browser session
_sessions = {}


async def _get_browser(headless=True):
    """Get or create browser instance."""
    if not PLAYWRIGHT_AVAILABLE:
        return None, "Playwright not installed. Run: pip install playwright && playwright install chromium"
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    return browser, None


async def handle_pw_open(params):
    url = params.get("url", "")
    headless = params.get("headless", True)
    browser, err = await _get_browser(headless)
    if err:
        return {"error": err}
    page = await browser.new_page()
    await page.goto(url)
    title = await page.title()
    content = await page.content()
    _sessions[url] = {"browser": browser, "page": page}
    return {"url": url, "title": title, "content_length": len(content), "status": "opened"}


async def handle_pw_click(params):
    url = params.get("url", "")
    selector = params.get("selector", "")
    session = _sessions.get(url)
    if not session:
        return {"error": f"No session for {url}. Open it first."}
    await session["page"].click(selector)
    return {"clicked": selector, "status": "success"}


async def handle_pw_type(params):
    url = params.get("url", "")
    selector = params.get("selector", "")
    text = params.get("text", "")
    session = _sessions.get(url)
    if not session:
        return {"error": f"No session for {url}. Open it first."}
    await session["page"].fill(selector, text)
    return {"typed": text, "into": selector, "status": "success"}


async def handle_pw_scrape(params):
    url = params.get("url", "")
    selector = params.get("selector", "body")
    session = _sessions.get(url)
    if not session:
        browser, err = await _get_browser()
        if err:
            return {"error": err}
        page = await browser.new_page()
        await page.goto(url)
        session = {"browser": browser, "page": page}
    text = await session["page"].eval_on_selector(selector, "el => el.innerText")
    return {"url": url, "selector": selector, "content": text[:5000]}


async def handle_pw_screenshot(params):
    url = params.get("url", "")
    output = params.get("output", f"screenshot_{hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:8]}.png")
    session = _sessions.get(url)
    if not session:
        browser, err = await _get_browser()
        if err:
            return {"error": err}
        page = await browser.new_page()
        await page.goto(url)
        session = {"browser": browser, "page": page}
    await session["page"].screenshot(path=output)
    return {"url": url, "screenshot": output, "status": "saved"}


async def handle_pw_fill_form(params):
    url = params.get("url", "")
    fields = params.get("fields", {})
    session = _sessions.get(url)
    if not session:
        return {"error": f"No session for {url}. Open it first."}
    for selector, value in fields.items():
        await session["page"].fill(selector, str(value))
    return {"filled": list(fields.keys()), "status": "success"}


async def handle_pw_wait(params):
    url = params.get("url", "")
    selector = params.get("selector", "")
    timeout = params.get("timeout", 10000)
    session = _sessions.get(url)
    if not session:
        return {"error": f"No session for {url}. Open it first."}
    await session["page"].wait_for_selector(selector, timeout=timeout)
    return {"selector": selector, "status": "found"}


async def handle_pw_execute_js(params):
    url = params.get("url", "")
    script = params.get("script", "")
    session = _sessions.get(url)
    if not session:
        return {"error": f"No session for {url}. Open it first."}
    result = await session["page"].eval_on_selector("body", f"() => {{ {script} }}")
    return {"url": url, "result": str(result)[:5000]}


async def handle_pw_navigate(params):
    url = params.get("url", "")
    goto = params.get("goto", "")
    session = _sessions.get(url)
    if not session:
        return {"error": f"No session for {url}. Open it first."}
    await session["page"].goto(goto)
    title = await session["page"].title()
    return {"navigated_to": goto, "title": title, "status": "success"}


async def handle_pw_get_text(params):
    url = params.get("url", "")
    selector = params.get("selector", "body")
    session = _sessions.get(url)
    if not session:
        browser, err = await _get_browser()
        if err:
            return {"error": err}
        page = await browser.new_page()
        await page.goto(url)
        session = {"browser": browser, "page": page}
    text = await session["page"].eval_on_selector(selector, "el => el.innerText")
    return {"url": url, "text": text[:5000]}


HANDLERS = {
    "ctz_pw_open": handle_pw_open,
    "ctz_pw_click": handle_pw_click,
    "ctz_pw_type": handle_pw_type,
    "ctz_pw_scrape": handle_pw_scrape,
    "ctz_pw_screenshot": handle_pw_screenshot,
    "ctz_pw_fill_form": handle_pw_fill_form,
    "ctz_pw_wait": handle_pw_wait,
    "ctz_pw_execute_js": handle_pw_execute_js,
    "ctz_pw_navigate": handle_pw_navigate,
    "ctz_pw_get_text": handle_pw_get_text,
}


def handle_request(request):
    method, params, req_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-playwright", "version": "1.0.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_params = params.get("arguments", {})
        handler = HANDLERS.get(tool_name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(handler(tool_params))
            loop.close()
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


if __name__ == "__main__":
    print("CTZ Playwright Browser MCP running", file=sys.stderr)
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue
