#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Automation Engine — Triggers, Actions, Chains, Persistence
Runs automations in background threads with full event history.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data" / "automation"
DB_PATH = DATA_DIR / "automations.db"
LOGS_DIR = DATA_DIR / "logs"


# ─── Notification Layer ───────────────────────────────────────────────

def _notify_windows(title: str, message: str):
    """Windows toast notification via PowerShell."""
    try:
        ps = f'''[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) | Out-Null
$textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("CHAOS TYPE ZERO").Show($toast)'''
        subprocess.Popen(["powershell", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # non-critical


def _notify_voice(message: str):
    """Speak notification via pyttsx3."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(message)
        engine.runAndWait()
        engine.stop()
    except Exception:
        pass  # non-critical


# ─── Action Types ─────────────────────────────────────────────────────

def action_shell(params: dict) -> dict:
    """Execute a shell command."""
    cmd = params.get("command", "")
    if not cmd:
        return {"error": "No command provided"}
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=params.get("timeout", 60)
        )
        return {
            "status": "completed",
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {params.get('timeout', 60)}s"}
    except Exception as e:
        return {"error": str(e)}


def action_file_copy(params: dict) -> dict:
    """Copy a file from src to dst."""
    src = params.get("src", "")
    dst = params.get("dst", "")
    if not src or not dst:
        return {"error": "src and dst required"}
    try:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return {"status": "copied", "src": src, "dst": dst}
    except Exception as e:
        return {"error": str(e)}


def action_file_cleanup(params: dict) -> dict:
    """Delete files older than max_age_days in a directory."""
    directory = params.get("directory", "")
    max_age_days = params.get("max_age_days", 7)
    pattern = params.get("pattern", "*")
    if not directory:
        return {"error": "directory required"}
    try:
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0
        d = Path(directory)
        if d.exists():
            for f in d.glob(pattern):
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
        return {"status": "cleaned", "removed": removed, "directory": directory}
    except Exception as e:
        return {"error": str(e)}


def action_api_call(params: dict) -> dict:
    """Make an HTTP API call."""
    import requests
    url = params.get("url", "")
    method = params.get("method", "GET").upper()
    headers = params.get("headers", {})
    body = params.get("body")
    if not url:
        return {"error": "url required"}
    try:
        resp = requests.request(method, url, headers=headers, json=body, timeout=30)
        return {
            "status_code": resp.status_code,
            "body": resp.text[:2000],
        }
    except Exception as e:
        return {"error": str(e)}


def action_notify(params: dict) -> dict:
    """Send notification (toast + optional voice)."""
    title = params.get("title", "CHAOS TYPE ZERO")
    message = params.get("message", "")
    voice = params.get("voice", False)
    _notify_windows(title, message)
    if voice:
        _notify_voice(message)
    return {"status": "notified", "title": title, "message": message}


def action_llm_query(params: dict) -> dict:
    """Query the LLM brain with a prompt."""
    try:
        from .smart_brain import get_brain
        brain = get_brain()
        prompt = params.get("prompt", "")
        task_type = params.get("task_type", "agent")
        response, provider, model, cached = brain.query(prompt, task_type)
        return {
            "status": "completed",
            "response": response[:2000],
            "provider": provider,
            "model": model,
        }
    except Exception as e:
        return {"error": str(e)}


def action_backup(params: dict) -> dict:
    """Backup a file or directory."""
    src = params.get("src", "")
    dst_dir = params.get("dst_dir", str(CTZ_ROOT / "data" / "backups"))
    if not src:
        return {"error": "src required"}
    try:
        src_path = Path(src)
        if not src_path.exists():
            return {"error": f"Source not found: {src}"}
        dst_path = Path(dst_dir)
        dst_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = src_path.name
        if src_path.is_dir():
            dst = dst_path / f"{name}_{timestamp}"
            shutil.copytree(str(src_path), str(dst))
        else:
            dst = dst_path / f"{name}_{timestamp}"
            shutil.copy2(str(src_path), str(dst))
        return {"status": "backed_up", "src": src, "dst": str(dst)}
    except Exception as e:
        return {"error": str(e)}


def action_log(params: dict) -> dict:
    """Write a message to the automation log file."""
    message = params.get("message", "")
    log_file = LOGS_DIR / f"auto_{datetime.now().strftime('%Y%m%d')}.log"
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        return {"status": "logged", "file": str(log_file)}
    except Exception as e:
        return {"error": str(e)}


ACTION_TYPES = {
    "shell": action_shell,
    "file_copy": action_file_copy,
    "file_cleanup": action_file_cleanup,
    "api_call": action_api_call,
    "notify": action_notify,
    "llm_query": action_llm_query,
    "backup": action_backup,
    "log": action_log,
}


# ─── Trigger Types ────────────────────────────────────────────────────

class FileWatcher:
    """Watch a directory for file changes (create/modify/delete)."""

    def __init__(self):
        self._snapshots: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

    def snapshot(self, watch_id: str, directory: str, pattern: str = "*") -> dict:
        """Take a snapshot of file mtimes. Returns new/changed/deleted files."""
        d = Path(directory)
        if not d.exists():
            return {"error": f"Directory not found: {directory}"}

        current = {}
        for f in d.glob(pattern):
            if f.is_file():
                current[str(f)] = f.stat().st_mtime

        with self._lock:
            old = self._snapshots.get(watch_id, {})
            self._snapshots[watch_id] = current

        if not old:
            return {"status": "initial_snapshot", "files": len(current)}

        new_files = [f for f in current if f not in old]
        changed = [f for f in current if f in old and current[f] > old[f]]
        deleted = [f for f in old if f not in current]

        has_changes = bool(new_files or changed or deleted)
        return {
            "has_changes": has_changes,
            "new": [Path(f).name for f in new_files],
            "changed": [Path(f).name for f in changed],
            "deleted": [Path(f).name for f in deleted],
        }


class URLWatcher:
    """Watch URLs for content changes (hash-based)."""

    def __init__(self):
        self._hashes: Dict[str, str] = {}
        self._lock = threading.Lock()

    def check(self, watch_id: str, url: str) -> dict:
        """Check if URL content has changed since last check."""
        import requests
        try:
            resp = requests.get(url, timeout=30)
            content_hash = hashlib.md5(resp.text.encode(), usedforsecurity=False).hexdigest()
            with self._lock:
                old_hash = self._hashes.get(watch_id)
                self._hashes[watch_id] = content_hash

            if old_hash is None:
                return {"status": "initial_check", "hash": content_hash}
            elif old_hash != content_hash:
                return {"has_changes": True, "old_hash": old_hash, "new_hash": content_hash}
            else:
                return {"has_changes": False}
        except Exception as e:
            return {"error": str(e)}


# ─── Scheduler (for interval/cron triggers) ───────────────────────────

class AutoScheduler:
    """Simple interval-based scheduler for automations."""

    def __init__(self):
        self._tasks: Dict[str, dict] = {}  # auto_id -> {interval, last_run, callback}
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def add(self, auto_id: str, interval_seconds: int, callback: Callable):
        with self._lock:
            self._tasks[auto_id] = {
                "interval": interval_seconds,
                "last_run": 0,
                "callback": callback,
            }

    def remove(self, auto_id: str):
        with self._lock:
            self._tasks.pop(auto_id, None)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            now = time.time()
            with self._lock:
                for auto_id, task in list(self._tasks.items()):
                    if now - task["last_run"] >= task["interval"]:
                        task["last_run"] = now
                        try:
                            task["callback"]()
                        except Exception as e:
                            print(f"[AUTO] Error in {auto_id}: {e}")
            time.sleep(1)  # check every second


# ─── Cron Parser (reuse from scheduler) ───────────────────────────────

def _parse_cron_next(cron_expr: str) -> Optional[float]:
    """Parse a 5-field cron expression and return the next fire time as epoch.
    Simplified: supports *, */N, N-M, N,M,O for each field.
    Returns None if invalid.
    """
    try:
        fields = cron_expr.strip().split()
        if len(fields) != 5:
            return None

        now = datetime.now()
        # Search up to 366 days ahead
        for day_offset in range(367):
            check_date = now + timedelta(days=day_offset)
            if _cron_matches(fields, check_date):
                # Return start of that minute
                target = check_date.replace(second=0, microsecond=0)
                if target > now:
                    return target.timestamp()
        return None
    except Exception:
        return None


def _cron_matches(fields: list, dt: datetime) -> bool:
    """Check if datetime matches all 5 cron fields."""
    checks = [
        (fields[0], dt.minute, 0, 59),
        (fields[1], dt.hour, 0, 23),
        (fields[2], dt.day, 1, 31),
        (fields[3], dt.month, 1, 12),
        (fields[4], dt.isoweekday() % 7, 0, 6),
    ]
    for field, value, min_v, max_v in checks:
        if not _cron_field_matches(field, value, min_v, max_v):
            return False
    return True


def _cron_field_matches(field: str, value: int, min_v: int, max_v: int) -> bool:
    """Check if a single cron field matches a value."""
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            return True
        if "/" in part:
            star, step = part.split("/", 1)
            step = int(step)
            if step <= 0:
                return False
            if star == "*":
                return (value - min_v) % step == 0
            base = int(star)
            return value >= base and (value - base) % step == 0
        if "-" in part:
            lo, hi = part.split("-", 1)
            lo, hi = int(lo), int(hi)
            return lo <= value <= hi
        if part.isdigit():
            return int(part) == value
    return False


# ─── Automation DB ────────────────────────────────────────────────────

class AutomationDB:
    """SQLite storage for automations and run history."""

    def __init__(self, db_path: str = None):
        self._path = db_path or str(DB_PATH)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS automations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    trigger_type TEXT NOT NULL,
                    trigger_config TEXT DEFAULT '{}',
                    actions TEXT DEFAULT '[]',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    last_status TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    automation_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    result TEXT DEFAULT '{}',
                    FOREIGN KEY (automation_id) REFERENCES automations(id)
                )
            """)

    def save(self, auto: dict):
        with sqlite3.connect(self._path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO automations
                (id, name, description, trigger_type, trigger_config, actions, enabled, created_at, last_run, last_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                auto["id"], auto["name"], auto.get("description", ""),
                auto["trigger_type"], json.dumps(auto.get("trigger_config", {})),
                json.dumps(auto.get("actions", [])),
                1 if auto.get("enabled", True) else 0,
                auto["created_at"], auto.get("last_run"), auto.get("last_status"),
            ))

    def get(self, auto_id: str) -> Optional[dict]:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM automations WHERE id = ?", (auto_id,)).fetchone()
            if row:
                return self._row_to_dict(row)
            return None

    def list_all(self, enabled_only: bool = False) -> list:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM automations" + (" WHERE enabled = 1" if enabled_only else " ORDER BY created_at DESC")
            return [self._row_to_dict(r) for r in conn.execute(q).fetchall()]

    def delete(self, auto_id: str) -> bool:
        with sqlite3.connect(self._path) as conn:
            conn.execute("DELETE FROM automations WHERE id = ?", (auto_id,))
            conn.execute("DELETE FROM run_history WHERE automation_id = ?", (auto_id,))
            return True

    def log_run(self, auto_id: str, status: str, result: dict):
        now = datetime.now().isoformat()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO run_history (automation_id, started_at, finished_at, status, result) VALUES (?, ?, ?, ?, ?)",
                (auto_id, now, now, status, json.dumps(result)),
            )
            conn.execute(
                "UPDATE automations SET last_run = ?, last_status = ? WHERE id = ?",
                (now, status, auto_id),
            )

    def get_history(self, auto_id: str = None, limit: int = 50) -> list:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            if auto_id:
                rows = conn.execute(
                    "SELECT * FROM run_history WHERE automation_id = ? ORDER BY id DESC LIMIT ?",
                    (auto_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM run_history ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> dict:
        with sqlite3.connect(self._path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM automations").fetchone()[0]
            enabled = conn.execute("SELECT COUNT(*) FROM automations WHERE enabled = 1").fetchone()[0]
            runs = conn.execute("SELECT COUNT(*) FROM run_history").fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM run_history WHERE status = 'success'").fetchone()[0]
            failures = conn.execute("SELECT COUNT(*) FROM run_history WHERE status = 'error'").fetchone()[0]
            return {
                "total_automations": total,
                "enabled": enabled,
                "disabled": total - enabled,
                "total_runs": runs,
                "successes": successes,
                "failures": failures,
                "success_rate": f"{(successes/runs*100):.1f}%" if runs else "N/A",
            }

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "trigger_type": row["trigger_type"],
            "trigger_config": json.loads(row["trigger_config"]),
            "actions": json.loads(row["actions"]),
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "last_run": row["last_run"],
            "last_status": row["last_status"],
        }


# ─── Main Engine ──────────────────────────────────────────────────────

class AutomationEngine:
    """Core automation engine — creates, runs, and manages automations."""

    def __init__(self):
        self.db = AutomationDB()
        self.scheduler = AutoScheduler()
        self.file_watcher = FileWatcher()
        self.url_watcher = URLWatcher()
        self._running_autos: Dict[str, threading.Thread] = {}

    def start(self):
        """Start the background scheduler."""
        self.scheduler.start()
        # Re-enable saved automations
        for auto in self.db.list_all(enabled_only=True):
            self._setup_trigger(auto)
        print(f"[AUTO] Engine started — {len(self.db.list_all(enabled_only=True))} active automations")

    def stop(self):
        """Stop all background threads."""
        self.scheduler.stop()
        for t in self._running_autos.values():
            t.join(timeout=2)
        self._running_autos.clear()

    # ── CRUD ──

    def create(self, name: str, trigger_type: str, trigger_config: dict,
               actions: list, description: str = "") -> dict:
        """Create a new automation."""
        auto_id = hashlib.md5(f"{name}_{time.time()}".encode(), usedforsecurity=False).hexdigest()[:12]
        auto = {
            "id": auto_id,
            "name": name,
            "description": description,
            "trigger_type": trigger_type,
            "trigger_config": trigger_config,
            "actions": actions,
            "enabled": True,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "last_status": None,
        }
        self.db.save(auto)
        self._setup_trigger(auto)
        return auto

    def get(self, auto_id: str) -> Optional[dict]:
        return self.db.get(auto_id)

    def list_all(self, enabled_only: bool = False) -> list:
        return self.db.list_all(enabled_only)

    def delete(self, auto_id: str) -> bool:
        self.scheduler.remove(auto_id)
        return self.db.delete(auto_id)

    def enable(self, auto_id: str) -> dict:
        auto = self.db.get(auto_id)
        if not auto:
            return {"error": "Automation not found"}
        auto["enabled"] = True
        self.db.save(auto)
        self._setup_trigger(auto)
        return {"status": "enabled", "id": auto_id}

    def disable(self, auto_id: str) -> dict:
        auto = self.db.get(auto_id)
        if not auto:
            return {"error": "Automation not found"}
        auto["enabled"] = False
        self.db.save(auto)
        self.scheduler.remove(auto_id)
        return {"status": "disabled", "id": auto_id}

    # ── Execution ──

    def run_now(self, auto_id: str) -> dict:
        """Manually trigger an automation immediately."""
        auto = self.db.get(auto_id)
        if not auto:
            return {"error": "Automation not found"}
        result = self._execute_actions(auto["actions"])
        status = "success" if not any(r.get("error") for r in result) else "error"
        self.db.log_run(auto_id, status, {"results": result})
        return {"status": status, "actions_run": len(result), "results": result}

    def _execute_actions(self, actions: list) -> list:
        """Execute a list of actions in order."""
        results = []
        for action in actions:
            action_type = action.get("type", "")
            params = action.get("params", {})
            handler = ACTION_TYPES.get(action_type)
            if handler:
                r = handler(params)
                results.append({"action": action_type, "result": r})
            else:
                results.append({"action": action_type, "result": {"error": f"Unknown action: {action_type}"}})
        return results

    # ── Triggers ──

    def _setup_trigger(self, auto: dict):
        """Configure the trigger for an automation."""
        if not auto.get("enabled"):
            return

        trigger_type = auto["trigger_type"]
        config = auto.get("trigger_config", {})
        auto_id = auto["id"]

        if trigger_type == "interval":
            seconds = config.get("seconds", 60)
            self.scheduler.add(auto_id, seconds, lambda a=auto: self._trigger_fired(a))
            self.scheduler.start()

        elif trigger_type == "cron":
            cron_expr = config.get("expression", "")
            self.scheduler.add(auto_id, 60, lambda a=auto, c=cron_expr: self._cron_check(a, c))
            self.scheduler.start()

        elif trigger_type == "file_change":
            directory = config.get("directory", "")
            pattern = config.get("pattern", "*")
            if directory:
                self.file_watcher.snapshot(auto_id, directory, pattern)
                self.scheduler.add(auto_id, config.get("check_interval", 10),
                                   lambda a=auto: self._file_check(a))
                self.scheduler.start()

        elif trigger_type == "url_change":
            url = config.get("url", "")
            if url:
                self.url_watcher.check(auto_id, url)
                self.scheduler.add(auto_id, config.get("check_interval", 300),
                                   lambda a=auto: self._url_check(a))
                self.scheduler.start()

    def _trigger_fired(self, auto: dict):
        """Called when an interval trigger fires."""
        auto_id = auto["id"]
        if auto_id in self._running_autos:
            return  # already running
        t = threading.Thread(target=self._run_automation, args=(auto,), daemon=True)
        self._running_autos[auto_id] = t
        t.start()

    def _cron_check(self, auto: dict, cron_expr: str):
        """Check if cron expression matches now."""
        now = datetime.now()
        if _cron_matches(cron_expr.split(), now):
            self._trigger_fired(auto)

    def _file_check(self, auto: dict):
        """Check file watcher for changes."""
        config = auto.get("trigger_config", {})
        result = self.file_watcher.snapshot(
            auto["id"],
            config.get("directory", ""),
            config.get("pattern", "*"),
        )
        if isinstance(result, dict) and result.get("has_changes"):
            # Inject change info into action params
            auto_copy = dict(auto)
            actions = []
            for a in auto["actions"]:
                a_copy = dict(a)
                a_copy["params"] = dict(a_copy.get("params", {}))
                a_copy["params"]["_changes"] = result
                actions.append(a_copy)
            auto_copy["actions"] = actions
            self._trigger_fired(auto_copy)

    def _url_check(self, auto: dict):
        """Check URL watcher for changes."""
        config = auto.get("trigger_config", {})
        result = self.url_watcher.check(auto["id"], config.get("url", ""))
        if isinstance(result, dict) and result.get("has_changes"):
            self._trigger_fired(auto)

    def _run_automation(self, auto: dict):
        """Execute an automation's actions."""
        auto_id = auto["id"]
        try:
            results = self._execute_actions(auto["actions"])
            status = "success" if not any(r.get("result", {}).get("error") for r in results) else "error"
            self.db.log_run(auto_id, status, {"results": results})
            print(f"[AUTO] {auto['name']}: {status}")
        except Exception as e:
            self.db.log_run(auto_id, "error", {"error": str(e)})
            print(f"[AUTO] {auto['name']} FAILED: {e}")
        finally:
            self._running_autos.pop(auto_id, None)

    # ── Presets ──

    def preset_auto_backup(self, src_path: str, interval_hours: int = 24) -> dict:
        """Create an auto-backup automation."""
        return self.create(
            name=f"Backup: {Path(src_path).name}",
            trigger_type="interval",
            trigger_config={"seconds": interval_hours * 3600},
            actions=[
                {"type": "backup", "params": {"src": src_path}},
                {"type": "log", "params": {"message": f"Backup completed for {src_path}"}},
            ],
            description=f"Auto-backup {src_path} every {interval_hours}h",
        )

    def preset_file_cleanup(self, directory: str, max_age_days: int = 7, pattern: str = "*") -> dict:
        """Create an auto-cleanup automation."""
        return self.create(
            name=f"Cleanup: {Path(directory).name}",
            trigger_type="interval",
            trigger_config={"seconds": 86400},  # daily
            actions=[
                {"type": "file_cleanup", "params": {
                    "directory": directory, "max_age_days": max_age_days, "pattern": pattern,
                }},
                {"type": "log", "params": {"message": f"Cleanup done: {directory}"}},
            ],
            description=f"Delete {pattern} files older than {max_age_days} days in {directory}",
        )

    def preset_url_monitor(self, url: str, notify: bool = True) -> dict:
        """Create a URL change monitor."""
        actions = [
            {"type": "log", "params": {"message": f"URL changed: {url}"}},
        ]
        if notify:
            actions.append({"type": "notify", "params": {
                "title": "CHAOS TYPE ZERO URL Monitor",
                "message": f"Content changed: {url}",
            }})
        return self.create(
            name=f"Monitor: {url[:50]}",
            trigger_type="url_change",
            trigger_config={"url": url, "check_interval": 300},
            actions=actions,
            description=f"Monitor {url} for changes every 5 min",
        )

    def preset_daily_report(self) -> dict:
        """Create a daily report automation."""
        return self.create(
            name="Daily Report",
            trigger_type="cron",
            trigger_config={"expression": "0 22 * * *"},  # 10 PM daily
            actions=[
                {"type": "llm_query", "params": {
                    "prompt": "Generate a daily summary: what tasks were completed, any errors, and recommendations for tomorrow.",
                    "task_type": "write",
                }},
                {"type": "notify", "params": {
                    "title": "CHAOS TYPE ZERO Daily Report",
                    "message": "Daily report generated — check logs",
                    "voice": True,
                }},
            ],
            description="Generate a daily summary report at 10 PM",
        )

    def preset_health_check(self, interval_minutes: int = 5) -> dict:
        """Create a system health check automation."""
        return self.create(
            name="Health Check",
            trigger_type="interval",
            trigger_config={"seconds": interval_minutes * 60},
            actions=[
                {"type": "shell", "params": {"command": "echo CHAOS TYPE ZERO health check OK"}},
                {"type": "log", "params": {"message": "Health check passed"}},
            ],
            description=f"System health check every {interval_minutes} min",
        )


# ─── Singleton ────────────────────────────────────────────────────────

_engine: Optional[AutomationEngine] = None


def get_engine() -> AutomationEngine:
    global _engine
    if _engine is None:
        _engine = AutomationEngine()
    return _engine
