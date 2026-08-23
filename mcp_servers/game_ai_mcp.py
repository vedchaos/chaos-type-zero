#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Game AI Server"""

import json
import sys
import re
import hashlib
import sqlite3
import math
import time
import os
from collections import defaultdict, Counter
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "game" / "game.db"


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT NOT NULL,
        outcome TEXT NOT NULL,
        score INTEGER DEFAULT 0,
        duration_sec REAL DEFAULT 0,
        metadata TEXT DEFAULT '{}',
        created_at REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT NOT NULL,
        action TEXT NOT NULL,
        state_before TEXT DEFAULT '{}',
        state_after TEXT DEFAULT '{}',
        reward REAL DEFAULT 0,
        created_at REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT NOT NULL,
        pattern_hash TEXT NOT NULL,
        pattern_data TEXT NOT NULL,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        created_at REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS screens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT NOT NULL,
        description TEXT NOT NULL,
        elements TEXT DEFAULT '[]',
        raw_data TEXT DEFAULT '{}',
        created_at REAL NOT NULL
    )""")
    conn.commit()
    return conn


def analyze_screen(description, game="unknown"):
    conn = get_db()
    desc_lower = description.lower()
    elements = []
    categories = []

    ui_keywords = {
        "health": ["health", "hp", "life", "hitpoint", "vitality"],
        "score": ["score", "point", "level", "xp", "experience", "coin", "gold"],
        "inventory": ["inventory", "bag", "item", "weapon", "armor", "equipment"],
        "enemy": ["enemy", "monster", "boss", "zombie", "ghost", "alien", "bot"],
        "player": ["player", "character", "hero", "avatar", "self"],
        "map": ["map", "minimap", "compass", "waypoint", "marker"],
        "menu": ["menu", "button", "option", "settings", "pause"],
        "objective": ["objective", "quest", "mission", "goal", "task", "target"],
        "obstacle": ["wall", "door", "barrier", "trap", "pit", "lava"],
        "resource": ["ammo", "medkit", "supply", "resource", "material"]
    }

    for cat, keywords in ui_keywords.items():
        for kw in keywords:
            if kw in desc_lower:
                if cat not in categories:
                    categories.append(cat)
                elements.append({"type": cat, "keyword": kw})

    threats = len([e for e in elements if e["type"] == "enemy"])
    resources = len([e for e in elements if e["type"] in ("resource", "inventory")])
    danger = min(1.0, threats * 0.25 + (0.3 if "obstacle" in categories else 0))
    opportunity = min(1.0, resources * 0.3 + (0.2 if "objective" in categories else 0))

    analysis = {
        "game": game,
        "element_count": len(elements),
        "elements": elements,
        "categories": categories,
        "threat_level": round(danger, 2),
        "opportunity_level": round(opportunity, 2),
        "complexity": round(min(1.0, len(elements) * 0.12), 2),
        "has_player": "player" in categories,
        "has_enemy": "enemy" in categories,
        "has_objective": "objective" in categories,
        "has_map": "map" in categories,
        "has_resources": resources > 0,
        "recommendation": _generate_recommendation(categories, danger, opportunity),
        "timestamp": time.time()
    }

    conn.execute(
        "INSERT INTO screens (game, description, elements, raw_data, created_at) VALUES (?, ?, ?, ?, ?)",
        (game, description, json.dumps(elements), json.dumps(analysis), time.time())
    )
    conn.commit()
    conn.close()
    return analysis


def _generate_recommendation(categories, danger, opportunity):
    if danger > 0.7:
        return "HIGH THREAT — retreat or prepare defenses"
    if danger > 0.4 and opportunity > 0.5:
        return "Balanced — cautiously engage while collecting resources"
    if opportunity > 0.6:
        return "Resource-rich — prioritize collection"
    if "objective" in categories:
        return "Objective visible — focus on completion"
    if "map" in categories:
        return "Map available — scout before advancing"
    return "Explore and assess surroundings"


def generate_strategy(state, game="unknown"):
    conn = get_db()

    recent = conn.execute(
        "SELECT outcome, score FROM stats WHERE game = ? ORDER BY created_at DESC LIMIT 10",
        (game,)
    ).fetchall()
    avg_score = sum(r["score"] for r in recent) / max(len(recent), 1)
    win_rate = sum(1 for r in recent if r["outcome"] == "win") / max(len(recent), 1)

    patterns = conn.execute(
        "SELECT pattern_data, success_count, fail_count FROM patterns WHERE game = ? ORDER BY success_count DESC LIMIT 5",
        (game,)
    ).fetchall()

    state_obj = state if isinstance(state, dict) else {"description": str(state)}
    threats = state_obj.get("threats", 0)
    resources = state_obj.get("resources", 0)
    health = state_obj.get("health", 100)
    has_objective = state_obj.get("has_objective", False)

    strategy = {
        "game": game,
        "current_state": state_obj,
        "performance": {
            "recent_games": len(recent),
            "avg_score": round(avg_score, 1),
            "win_rate": round(win_rate * 100, 1)
        },
        "tactics": [],
        "priority_actions": [],
        "risk_assessment": "low"
    }

    if health < 30:
        strategy["priority_actions"].append("RETREAT — health critically low")
        strategy["risk_assessment"] = "critical"
    elif threats > 3 and health < 60:
        strategy["priority_actions"].append("DEFEND — overwhelming threats detected")
        strategy["risk_assessment"] = "high"
    elif has_objective and threats <= 2:
        strategy["priority_actions"].append("ADVANCE — clear path to objective")
        strategy["tactics"].append("rush_objective")
    else:
        strategy["priority_actions"].append("ASSESS — evaluate surroundings")
        strategy["tactics"].append("recon_first")

    if resources > 0:
        strategy["tactics"].append("collect_resources")
        strategy["priority_actions"].append("GATHER — resources available nearby")

    if win_rate > 0.7 and len(recent) >= 5:
        strategy["tactics"].append("aggressive_play")
        strategy["risk_assessment"] = "calculated"
    elif win_rate < 0.3 and len(recent) >= 3:
        strategy["tactics"].append("conservative_play")
        strategy["tactics"].append("avoid_combat")

    for p in patterns:
        pdata = json.loads(p["pattern_data"]) if isinstance(p["pattern_data"], str) else p["pattern_data"]
        total = p["success_count"] + p["fail_count"]
        if total > 0 and p["success_count"] / total > 0.6:
            strategy["tactics"].append(f"proven_pattern_{p['pattern_hash'][:8]}")

    strategy["tactics"] = list(dict.fromkeys(strategy["tactics"]))
    strategy["timestamp"] = time.time()

    conn.close()
    return strategy


def track_stats(game, outcome, score=0, duration_sec=0, metadata=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO stats (game, outcome, score, duration_sec, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (game, outcome, score, duration_sec, json.dumps(metadata or {}), time.time())
    )
    conn.commit()

    stats = conn.execute(
        """SELECT outcome, COUNT(*) as count, AVG(score) as avg_score,
           MAX(score) as best_score, SUM(duration_sec) as total_time
           FROM stats WHERE game = ? GROUP BY outcome""",
        (game,)
    ).fetchall()

    total = conn.execute("SELECT COUNT(*) as c FROM stats WHERE game = ?", (game,)).fetchone()["c"]
    conn.close()

    return {
        "recorded": True,
        "game": game,
        "outcome": outcome,
        "score": score,
        "aggregate": {r["outcome"]: {"count": r["count"], "avg_score": round(r["avg_score"], 1), "best_score": r["best_score"]} for r in stats},
        "total_games": total,
        "timestamp": time.time()
    }


def recommend_move(state, game="unknown"):
    conn = get_db()
    state_obj = state if isinstance(state, dict) else {"description": str(state)}

    recent_wins = conn.execute(
        """SELECT history.action, history.reward FROM history
           JOIN stats ON history.game = stats.game
           WHERE history.game = ? AND stats.outcome = 'win'
           ORDER BY history.created_at DESC LIMIT 20""",
        (game,)
    ).fetchall()

    action_rewards = defaultdict(list)
    for r in recent_wins:
        action_rewards[r["action"]].append(r["reward"])

    best_actions = []
    for action, rewards in action_rewards.items():
        avg = sum(rewards) / len(rewards)
        best_actions.append({"action": action, "avg_reward": round(avg, 2), "count": len(rewards)})
    best_actions.sort(key=lambda x: x["avg_reward"], reverse=True)

    health = state_obj.get("health", 100)
    threats = state_obj.get("threats", 0)

    moves = []
    if health < 25:
        moves.append({"action": "heal", "confidence": 0.9, "reason": "critical health"})
    elif health < 50 and threats > 0:
        moves.append({"action": "flee", "confidence": 0.7, "reason": "low health with threats"})
    elif threats == 0 and state_obj.get("has_objective"):
        moves.append({"action": "push_objective", "confidence": 0.85, "reason": "no threats, objective ahead"})
    else:
        moves.append({"action": "scan_area", "confidence": 0.6, "reason": "gather information"})

    for ba in best_actions[:3]:
        existing = [m["action"] for m in moves]
        if ba["action"] not in existing:
            moves.append({
                "action": ba["action"],
                "confidence": min(0.95, ba["avg_reward"] / 10),
                "reason": f"historical success (avg reward: {ba['avg_reward']}, {ba['count']}x)"
            })

    moves.sort(key=lambda x: x["confidence"], reverse=True)

    result = {
        "game": game,
        "state": state_obj,
        "recommended_moves": moves[:5],
        "best_historical": best_actions[:3],
        "timestamp": time.time()
    }

    conn.close()
    return result


def get_history(game=None, limit=20):
    conn = get_db()
    if game:
        rows = conn.execute(
            "SELECT * FROM history WHERE game = ? ORDER BY created_at DESC LIMIT ?",
            (game, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()

    conn.close()
    return {
        "count": len(rows),
        "entries": [
            {
                "id": r["id"], "game": r["game"], "action": r["action"],
                "state_before": r["state_before"], "state_after": r["state_after"],
                "reward": r["reward"], "timestamp": r["created_at"]
            }
            for r in rows
        ]
    }


def train_patterns(game, actions, result, reward=0):
    conn = get_db()
    pattern_str = json.dumps(sorted(actions)) if isinstance(actions, list) else str(actions)
    phash = hashlib.md5(pattern_str.encode(), usedforsecurity=False).hexdigest()

    existing = conn.execute(
        "SELECT id, success_count, fail_count FROM patterns WHERE game = ? AND pattern_hash = ?",
        (game, phash)
    ).fetchone()

    if existing:
        if result == "win":
            conn.execute("UPDATE patterns SET success_count = success_count + 1 WHERE id = ?", (existing["id"],))
        else:
            conn.execute("UPDATE patterns SET fail_count = fail_count + 1 WHERE id = ?", (existing["id"],))
    else:
        conn.execute(
            "INSERT INTO patterns (game, pattern_hash, pattern_data, success_count, fail_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (game, phash, json.dumps({"actions": actions, "result": result}), 1 if result == "win" else 0, 0 if result == "win" else 1, time.time())
        )

    conn.execute(
        "INSERT INTO history (game, action, state_before, reward, created_at) VALUES (?, ?, ?, ?, ?)",
        (game, json.dumps({"actions": actions, "result": result}), json.dumps({}), reward, time.time())
    )

    conn.commit()

    stats = conn.execute(
        "SELECT success_count, fail_count FROM patterns WHERE game = ? AND pattern_hash = ?",
        (game, phash)
    ).fetchone()

    total = stats["success_count"] + stats["fail_count"]
    conn.close()

    return {
        "trained": True,
        "game": game,
        "pattern_hash": phash,
        "success_rate": round(stats["success_count"] / max(total, 1) * 100, 1),
        "total_uses": total,
        "reward": reward,
        "timestamp": time.time()
    }


TOOLS = [
    {"name": "ctz_game_analyze_screen", "description": "Analyze a game screenshot description — identify UI elements, threats, resources", "inputSchema": {"type": "object", "properties": {"description": {"type": "string", "description": "Text description of the game screen"}, "game": {"type": "string", "default": "unknown"}}, "required": ["description"]}},
    {"name": "ctz_game_strategy", "description": "Generate a game strategy based on current state and historical performance", "inputSchema": {"type": "object", "properties": {"state": {"type": "object", "description": "Current game state (health, threats, resources, has_objective, etc.)"}, "game": {"type": "string", "default": "unknown"}}, "required": ["state"]}},
    {"name": "ctz_game_track_stats", "description": "Track game statistics — wins, losses, scores, duration", "inputSchema": {"type": "object", "properties": {"game": {"type": "string"}, "outcome": {"type": "string", "enum": ["win", "loss", "draw", "abandoned"]}, "score": {"type": "integer", "default": 0}, "duration_sec": {"type": "number", "default": 0}, "metadata": {"type": "object", "default": {}}}, "required": ["game", "outcome"]}},
    {"name": "ctz_game_recommend", "description": "Recommend the next best move based on state and historical data", "inputSchema": {"type": "object", "properties": {"state": {"type": "object", "description": "Current game state"}, "game": {"type": "string", "default": "unknown"}}, "required": ["state"]}},
    {"name": "ctz_game_history", "description": "Get game play history", "inputSchema": {"type": "object", "properties": {"game": {"type": "string", "default": ""}, "limit": {"type": "integer", "default": 20}}}},
    {"name": "ctz_game_train", "description": "Train on game patterns — record action sequences and outcomes", "inputSchema": {"type": "object", "properties": {"game": {"type": "string"}, "actions": {"type": "array", "items": {"type": "string"}, "description": "Sequence of actions taken"}, "result": {"type": "string", "enum": ["win", "loss"], "description": "Outcome of the pattern"}, "reward": {"type": "number", "default": 0}}, "required": ["game", "actions", "result"]}},
]


def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "ctz-game-ai", "version": "1.0.0"}
        }}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            if name == "ctz_game_analyze_screen":
                r = analyze_screen(args["description"], args.get("game", "unknown"))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r, indent=2)}]}}
            elif name == "ctz_game_strategy":
                r = generate_strategy(args["state"], args.get("game", "unknown"))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r, indent=2)}]}}
            elif name == "ctz_game_track_stats":
                r = track_stats(args["game"], args["outcome"], args.get("score", 0), args.get("duration_sec", 0), args.get("metadata"))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r, indent=2)}]}}
            elif name == "ctz_game_recommend":
                r = recommend_move(args["state"], args.get("game", "unknown"))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r, indent=2)}]}}
            elif name == "ctz_game_history":
                r = get_history(args.get("game", ""), args.get("limit", 20))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r, indent=2)}]}}
            elif name == "ctz_game_train":
                r = train_patterns(args["game"], args["actions"], args["result"], args.get("reward", 0))
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(r, indent=2)}]}}
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
        except:
            pass
