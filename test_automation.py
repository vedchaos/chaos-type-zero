#!/usr/bin/env python3
"""CHAOS TYPE ZERO Automation Engine — Full Test"""
import json
import time
import sys
from pathlib import Path

CTZ_ROOT = Path(__file__).parent
sys.path.insert(0, str(CTZ_ROOT))

print("=" * 60)
print("  CHAOS TYPE ZERO Automation Engine — Test")
print("=" * 60)

# 1. Import & init
print("\n[1/6] Import & Init...")
from bridge_core.automation import (
    get_engine, ACTION_TYPES, AutoScheduler,
    FileWatcher, URLWatcher, _parse_cron_next, _cron_matches,
)
engine = get_engine()
print(f"  Action types: {list(ACTION_TYPES.keys())}")
print(f"  DB path: {engine.db._path}")

# 2. CRUD
print("\n[2/6] CRUD Operations...")
auto1 = engine.create(
    name="Test Interval",
    trigger_type="interval",
    trigger_config={"seconds": 300},
    actions=[
        {"type": "shell", "params": {"command": "echo hello from CHAOS TYPE ZERO"}},
        {"type": "log", "params": {"message": "Test automation ran"}},
    ],
    description="Test interval automation",
)
print(f"  Created: {auto1['id']} — {auto1['name']}")
assert engine.get(auto1["id"]) is not None
print("  GET: OK")

auto2 = engine.create(
    name="Test Cron",
    trigger_type="cron",
    trigger_config={"expression": "0 22 * * *"},
    actions=[
        {"type": "notify", "params": {"title": "Test", "message": "Cron fired"}},
    ],
)
print(f"  Created: {auto2['id']} — {auto2['name']}")

all_autos = engine.list_all()
print(f"  List: {len(all_autos)} automations")
assert len(all_autos) >= 2

# 3. Enable / Disable
print("\n[3/6] Enable / Disable...")
engine.disable(auto1["id"])
d = engine.get(auto1["id"])
assert not d["enabled"], "Should be disabled"
print("  Disable: OK")

engine.enable(auto1["id"])
e = engine.get(auto1["id"])
assert e["enabled"], "Should be enabled"
print("  Enable: OK")

# 4. Run Now
print("\n[4/6] Run Now (manual trigger)...")
result = engine.run_now(auto1["id"])
print(f"  Status: {result['status']}")
print(f"  Actions run: {result['actions_run']}")
for r in result.get("results", []):
    print(f"    {r['action']}: {r['result'].get('status', r['result'].get('error', 'ok'))}")
assert result["status"] == "success"
print("  Run: OK")

# 5. Presets
print("\n[5/6] Presets...")
auto_backup = engine.preset_auto_backup(str(CTZ_ROOT), interval_hours=1)
print(f"  Auto Backup: {auto_backup['id']} — {auto_backup['name']}")

auto_cleanup = engine.preset_file_cleanup(str(CTZ_ROOT / "data"), max_age_days=7)
print(f"  File Cleanup: {auto_cleanup['id']} — {auto_cleanup['name']}")

auto_report = engine.preset_daily_report()
print(f"  Daily Report: {auto_report['id']} — {auto_report['name']}")

auto_health = engine.preset_health_check(interval_minutes=5)
print(f"  Health Check: {auto_health['id']} — {auto_health['name']}")

# 6. History & Stats
print("\n[6/6] History & Stats...")
history = engine.db.get_history(limit=10)
print(f"  History entries: {len(history)}")

stats = engine.db.stats()
print(f"  Stats: {json.dumps(stats, indent=2)}")

# 7. Advanced Agentic Actions & Variable Piping
print("\n[7/10] Advanced Agentic Actions & Variable Piping...")
piping_auto = engine.create(
    name="Piping Workflow",
    trigger_type="interval",
    trigger_config={"seconds": 3600},
    actions=[
        {"type": "shell", "params": {"command": "echo verified_agentic_pipeline"}},
        {"type": "log", "params": {"message": "Piped output: {{prev.output}}"}},
        {"type": "receipt", "params": {"action_name": "piped_workflow_execution"}},
        {"type": "context_save", "params": {"fact": "Automation piping test passed", "category": "automation"}},
    ],
    description="Test variable piping and provenance receipt signing",
)
pipe_res = engine.run_now(piping_auto["id"])
print(f"  Piping Workflow status: {pipe_res['status']}")
assert pipe_res["status"] == "success"
assert pipe_res["actions_run"] == 4
# Check receipt action produced receipt_id
receipt_step = pipe_res["results"][2]["result"]
assert "receipt_id" in receipt_step, "Receipt step should contain receipt_id"
assert receipt_step["status"] == "signed"
print(f"  Receipt ID generated: {receipt_step['receipt_id']}")
print("  Agentic Actions & Piping: OK")

# 8. MCP Tool Action Execution
print("\n[8/10] Direct MCP Tool Action...")
mcp_auto = engine.create(
    name="Direct MCP Action",
    trigger_type="interval",
    trigger_config={"seconds": 3600},
    actions=[
        {"type": "mcp_tool", "params": {
            "server": "git_mcp",
            "tool": "ctz_git_status",
            "arguments": {"path": "."}
        }},
    ],
    description="Invoke git_mcp directly from automation engine",
)
mcp_res = engine.run_now(mcp_auto["id"])
print(f"  MCP Tool Action status: {mcp_res['status']}")
assert mcp_res["status"] == "success"
print("  Direct MCP Tool Action: OK")

# 9. Natural Language Automation Creator
print("\n[9/10] Natural Language Automation Creator...")
nl_auto = engine.create_from_natural_language("har 2 ghante me data backup aur receipt sign karo")
print(f"  NL Auto created: {nl_auto['id']} — {nl_auto['name']} ({nl_auto['trigger_type']})")
assert nl_auto["trigger_type"] == "interval"
assert nl_auto["trigger_config"]["seconds"] == 7200
nl_res = engine.run_now(nl_auto["id"])
assert nl_res["status"] == "success"
print("  Natural Language Automation: OK")

# 10. Agentic Sentinel Presets
print("\n[10/10] Agentic Sentinel Presets...")
sentinel = engine.preset_autonomous_sentinel()
print(f"  Autonomous Sentinel: {sentinel['id']} — {sentinel['name']}")
assert sentinel["trigger_type"] == "interval"
git_sentinel = engine.preset_git_sentinel()
print(f"  Git Sentinel: {git_sentinel['id']} — {git_sentinel['name']}")
assert git_sentinel["trigger_type"] == "file_change"

# 11. Cron parser
print("\n  Cron parser test:")
assert _cron_matches(["0", "22", "*", "*", "*"],
                      __import__("datetime").datetime(2026, 1, 1, 22, 0))
print("    0 22 * * * at 22:00: MATCH")
assert not _cron_matches(["0", "22", "*", "*", "*"],
                          __import__("datetime").datetime(2026, 1, 1, 21, 0))
print("    0 22 * * * at 21:00: NO MATCH")
assert _cron_matches(["*/5", "*", "*", "*", "*"],
                      __import__("datetime").datetime(2026, 1, 1, 14, 15))
print("    */5 * * * * at :15: MATCH")
assert _cron_matches(["0", "9", "*", "*", "1-5"],
                      __import__("datetime").datetime(2026, 1, 5, 9, 0))  # Monday
print("    0 9 * * 1-5 on Monday 09:00: MATCH")

# 12. File watcher
print("\n  File watcher test:")
fw = FileWatcher()
r1 = fw.snapshot("test_watch", str(CTZ_ROOT), "*.py")
print(f"    Initial: {r1.get('status')} — {r1.get('files', 0)} files")
assert r1.get("status") == "initial_snapshot"
r2 = fw.snapshot("test_watch", str(CTZ_ROOT), "*.py")
print(f"    Second: changes={r2.get('has_changes', False)}")
assert not r2.get("has_changes", True), "Should be no changes"

# Cleanup
print("\n  Cleanup test automations...")
for a in [auto1, auto2, auto_backup, auto_cleanup, auto_report, auto_health, piping_auto, mcp_auto, nl_auto, sentinel, git_sentinel]:
    engine.delete(a["id"])
final = engine.list_all()
print(f"  Remaining: {len(final)} automations")

print("\n" + "=" * 60)
print("  ALL TESTS PASSED! 100% OPERATIONAL")
print("=" * 60)
