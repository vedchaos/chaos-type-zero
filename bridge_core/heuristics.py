#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Heuristics Engine — Rule-based decision optimization

Features:
- Rules engine: if-then rules for task routing, resource allocation, error recovery
- Pattern recognition: detect recurring patterns in task execution
- Optimization suggestions: recommend faster/better approaches based on history
- Cost estimation: estimate token/time cost before execution
- Risk assessment: score tasks 0-100 for risk level
- Decision caching: remember past decisions for similar inputs
- Rule learning: auto-create rules from successful task patterns
"""

import hashlib
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data" / "heuristics"
DB_PATH = DATA_DIR / "heuristics.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

RISK_KEYWORDS = {
    "delete": 30, "remove": 25, "drop": 30, "truncate": 35, "destroy": 40,
    "overwrite": 25, "modify": 15, "edit": 10, "write": 10, "create": 5,
    "read": 0, "list": 0, "search": 0, "query": 5, "pentest": 50,
    "exploit": 60, "attack": 50, "inject": 55, "brute": 65, "crack": 70,
    "sudo": 45, "root": 45, "admin": 35, "deploy": 25, "migrate": 30,
    "network": 20, "firewall": 25, "ssh": 20, "rm -rf": 80, "format": 50,
}

COST_TIERS = {
    "trivial": {"tokens": 50, "time_s": 0.5, "cost_usd": 0.00001},
    "simple": {"tokens": 200, "time_s": 2, "cost_usd": 0.0001},
    "moderate": {"tokens": 1000, "time_s": 10, "cost_usd": 0.001},
    "complex": {"tokens": 4000, "time_s": 30, "cost_usd": 0.005},
    "heavy": {"tokens": 8000, "time_s": 60, "cost_usd": 0.01},
}

DEFAULT_RULES = [
    {
        "name": "high_risk_block",
        "description": "Flag tasks with risk > 70 for manual review",
        "condition": lambda t: t.get("risk", 0) > 70,
        "action": lambda t: {"action": "flag_for_review", "reason": "High risk task"},
    },
    {
        "name": "simple_speed",
        "description": "Route trivial tasks to fastest provider",
        "condition": lambda t: t.get("tier") == "trivial",
        "action": lambda t: {"action": "route", "provider": "groq", "reason": "Speed optimization"},
    },
    {
        "name": "complex_quality",
        "description": "Route complex tasks to quality providers",
        "condition": lambda t: t.get("tier") in ("complex", "heavy"),
        "action": lambda t: {"action": "route", "provider": "openai", "reason": "Quality priority"},
    },
]


class CTZHeuristics:
    """Rule-based decision optimization engine for CHAOS TYPE ZERO."""

    def __init__(self, db_path=None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
        self.rules = list(DEFAULT_RULES)
        self._load_custom_rules()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_hash TEXT NOT NULL,
            task_desc TEXT,
            outcome TEXT,
            success INTEGER DEFAULT 1,
            metadata TEXT DEFAULT '{}',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_hash TEXT UNIQUE NOT NULL,
            decision TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS learned_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            condition_key TEXT,
            action_key TEXT,
            description TEXT,
            hit_count INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pattern_hash ON patterns(task_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_decision_hash ON decisions(task_hash)")
        conn.commit()
        conn.close()

    def _hash_task(self, task_desc):
        return hashlib.sha256(task_desc.lower().strip().encode()).hexdigest()[:16]

    def _classify_risk(self, task_desc):
        score = 5
        lower = task_desc.lower()
        for keyword, weight in RISK_KEYWORDS.items():
            if keyword in lower:
                score = max(score, score + weight)
        return min(score, 100)

    def assess_risk(self, task_desc):
        """Assess task risk level on a 0-100 scale."""
        return self._classify_risk(task_desc)

    def calculate_risk(self, task_desc):
        """Alias for assess_risk."""
        return self._classify_risk(task_desc)

    def estimate_cost(self, task_desc):
        """Estimate execution cost in USD."""
        tier = self._classify_tier(task_desc)
        return COST_TIERS.get(tier, COST_TIERS["moderate"])["cost_usd"]

    def _classify_tier(self, task_desc):
        lower = task_desc.lower()
        word_count = len(lower.split())
        if word_count <= 5 and score_lower(lower) < 15:
            return "trivial"
        if word_count <= 10:
            return "simple"
        if word_count <= 20:
            return "moderate"
        if word_count <= 40:
            return "complex"
        return "heavy"

    def _load_custom_rules(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT name, description FROM learned_rules")
        rows = c.fetchall()
        conn.close()
        for name, desc in rows:
            if not any(r["name"] == name for r in self.rules):
                self.rules.append({"name": name, "description": desc or "", "condition": None, "action": None})

    def evaluate_task(self, task_desc):
        risk = self._classify_risk(task_desc)
        tier = self._classify_tier(task_desc)
        cost_est = COST_TIERS.get(tier, COST_TIERS["moderate"])
        task_hash = self._hash_task(task_desc)
        cached = self.get_decision(task_hash)
        if cached:
            return {"risk": risk, "cost_est": cost_est, "tier": tier,
                    "recommended_approach": cached["decision"], "cached": True}
        context = {"risk": risk, "tier": tier, "task_desc": task_desc}
        approach = "default"
        for rule in self.rules:
            cond = rule.get("condition")
            if cond and callable(cond):
                try:
                    if cond(context):
                        result = rule["action"](context) if rule.get("action") else {}
                        approach = result.get("action", rule["name"])
                        break
                except Exception:
                    continue
        return {"risk": risk, "cost_est": cost_est, "tier": tier,
                "recommended_approach": approach, "cached": False}

    def suggest_optimization(self, task_history):
        suggestions = []
        if not task_history:
            return [{"suggestion": "No history available", "priority": "low"}]
        durations = [t.get("duration_s", 0) for t in task_history if "duration_s" in t]
        successes = [t.get("success", True) for t in task_history]
        avg_duration = sum(durations) / len(durations) if durations else 0
        success_rate = sum(successes) / len(successes) if successes else 0
        if avg_duration > 30:
            suggestions.append({
                "suggestion": f"Avg task duration {avg_duration:.1f}s is high — consider caching or simpler models",
                "priority": "high", "potential_savings": f"{avg_duration * 0.3:.1f}s per task",
            })
        if success_rate < 0.8:
            suggestions.append({
                "suggestion": f"Success rate {success_rate:.0%} is below 80% — review failure patterns",
                "priority": "high",
            })
        providers = {}
        for t in task_history:
            p = t.get("provider", "unknown")
            providers.setdefault(p, []).append(t.get("success", True))
        for p, results in providers.items():
            sr = sum(results) / len(results) if results else 0
            if sr < 0.7 and len(results) >= 3:
                suggestions.append({
                    "suggestion": f"Provider '{p}' has {sr:.0%} success rate — consider alternatives",
                    "priority": "medium",
                })
        if not suggestions:
            suggestions.append({"suggestion": "Performance looks good — no optimizations needed", "priority": "low"})
        return suggestions

    def learn_pattern(self, task, outcome):
        task_hash = self._hash_task(str(task))
        success = 1 if outcome.get("success", True) else 0
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO patterns (task_hash, task_desc, outcome, success, metadata) VALUES (?, ?, ?, ?, ?)",
                  (task_hash, str(task)[:500], json.dumps(outcome)[:500],
                   success, json.dumps({"provider": outcome.get("provider", "")})))
        c.execute("SELECT COUNT(*), SUM(success) FROM patterns WHERE task_hash = ?", (task_hash,))
        count, total_success = c.fetchone()
        if count >= 3 and total_success and total_success / count > 0.8:
            rule_name = f"learned_{task_hash[:8]}"
            c.execute("""INSERT OR REPLACE INTO learned_rules 
                (name, condition_key, action_key, description, hit_count, success_rate)
                VALUES (?, ?, ?, ?, ?, ?)""",
                      (rule_name, task_hash, "auto", f"Auto-learned from {count} successful executions",
                       count, total_success / count))
        conn.commit()
        conn.close()

    def get_decision(self, task_hash):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT decision, confidence FROM decisions WHERE task_hash = ?", (task_hash,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"decision": row[0], "confidence": row[1]}
        return None

    def save_decision(self, task_hash, decision, confidence=0.5):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO decisions (task_hash, decision, confidence) VALUES (?, ?, ?)""",
                  (task_hash, json.dumps(decision) if not isinstance(decision, str) else decision, confidence))
        conn.commit()
        conn.close()

    def get_rules(self):
        return [{"name": r["name"], "description": r.get("description", "")} for r in self.rules]

    def add_rule(self, name, condition_fn, action_fn, description=""):
        self.rules.append({"name": name, "condition": condition_fn, "action": action_fn, "description": description})


def _score_lower(text):
    score = 5
    for kw, w in RISK_KEYWORDS.items():
        if kw in text:
            score += w
    return min(score, 100)


def score_lower(text):
    return _score_lower(text)


_heuristics = None


def get_heuristics(db_path=None):
    global _heuristics
    if _heuristics is None:
        _heuristics = CTZHeuristics(db_path)
    return _heuristics


if __name__ == "__main__":
    h = get_heuristics()
    print(json.dumps(h.evaluate_task("rm -rf /tmp/logs"), indent=2))
    print(json.dumps(h.evaluate_task("list files in directory"), indent=2))
    print("Rules:", h.get_rules())
