#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Browser Automation Server"""

import json
import sys
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ── Simulated browser state ──────────────────────────────────────────────────

class BrowserTab:
    """Simulated browser tab holding page state."""
    def __init__(self, tab_id, url="about:blank"):
        self.tab_id = tab_id
        self.url = url
        self.title = ""
        self.html = ""
        self.text = ""
        self.links = []
        self.images = []
        self.forms = []
        self.history = [url]
        self.js_result = None
        self.cookies = {}
        self.headers = {}
        self.status_code = 200
        self.opened_at = time.time()
        self.last_accessed = time.time()

    def to_dict(self):
        return {
            "tab_id": self.tab_id,
            "url": self.url,
            "title": self.title,
            "links_count": len(self.links),
            "images_count": len(self.images),
            "status_code": self.status_code,
            "history_depth": len(self.history),
            "opened_at": self.opened_at,
            "last_accessed": self.last_accessed,
        }


class BrowserState:
    """Global browser state manager."""
    def __init__(self):
        self.tabs = {}
        self.active_tab_id = None
        self.next_tab_id = 1
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CTZ-Browser/1.0"
        self.default_timeout = 30
        self.screenshot_dir = Path(__file__).parent.parent / "data" / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def get_active_tab(self):
        if self.active_tab_id and self.active_tab_id in self.tabs:
            return self.tabs[self.active_tab_id]
        if self.tabs:
            return list(self.tabs.values())[-1]
        return None

    def create_tab(self, url="about:blank"):
        tab_id = f"tab-{self.next_tab_id}"
        self.next_tab_id += 1
        tab = BrowserTab(tab_id, url)
        self.tabs[tab_id] = tab
        self.active_tab_id = tab_id
        return tab

    def close_tab(self, tab_id=None):
        tid = tab_id or self.active_tab_id
        if tid and tid in self.tabs:
            del self.tabs[tid]
            if self.active_tab_id == tid:
                self.active_tab_id = list(self.tabs.keys())[-1] if self.tabs else None
            return True
        return False


_browser = BrowserState()


# ── HTTP fetch helpers ───────────────────────────────────────────────────────

def _fetch_url(url, timeout=30):
    """Fetch URL content using requests or urllib fallback."""
    headers = {"User-Agent": _browser.user_agent}
    if requests:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            return resp.text, resp.status_code, dict(resp.headers), resp.url
        except Exception as e:
            raise RuntimeError(f"requests failed: {e}")
    else:
        from urllib.request import Request, urlopen
        from urllib.error import URLError, HTTPError
        try:
            req = Request(url, headers=headers)
            resp = urlopen(req, timeout=timeout)
            html = resp.read().decode("utf-8", errors="replace")
            return html, resp.status, dict(resp.headers), resp.url
        except HTTPError as e:
            html = e.read().decode("utf-8", errors="replace") if e.fp else ""
            return html, e.code, {}, url
        except URLError as e:
            raise RuntimeError(f"urllib failed: {e.reason}")


def _parse_page(html, base_url):
    """Parse HTML into structured data."""
    result = {"text": "", "links": [], "images": [], "forms": []}
    if not BeautifulSoup:
        # Fallback: crude regex extraction
        result["text"] = re.sub(r'<[^>]+>', ' ', html)
        result["text"] = re.sub(r'\s+', ' ', result["text"]).strip()[:50000]
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html):
            result["links"].append({"text": "", "href": urljoin(base_url, m.group(1))})
        for m in re.finditer(r'src=["\']([^"\']+)["\']', html):
            result["images"].append({"alt": "", "src": urljoin(base_url, m.group(1))})
        return result

    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_tag = soup.find("title")
    result["title"] = title_tag.get_text(strip=True) if title_tag else ""

    # Text content
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    result["text"] = soup.get_text(separator="\n", strip=True)[:50000]

    # Links
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        result["links"].append({"text": a.get_text(strip=True)[:200], "href": href})

    # Images
    for img in soup.find_all("img"):
        src = urljoin(base_url, img.get("src", ""))
        result["images"].append({"alt": img.get("alt", ""), "src": src})

    # Forms
    for form in soup.find_all("form"):
        fd = {
            "action": urljoin(base_url, form.get("action", "")),
            "method": form.get("method", "GET").upper(),
            "inputs": [],
        }
        for inp in form.find_all(["input", "textarea", "select"]):
            fd["inputs"].append({
                "tag": inp.name,
                "name": inp.get("name", ""),
                "type": inp.get("type", "text"),
                "value": inp.get("value", ""),
            })
        result["forms"].append(fd)

    return result


def _evaluate_js(html, script):
    """Simulate JavaScript evaluation on fetched HTML.
    Supports: document.title, document.body.innerText, document.querySelectorAll, window.location.
    Returns a text approximation."""
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
    else:
        soup = None

    s = script.strip()

    if "document.title" in s:
        if soup:
            t = soup.find("title")
            return t.get_text(strip=True) if t else ""
        return ""

    if "document.body.innerText" in s or "document.body.textContent" in s:
        if soup:
            for tag in soup(["script", "style"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)[:20000]
        return re.sub(r'<[^>]+>', ' ', html)[:20000]

    if "document.querySelectorAll" in s:
        # Extract selector from querySelectorAll('...') or querySelectorAll("...")
        m = re.search(r'querySelectorAll\(["\']([^"\']+)["\']\)', s)
        if m and soup:
            selector = m.group(1)
            els = soup.select(selector)
            return json.dumps([e.get_text(strip=True)[:500] for e in els[:50]])
        return "[]"

    if "document.querySelector" in s:
        m = re.search(r'querySelector\(["\']([^"\']+)["\']\)', s)
        if m and soup:
            el = soup.select_one(m.group(1))
            return el.get_text(strip=True)[:2000] if el else ""
        return ""

    if "window.location" in s:
        return ""

    # Generic: return page text as fallback
    if soup:
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:10000]
    return re.sub(r'<[^>]+>', ' ', html)[:10000]


def _take_screenshot(tab, page_hash=None):
    """Save a text-based 'screenshot' (HTML snapshot) and return the path."""
    h = page_hash or hashlib.md5(tab.url.encode(), usedforsecurity=False).hexdigest()[:12]
    fname = f"screenshot_{tab.tab_id}_{h}.txt"
    fpath = _browser.screenshot_dir / fname
    content = f"[CTZ SCREENSHOT] {tab.url}\nTitle: {tab.title}\nStatus: {tab.status_code}\n\n{tab.text[:8000]}"
    fpath.write_text(content, encoding="utf-8")
    return str(fpath)


# ── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "ctz_browser_open",
        "description": "Open a URL, fetch the page, and return page info (title, text preview, links, images count).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to open"},
                "timeout": {"type": "integer", "description": "Request timeout in seconds", "default": 30},
            },
            "required": ["url"],
        },
    },
    {
        "name": "ctz_browser_navigate",
        "description": "Navigate the active tab to a new URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["url"],
        },
    },
    {
        "name": "ctz_browser_click",
        "description": "Simulate clicking a link by its href or by CSS selector match on text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Link text or CSS selector to match"},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "ctz_browser_type",
        "description": "Simulate typing into a form input by finding a matching form field.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Input name or CSS selector"},
                "value": {"type": "string", "description": "Text to type"},
            },
            "required": ["selector", "value"],
        },
    },
    {
        "name": "ctz_browser_screenshot",
        "description": "Take a text-based screenshot of the current page (saves HTML snapshot).",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "ctz_browser_scrape",
        "description": "Scrape the current page for text, links, and images.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["text", "links", "images", "all"], "default": "all"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "ctz_browser_tabs",
        "description": "List all open browser tabs.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "ctz_browser_close",
        "description": "Close the current or a specific tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Tab ID to close (optional, defaults to active)"},
            },
        },
    },
    {
        "name": "ctz_browser_evaluate",
        "description": "Run simulated JavaScript on the current page (supports document.title, body.innerText, querySelector, querySelectorAll).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "JavaScript expression to evaluate"},
            },
            "required": ["script"],
        },
    },
    {
        "name": "ctz_browser_wait",
        "description": "Wait for an element to appear (by text/selector match) or timeout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Text or selector to wait for"},
                "timeout": {"type": "integer", "default": 10},
            },
            "required": ["selector"],
        },
    },
]


# ── Tool handler ─────────────────────────────────────────────────────────────

def _handle_tool(name, args):
    tab = _browser.get_active_tab()

    if name == "ctz_browser_open":
        url = args["url"]
        timeout = args.get("timeout", _browser.default_timeout)
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        tab = _browser.create_tab(url)
        try:
            html, status, headers, final_url = _fetch_url(url, timeout)
        except Exception as e:
            return {"content": [{"type": "text", "text": json.dumps({"error": str(e), "url": url})}], "isError": True}

        parsed = _parse_page(html, final_url)
        tab.url = final_url
        tab.title = parsed.get("title", "")
        tab.html = html
        tab.text = parsed["text"]
        tab.links = parsed["links"]
        tab.images = parsed["images"]
        tab.forms = parsed["forms"]
        tab.status_code = status
        tab.headers = headers
        tab.cookies = {}
        tab.last_accessed = time.time()

        result = {
            "tab_id": tab.tab_id,
            "url": final_url,
            "title": tab.title,
            "status": status,
            "text_preview": tab.text[:1500],
            "links_count": len(tab.links),
            "images_count": len(tab.images),
            "forms_count": len(tab.forms),
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    if name == "ctz_browser_navigate":
        url = args["url"]
        timeout = args.get("timeout", _browser.default_timeout)
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if not tab:
            tab = _browser.create_tab(url)
        tab.url = url
        tab.history.append(url)
        try:
            html, status, headers, final_url = _fetch_url(url, timeout)
        except Exception as e:
            return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}

        parsed = _parse_page(html, final_url)
        tab.url = final_url
        tab.title = parsed.get("title", "")
        tab.html = html
        tab.text = parsed["text"]
        tab.links = parsed["links"]
        tab.images = parsed["images"]
        tab.forms = parsed["forms"]
        tab.status_code = status
        tab.headers = headers
        tab.last_accessed = time.time()

        return {"content": [{"type": "text", "text": json.dumps({
            "tab_id": tab.tab_id, "url": final_url, "title": tab.title,
            "status": status, "text_preview": tab.text[:1500],
            "links_count": len(tab.links), "images_count": len(tab.images),
        }, indent=2)}]}

    if name == "ctz_browser_click":
        if not tab or not tab.html:
            return {"content": [{"type": "text", "text": "No active page. Use ctz_browser_open first."}], "isError": True}
        selector = args["selector"]
        # Search links by text match or href match
        for link in tab.links:
            if selector.lower() in link.get("text", "").lower() or selector.lower() in link.get("href", "").lower():
                target_url = link["href"]
                try:
                    html, status, headers, final_url = _fetch_url(target_url)
                except Exception as e:
                    return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}
                parsed = _parse_page(html, final_url)
                tab.url = final_url
                tab.title = parsed.get("title", "")
                tab.html = html
                tab.text = parsed["text"]
                tab.links = parsed["links"]
                tab.images = parsed["images"]
                tab.forms = parsed["forms"]
                tab.status_code = status
                tab.history.append(final_url)
                tab.last_accessed = time.time()
                return {"content": [{"type": "text", "text": json.dumps({
                    "clicked": link["text"][:100], "url": final_url, "title": tab.title,
                    "status": status, "text_preview": tab.text[:1500],
                }, indent=2)}]}
        return {"content": [{"type": "text", "text": json.dumps({"error": f"No link matching '{selector}' found", "available_links": [l["text"][:60] for l in tab.links[:20]]})}], "isError": True}

    if name == "ctz_browser_type":
        if not tab:
            return {"content": [{"type": "text", "text": "No active tab."}], "isError": True}
        selector = args["selector"]
        value = args["value"]
        # Find matching form field
        for form in tab.forms:
            for inp in form["inputs"]:
                if selector.lower() in inp.get("name", "").lower() or selector.lower() in inp.get("type", "").lower():
                    inp["value"] = value
                    return {"content": [{"type": "text", "text": json.dumps({
                        "action": "typed", "field": inp["name"], "value": value,
                        "form_action": form["action"], "form_method": form["method"],
                    })}]}
        tab.forms.append({"action": tab.url, "method": "GET", "inputs": [{"name": selector, "type": "text", "value": value}]})
        return {"content": [{"type": "text", "text": json.dumps({"action": "typed", "field": selector, "value": value, "note": "No matching form found; field added to virtual form."})}]}

    if name == "ctz_browser_screenshot":
        if not tab or not tab.html:
            return {"content": [{"type": "text", "text": "No active page to screenshot."}], "isError": True}
        path = _take_screenshot(tab)
        return {"content": [{"type": "text", "text": json.dumps({"screenshot_path": path, "url": tab.url, "title": tab.title})}]}

    if name == "ctz_browser_scrape":
        if not tab or not tab.html:
            return {"content": [{"type": "text", "text": "No active page to scrape."}], "isError": True}
        mode = args.get("mode", "all")
        limit = args.get("limit", 50)
        result = {}
        if mode in ("text", "all"):
            result["text"] = tab.text[:20000]
        if mode in ("links", "all"):
            result["links"] = tab.links[:limit]
        if mode in ("images", "all"):
            result["images"] = tab.images[:limit]
        result["url"] = tab.url
        result["title"] = tab.title
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    if name == "ctz_browser_tabs":
        tabs_info = [t.to_dict() for t in _browser.tabs.values()]
        active = _browser.active_tab_id
        return {"content": [{"type": "text", "text": json.dumps({"tabs": tabs_info, "active_tab": active}, indent=2)}]}

    if name == "ctz_browser_close":
        tab_id = args.get("tab_id")
        closed = _browser.close_tab(tab_id)
        if closed:
            remaining = len(_browser.tabs)
            return {"content": [{"type": "text", "text": json.dumps({"closed": tab_id or "active", "remaining_tabs": remaining})}]}
        return {"content": [{"type": "text", "text": json.dumps({"error": "Tab not found"})}], "isError": True}

    if name == "ctz_browser_evaluate":
        if not tab or not tab.html:
            return {"content": [{"type": "text", "text": "No active page to evaluate script on."}], "isError": True}
        script = args["script"]
        result = _evaluate_js(tab.html, script)
        return {"content": [{"type": "text", "text": json.dumps({"result": result})}]}

    if name == "ctz_browser_wait":
        if not tab:
            return {"content": [{"type": "text", "text": "No active tab."}], "isError": True}
        selector = args["selector"]
        timeout = args.get("timeout", 10)
        # Poll: check if text/selector appears in current page
        deadline = time.time() + timeout
        while time.time() < deadline:
            if selector.lower() in tab.text.lower():
                return {"content": [{"type": "text", "text": json.dumps({"found": True, "waited": round(time.time() - (deadline - timeout), 2)})}]}
            # Refresh page and re-check
            try:
                html, status, headers, final_url = _fetch_url(tab.url, timeout=min(5, timeout))
                parsed = _parse_page(html, final_url)
                tab.html = html
                tab.text = parsed["text"]
                tab.links = parsed["links"]
                tab.images = parsed["images"]
                tab.status_code = status
            except Exception:
                pass
            time.sleep(1)
        return {"content": [{"type": "text", "text": json.dumps({"found": False, "waited": timeout, "message": f"'{selector}' not found within {timeout}s"})}]}

    return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}


# ── MCP JSON-RPC handler ────────────────────────────────────────────────────

def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "ctz-browser", "version": "1.0.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            result = _handle_tool(name, args)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown method"}}


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = handle_request(json.loads(line.strip()))
            if r:
                sys.stdout.write(json.dumps(r) + "\n")
                sys.stdout.flush()
        except Exception:
            pass
