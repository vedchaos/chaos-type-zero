#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Automation MCP Server — 10 tools for full automation control.
Triggers, actions, chains, presets, history, stats.
"""
import json
import sys
from pathlib import Path

CTZ_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CTZ_ROOT))

from bridge_core.automation import get_engine, ACTION_TYPES


def handle_request(req: dict) -> dict:
    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "ctz-automation", "version": "1.0.0"},
        }}

    if method == "notifications/initialized":
        return None

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [
            {
                "name": "ctz_auto_create",
                "description": "Create a new automation with trigger + actions",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Automation name"},
                        "trigger_type": {"type": "string", "enum": ["interval", "cron", "file_change", "url_change"], "description": "Trigger type"},
                        "trigger_config": {"type": "object", "description": "Trigger config: {seconds} for interval, {expression} for cron (5-field), {directory,pattern,check_interval} for file_change, {url,check_interval} for url_change"},
                        "actions": {"type": "array", "description": "List of actions to execute. Each: {type, params}", "items": {"type": "object"}},
                        "description": {"type": "string", "description": "What this automation does"},
                    },
                    "required": ["name", "trigger_type", "trigger_config", "actions"],
                },
            },
            {
                "name": "ctz_auto_list",
                "description": "List all automations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "enabled_only": {"type": "boolean", "description": "Only show enabled automations"},
                    },
                },
            },
            {
                "name": "ctz_auto_get",
                "description": "Get details of an automation by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "auto_id": {"type": "string", "description": "Automation ID"},
                    },
                    "required": ["auto_id"],
                },
            },
            {
                "name": "ctz_auto_delete",
                "description": "Delete an automation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "auto_id": {"type": "string", "description": "Automation ID"},
                    },
                    "required": ["auto_id"],
                },
            },
            {
                "name": "ctz_auto_enable",
                "description": "Enable a disabled automation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "auto_id": {"type": "string", "description": "Automation ID"},
                    },
                    "required": ["auto_id"],
                },
            },
            {
                "name": "ctz_auto_disable",
                "description": "Disable an automation (stops trigger)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "auto_id": {"type": "string", "description": "Automation ID"},
                    },
                    "required": ["auto_id"],
                },
            },
            {
                "name": "ctz_auto_run",
                "description": "Manually trigger an automation right now",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "auto_id": {"type": "string", "description": "Automation ID"},
                    },
                    "required": ["auto_id"],
                },
            },
            {
                "name": "ctz_auto_preset",
                "description": "Create a pre-built automation (auto_backup, file_cleanup, url_monitor, daily_report, health_check)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "preset": {"type": "string", "enum": ["auto_backup", "file_cleanup", "url_monitor", "daily_report", "health_check"], "description": "Preset type"},
                        "params": {"type": "object", "description": "Preset params: {src_path,interval_hours} for backup; {directory,max_age_days,pattern} for cleanup; {url} for monitor; {} for report; {interval_minutes} for health"},
                    },
                    "required": ["preset"],
                },
            },
            {
                "name": "ctz_auto_history",
                "description": "Get run history for automations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "auto_id": {"type": "string", "description": "Filter by automation ID (optional)"},
                        "limit": {"type": "integer", "description": "Max results (default 50)"},
                    },
                },
            },
            {
                "name": "ctz_auto_stats",
                "description": "Get automation engine statistics",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]}}

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        engine = get_engine()

        if tool_name == "ctz_auto_create":
            result = engine.create(
                name=args.get("name", "Unnamed"),
                trigger_type=args.get("trigger_type", "interval"),
                trigger_config=args.get("trigger_config", {}),
                actions=args.get("actions", []),
                description=args.get("description", ""),
            )
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            }}

        elif tool_name == "ctz_auto_list":
            result = engine.list_all(args.get("enabled_only", False))
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            }}

        elif tool_name == "ctz_auto_get":
            result = engine.get(args.get("auto_id", ""))
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str) if result else "Not found"}],
            }}

        elif tool_name == "ctz_auto_delete":
            result = engine.delete(args.get("auto_id", ""))
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": f"Deleted: {result}"}],
            }}

        elif tool_name == "ctz_auto_enable":
            result = engine.enable(args.get("auto_id", ""))
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result)}],
            }}

        elif tool_name == "ctz_auto_disable":
            result = engine.disable(args.get("auto_id", ""))
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result)}],
            }}

        elif tool_name == "ctz_auto_run":
            result = engine.run_now(args.get("auto_id", ""))
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            }}

        elif tool_name == "ctz_auto_preset":
            preset = args.get("preset", "")
            p = args.get("params", {})
            if preset == "auto_backup":
                result = engine.preset_auto_backup(
                    p.get("src_path", str(CTZ_ROOT)),
                    p.get("interval_hours", 24),
                )
            elif preset == "file_cleanup":
                result = engine.preset_file_cleanup(
                    p.get("directory", str(CTZ_ROOT / "data")),
                    p.get("max_age_days", 7),
                    p.get("pattern", "*"),
                )
            elif preset == "url_monitor":
                result = engine.preset_url_monitor(p.get("url", "https://example.com"))
            elif preset == "daily_report":
                result = engine.preset_daily_report()
            elif preset == "health_check":
                result = engine.preset_health_check(p.get("interval_minutes", 5))
            elif preset == "autonomous_sentinel":
                result = engine.preset_autonomous_sentinel()
            elif preset == "git_sentinel":
                result = engine.preset_git_sentinel()
            else:
                result = {"error": f"Unknown preset: {preset}"}
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            }}

        elif tool_name == "ctz_auto_nl_create":
            prompt = args.get("prompt", "")
            result = engine.create_from_natural_language(prompt)
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            }}

        elif tool_name == "ctz_auto_history":
            result = engine.db.get_history(args.get("auto_id"), args.get("limit", 50))
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            }}

        elif tool_name == "ctz_auto_stats":
            result = engine.db.stats()
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            }}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
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
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
