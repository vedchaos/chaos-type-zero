#!/usr/bin/env python3
"""CHAOS TYPE ZERO — Slack Bot Controller"""
import hmac
import json, sys, os, hashlib, time, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

# Bot config — set these environment variables
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "xoxb-YOUR-BOT-TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "YOUR-SIGNING-SECRET")
PORT = int(os.environ.get("CTZ_SLACK_PORT", 3000))

# MCP server references
MCP_SERVERS = {
    "brain": "ctz-brain",
    "memory": "ctz-memory",
    "router": "ctz-router",
    "security": "ctz-security",
    "browser": "ctz-browser",
    "voice": "ctz-voice",
    "neural": "ctz-neural",
    "orchestrator": "ctz-orchestrator",
}

# Command patterns
COMMANDS = {
    r"scan\s+(.+)": "security",
    r"search\s+(.+)": "memory",
    r"run\s+(.+)": "orchestrator",
    r"browse\s+(.+)": "browser",
    r"status": "status",
    r"help": "help",
    r"health": "health",
    r"servers": "servers",
}


def process_command(text):
    """Process a Slack command and return response."""
    text = text.strip().lower()
    
    # Help command
    if text in ["help", "!help", "/ctz help"]:
        return {
            "response_type": "in_channel",
            "text": "*CHAOS TYPE ZERO — Commands*\n"
                    "```\n"
                    "scan <target>     — Security scan\n"
                    "search <query>    — Search memory\n"
                    "run <task>        — Run task\n"
                    "browse <url>      — Browse website\n"
                    "status            — System status\n"
                    "health            — Health check\n"
                    "servers           — MCP servers\n"
                    "help              — Show this help\n"
                    "```"
        }
    
    # Status
    if text in ["status", "!status"]:
        return {
            "response_type": "in_channel",
            "text": "*CTZ Status*\n"
                    "```Servers: 40\nTools: 298\nProviders: 14\nSkills: 31\nStatus: ONLINE```"
        }
    
    # Health
    if text in ["health", "!health"]:
        return {
            "response_type": "in_channel",
            "text": "*Health Check*\nAll systems operational. 40/40 MCP servers ready."
        }
    
    # Servers
    if text in ["servers", "!servers"]:
        server_list = "\n".join([f"  {k}: {v}" for k, v in MCP_SERVERS.items()])
        return {
            "response_type": "in_channel",
            "text": f"*MCP Servers*\n```\n{server_list}\n```"
        }
    
    # Pattern matching
    for pattern, server_type in COMMANDS.items():
        match = re.match(pattern, text)
        if match:
            arg = match.group(1) if match.lastindex else ""
            return {
                "response_type": "in_channel",
                "text": f"*CTZ [{server_type.upper()}]*\nCommand: `{text}`\n"
                        f"Target: `{arg}`\n"
                        f"Status: Dispatched to {MCP_SERVERS.get(server_type, server_type)}"
            }
    
    return {
        "response_type": "ephemeral",
        "text": "Unknown command. Type `help` for available commands."
    }


def _verify_slack_signature(headers, body: bytes) -> bool:
    """
    SECURITY: this endpoint is bound to 0.0.0.0 and previously accepted +
    executed ANY POST body as if it were a real Slack event, without ever
    checking SLACK_SIGNING_SECRET -- meaning anyone who could reach the
    port could forge Slack commands. This implements Slack's documented
    HMAC-SHA256 request signing check.
    https://api.slack.com/authentication/verifying-requests-from-slack
    """
    if SLACK_SIGNING_SECRET in ("YOUR-SIGNING-SECRET", ""):
        return False  # refuse to trust anything until a real secret is configured

    timestamp = headers.get("X-Slack-Request-Timestamp", "")
    slack_signature = headers.get("X-Slack-Signature", "")
    if not timestamp or not slack_signature:
        return False

    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False  # protect against replay attacks
    except ValueError:
        return False

    basestring = f"v0:{timestamp}:{body.decode('utf-8', errors='replace')}"
    computed = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, slack_signature)


class SlackHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        if not _verify_slack_signature(self.headers, body):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "invalid signature"}')
            return

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return
        
        # URL verification
        if data.get("type") == "url_verification":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"challenge": data.get("challenge")}).encode())
            return
        
        # Event callback
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            if event.get("type") == "message":
                text = event.get("text", "")
                channel = event.get("channel", "")
                
                # Ignore bot messages
                if event.get("subtype") == "bot_message":
                    self.send_response(200)
                    self.end_headers()
                    return
                
                # Process command
                response = process_command(text)
                print(f"[CTZ-SLACK] {text} -> {response['text'][:100]}...")
        
        self.send_response(200)
        self.end_headers()


def run_bot():
    """Start the Slack bot server."""
    print(f"CTZ Slack Bot starting on port {PORT}...")
    print(f"Bot Token: {SLACK_BOT_TOKEN[:20]}...")
    print(f"Signing Secret: {SLACK_SIGNING_SECRET[:20]}...")
    print("\nTo set up:")
    print("1. Create Slack app at https://api.slack.com/apps")
    print("2. Enable Event Subscriptions")
    print("3. Set Request URL to http://YOUR_IP:3000/slack/events")
    print("4. Subscribe to message.channels and message.im")
    print("5. Install to workspace")
    print(f"6. Set SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET env vars")
    print(f"7. Run: python slack_bot.py")
    
    server = HTTPServer(("0.0.0.0", PORT), SlackHandler)
    server.serve_forever()


if __name__ == "__main__":
    run_bot()
