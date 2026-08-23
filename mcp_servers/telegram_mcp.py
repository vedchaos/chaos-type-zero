#!/usr/bin/env python3
"""CTZ MCP — Telegram Bot"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "telegram-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "tg_send_message", "description": "Send a text message to a chat.", "inputSchema": {"type": "object", "properties": {"chat_id": {"type": "string"}, "text": {"type": "string"}}, "required": ["chat_id", "text"]}},
    {"name": "tg_get_me", "description": "Get the bot's own profile (getMe).", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "tg_get_updates", "description": "Fetch recent updates/messages sent to the bot.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}, "required": []}},
    {"name": "tg_forward_message", "description": "Forward a message between chats.", "inputSchema": {"type": "object", "properties": {"chat_id": {"type": "string"}, "from_chat_id": {"type": "string"}, "message_id": {"type": "integer"}}, "required": ["chat_id", "from_chat_id", "message_id"]}},
    {"name": "tg_answer_callback", "description": "Answer an inline-keyboard callback query (stops the loading spinner, optional toast text).", "inputSchema": {"type": "object", "properties": {"callback_query_id": {"type": "string"}, "text": {"type": "string"}}, "required": ["callback_query_id"]}},
]


def _api(method, params=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"error": "TELEGRAM_BOT_TOKEN environment variable is not set"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "ctz-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", errors="replace"))
            return {"error": detail.get("description", f"HTTP {exc.code}"), "error_code": detail.get("error_code", exc.code)}
        except Exception:
            return {"error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"error": str(exc)}
    if not data.get("ok"):
        return {"error": data.get("description", "Telegram API error"), "error_code": data.get("error_code")}
    return data.get("result")


def tg_send_message(chat_id, text):
    return _api("sendMessage", {"chat_id": chat_id, "text": text})


def tg_get_me():
    return _api("getMe")


def tg_get_updates(limit=10):
    return _api("getUpdates", {"limit": int(limit)})


def tg_forward_message(chat_id, from_chat_id, message_id):
    return _api("forwardMessage", {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": int(message_id)})


def tg_answer_callback(callback_query_id, text=None):
    params = {"callback_query_id": callback_query_id}
    if text:
        params["text"] = text
    return _api("answerCallbackQuery", params)


HANDLERS = {
    "tg_send_message": tg_send_message,
    "tg_get_me": tg_get_me,
    "tg_get_updates": tg_get_updates,
    "tg_forward_message": tg_forward_message,
    "tg_answer_callback": tg_answer_callback,
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
