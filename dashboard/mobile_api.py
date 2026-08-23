#!/usr/bin/env python3
"""CHAOS TYPE ZERO -- Mobile API Backend (REST HTTP server for React Native app)"""

import json
import sys
import os
import secrets
import time
import hashlib
import hmac
import sqlite3
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime

# SECURITY: this used to default to the publicly documented string
# "ctz-default-token-change-me" while binding to 0.0.0.0 -- meaning
# anyone on the same network (or anyone who read this file on GitHub)
# already knew the auth token for a server exposed on every interface.
# We now refuse to start with a weak/default token; a random one is
# generated on first run if CTZ_API_TOKEN isn't set, and it's printed
# once (and saved locally) so you can put it in the mobile app.
HOST = os.environ.get("CTZ_API_HOST", "127.0.0.1")  # bind to localhost by default
PORT = 8081
DATA_DIR = Path(__file__).parent.parent / "data"
LOG_DB = DATA_DIR / "mobile_api.db"
TOKEN_FILE = DATA_DIR / "mobile_api_token.txt"

_INSECURE_DEFAULTS = {"", "ctz-default-token-change-me", "changeme", "default", "password", "token"}


def _resolve_auth_token() -> str:
    env_token = os.environ.get("CTZ_API_TOKEN", "").strip()
    if env_token:
        if env_token.lower() in _INSECURE_DEFAULTS:
            raise SystemExit(
                "[CTZ Mobile API] CTZ_API_TOKEN is set to a weak/default value. "
                "Choose a real secret (e.g. `python -c \"import secrets; print(secrets.token_urlsafe(32))\"`)."
            )
        return env_token
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(token)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return token


AUTH_TOKEN = _resolve_auth_token()


def get_log_db():
    LOG_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LOG_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT DEFAULT 'info',
        source TEXT DEFAULT 'api',
        message TEXT NOT NULL,
        metadata TEXT DEFAULT '{}',
        created_at REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        read INTEGER DEFAULT 0,
        created_at REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS voice_commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        command TEXT NOT NULL,
        response TEXT DEFAULT '',
        latency_ms REAL DEFAULT 0,
        created_at REAL NOT NULL
    )""")
    conn.commit()
    return conn


def log_event(level, source, message, metadata=None):
    try:
        conn = get_log_db()
        conn.execute(
            "INSERT INTO logs (level, source, message, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (level, source, message, json.dumps(metadata or {}), time.time())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def parse_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    body = handler.rfile.read(length)
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {}


def make_mcp_servers():
    mcps = {}
    oc = Path(__file__).parent.parent / "opencode.json"
    if oc.exists():
        try:
            cfg = json.loads(oc.read_text())
            mcps = cfg.get("mcp", {})
        except Exception:
            pass
    return mcps


def _execute_ctz_command(cmd, args):
    valid_commands = [
        "status", "scan", "recon", "exploit", "deploy",
        "analyze", "monitor", "backup", "report"
    ]
    if cmd not in valid_commands:
        return {"status": "error", "message": f"Unknown command: {cmd}. Valid: {valid_commands}"}
    log_event("info", "command_exec", f"Executing CTZ command: {cmd}", {"args": args})
    return {
        "status": "executed",
        "command": cmd,
        "args": args,
        "message": f"Command '{cmd}' dispatched to CTZ engine",
        "timestamp": time.time()
    }


def _process_voice_command(transcript):
    transcript_lower = transcript.lower()
    if "status" in transcript_lower:
        return "System status: all CTZ subsystems operational."
    elif "scan" in transcript_lower:
        return "Initiating network scan. Results will appear in the scan panel."
    elif "deploy" in transcript_lower:
        return "Deployment initiated. Monitor progress in the deploy panel."
    elif "help" in transcript_lower:
        return "Available voice commands: status, scan, deploy, analyze, monitor, help"
    else:
        return f"Received: '{transcript}'. Processing as general query."


class MobileAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    def check_auth(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else auth
        # constant-time comparison to avoid leaking the token via timing
        return hmac.compare_digest(token, AUTH_TOKEN)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/health":
            return self.send_json({
                "status": "healthy",
                "service": "ctz-mobile-api",
                "version": "1.0.0",
                "uptime": time.time()
            })

        if not self.check_auth():
            return self.send_json({"error": "unauthorized", "message": "Valid Bearer token required"}, 401)

        if path == "/api/status":
            return self.send_json({
                "status": "online",
                "system": "CHAOS TYPE ZERO",
                "version": "1.0.0",
                "api_port": PORT,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "components": {
                    "api": "operational",
                    "mcp_bridge": "operational",
                    "mobile_api": "operational"
                }
            })

        elif path == "/api/servers":
            mcps = make_mcp_servers()
            servers = []
            for name, cfg in mcps.items():
                servers.append({
                    "name": name,
                    "type": cfg.get("type", "unknown"),
                    "enabled": cfg.get("enabled", False),
                    "command": " ".join(cfg.get("command", []))
                })
            return self.send_json({"count": len(servers), "servers": servers})

        elif path == "/api/memory":
            mem_info = {"status": "no_data"}
            try:
                conn = get_log_db()
                total_logs = conn.execute("SELECT COUNT(*) as c FROM logs").fetchone()["c"]
                total_notifs = conn.execute("SELECT COUNT(*) as c FROM notifications").fetchone()["c"]
                total_voice = conn.execute("SELECT COUNT(*) as c FROM voice_commands").fetchone()["c"]
                conn.close()
                mem_info = {
                    "total_logs": total_logs,
                    "total_notifications": total_notifs,
                    "total_voice_commands": total_voice,
                    "status": "active"
                }
            except Exception:
                pass
            return self.send_json({"memory": mem_info})

        elif path == "/api/logs":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["50"])[0])
            conn = get_log_db()
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?",
                (min(limit, 200),)
            ).fetchall()
            conn.close()
            logs = [
                {"id": r["id"], "level": r["level"], "source": r["source"],
                 "message": r["message"], "timestamp": r["created_at"]}
                for r in rows
            ]
            return self.send_json({"count": len(logs), "logs": logs})

        return self.send_json({"error": "not_found", "path": path}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if not self.check_auth():
            return self.send_json({"error": "unauthorized", "message": "Valid Bearer token required"}, 401)

        body = parse_body(self)

        if path == "/api/command":
            cmd = body.get("command", "")
            args = body.get("args", {})
            log_event("info", "command", f"Received command: {cmd}", {"args": args})
            result = _execute_ctz_command(cmd, args)
            return self.send_json({"command": cmd, "result": result, "timestamp": time.time()})

        elif path == "/api/voice":
            transcript = body.get("transcript", "")
            language = body.get("language", "en")
            log_event("info", "voice", f"Voice command: {transcript}", {"lang": language})
            conn = get_log_db()
            start = time.time()
            response = _process_voice_command(transcript)
            latency = (time.time() - start) * 1000
            conn.execute(
                "INSERT INTO voice_commands (command, response, latency_ms, created_at) VALUES (?, ?, ?, ?)",
                (transcript, response, latency, time.time())
            )
            conn.commit()
            conn.close()
            return self.send_json({
                "transcript": transcript,
                "response": response,
                "latency_ms": round(latency, 1)
            })

        elif path == "/api/notify":
            title = body.get("title", "CTZ Notification")
            nbody = body.get("body", "")
            level = body.get("level", "info")
            log_event("info", "notification", f"Notification: {title}", {"level": level})
            conn = get_log_db()
            conn.execute(
                "INSERT INTO notifications (title, body, level, created_at) VALUES (?, ?, ?, ?)",
                (title, nbody, level, time.time())
            )
            conn.commit()
            conn.close()
            return self.send_json({
                "status": "sent",
                "notification": {"title": title, "body": nbody, "level": level}
            })

        return self.send_json({"error": "not_found", "path": path}, 404)


def main():
    server = HTTPServer((HOST, PORT), MobileAPIHandler)
    log_event("info", "server", f"CTZ Mobile API started on {HOST}:{PORT}")
    print(f"[CTZ Mobile API] Serving on http://{HOST}:{PORT}")
    print(f"[CTZ Mobile API] Health: http://{HOST}:{PORT}/api/health")
    if not os.environ.get("CTZ_API_TOKEN"):
        print(f"[CTZ Mobile API] No CTZ_API_TOKEN set -- generated one and saved to {TOKEN_FILE}")
        print(f"[CTZ Mobile API] Auth token: {AUTH_TOKEN}")
    else:
        print("[CTZ Mobile API] Auth token: loaded from CTZ_API_TOKEN env var")
    if HOST == "0.0.0.0":
        print("[CTZ Mobile API] WARNING: bound to 0.0.0.0 -- reachable from your whole network.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[CTZ Mobile API] Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
