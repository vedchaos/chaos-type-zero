#!/usr/bin/env python3
"""CTZ MCP — Email (SMTP/IMAP via stdlib)"""
import imaplib
import json
import re
import smtplib
import sys
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

SERVER_INFO = {"name": "email-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "email_send", "description": "Send an email via SMTP (SSL on 465, STARTTLS otherwise). Multiple recipients separated by comma/semicolon.", "inputSchema": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "smtp_server": {"type": "string"}, "smtp_port": {"type": "integer"}, "username": {"type": "string"}, "password": {"type": "string"}}, "required": ["to", "subject", "body", "smtp_server", "smtp_port", "username", "password"]}},
    {"name": "email_read_imap", "description": "Read latest messages from an IMAP folder (IMAP4_SSL 993).", "inputSchema": {"type": "object", "properties": {"imap_server": {"type": "string"}, "username": {"type": "string"}, "password": {"type": "string"}, "folder": {"type": "string", "default": "INBOX"}, "limit": {"type": "integer", "default": 10}}, "required": ["imap_server", "username", "password"]}},
    {"name": "email_search", "description": "Search an IMAP folder with standard IMAP criteria (e.g. 'UNSEEN', 'FROM \"x\"', 'SUBJECT y').", "inputSchema": {"type": "object", "properties": {"imap_server": {"type": "string"}, "username": {"type": "string"}, "password": {"type": "string"}, "folder": {"type": "string", "default": "INBOX"}, "search_criteria": {"type": "string", "default": "ALL"}}, "required": ["imap_server", "username", "password"]}},
    {"name": "email_folders", "description": "List IMAP mailboxes/folders.", "inputSchema": {"type": "object", "properties": {"imap_server": {"type": "string"}, "username": {"type": "string"}, "password": {"type": "string"}}, "required": ["imap_server", "username", "password"]}},
]


def email_send(to, subject, body, smtp_server, smtp_port, username, password):
    try:
        recipients = [a.strip() for a in re.split(r"[;,]", to) if a.strip()]
        msg = EmailMessage()
        msg["From"] = username
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.set_content(body)
        port = int(smtp_port)
        if port == 465:
            server = smtplib.SMTP_SSL(smtp_server, port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_server, port, timeout=30)
        try:
            server.ehlo()
            if port != 465:
                try:
                    server.starttls()
                    server.ehlo()
                except smtplib.SMTPException:
                    pass
            server.login(username, password)
            refused = server.send_message(msg, from_addr=username, to_addrs=recipients)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return {"success": True, "to": recipients, "subject": subject, "refused": dict(refused or {})}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _connect(imap_server, username, password, folder):
    conn = imaplib.IMAP4_SSL(imap_server, 993)
    conn.login(username, password)
    conn.select(folder, readonly=True)
    return conn


def _body_text(msg):
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            return ""
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return str(payload or "")
    except Exception as exc:
        return f"<body error: {exc}>"


def email_read_imap(imap_server, username, password, folder="INBOX", limit=10):
    try:
        conn = _connect(imap_server, username, password, folder)
        try:
            _, data = conn.search(None, "ALL")
            ids = data[0].split() if data and data[0] else []
            picked = ids[-int(limit):][::-1]
            messages = []
            for mid in picked:
                _, msgdata = conn.fetch(mid, "(RFC822)")
                raw = None
                for item in msgdata:
                    if isinstance(item, tuple):
                        raw = item[1]
                        break
                if raw is None:
                    continue
                msg = BytesParser(policy=policy.default).parsebytes(raw)
                messages.append({
                    "id": mid.decode(errors="replace"),
                    "from": str(msg["From"]),
                    "subject": str(msg["Subject"]),
                    "date": str(msg["Date"]),
                    "body_preview": _body_text(msg)[:2000],
                })
            return {"folder": folder, "total_messages": len(ids), "returned": len(messages), "messages": messages}
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def email_search(imap_server, username, password, folder="INBOX", search_criteria="ALL"):
    try:
        conn = _connect(imap_server, username, password, folder)
        try:
            _, data = conn.search(None, search_criteria)
            ids = data[0].split() if data and data[0] else []
            results = []
            for mid in ids[-50:]:
                _, msgdata = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                header_raw = b""
                for item in msgdata:
                    if isinstance(item, tuple):
                        header_raw = item[1]
                        break
                msg = BytesParser(policy=policy.default).parsebytes(header_raw)
                results.append({"id": mid.decode(errors="replace"), "from": str(msg["From"]), "subject": str(msg["Subject"]), "date": str(msg["Date"])})
            return {"folder": folder, "criteria": search_criteria, "matches": len(ids), "results": results}
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def email_folders(imap_server, username, password):
    try:
        conn = imaplib.IMAP4_SSL(imap_server, 993)
        conn.login(username, password)
        try:
            status, boxes = conn.list()
            folders = []
            for entry in boxes or []:
                text = entry.decode(errors="replace")
                parts = text.rsplit('"/"', 1) if '"/"' in text else text.split(" ", 1)[-1:]
                name = parts[-1].strip().strip('"') if parts else text.strip()
                flags = text.split('"/"')[0].strip() if '"/"' in text else ""
                folders.append({"flags": flags, "name": name})
            return {"status": status.decode(), "folders": folders}
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


HANDLERS = {
    "email_send": email_send,
    "email_read_imap": email_read_imap,
    "email_search": email_search,
    "email_folders": email_folders,
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
