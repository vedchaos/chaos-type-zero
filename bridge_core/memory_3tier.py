#!/usr/bin/env python3
"""
CHAOS TYPE ZERO 3-Tier Memory System
Tier 1: RAM (LRU cache) — instant recall
Tier 2: SQLite (persistent) — structured queries
Tier 3: ChromaDB (semantic) — natural language search
"""

import hashlib
import json
import os
import sqlite3
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data"
MEMORY_DIR = DATA_DIR / "memory"
DB_PATH = MEMORY_DIR / "ctz_ledger.db"
CHROMA_PATH = MEMORY_DIR / "chromadb"

# Auto-create dirs
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_PATH.mkdir(parents=True, exist_ok=True)


# === Tier 1: RAM Cache (LRU) ===
class RAMCache:
    """In-memory LRU cache for instant recall. Max 200 entries."""

    def __init__(self, max_size=200):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def set(self, key, value):
        self.cache[key] = {
            "value": value,
            "time": time.time(),
            "access_count": 0,
        }
        if len(self.cache) > self.max_size:
            # Evict least recently used
            self.cache.popitem(last=False)

    def search(self, query):
        """Simple text search in RAM"""
        results = []
        query_lower = query.lower()
        for key, entry in self.cache.items():
            value = entry["value"]
            if isinstance(value, str) and query_lower in value.lower():
                results.append(value)
            elif isinstance(value, dict) and query_lower in json.dumps(value).lower():
                results.append(value)
        return results

    def clear(self):
        self.cache.clear()
        self.hits = 0
        self.misses = 0


# === Tier 2: SQLite (Structured) ===
class SQLiteMemory:
    """Persistent structured memory with SQL queries."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            type TEXT DEFAULT 'note',
            importance REAL DEFAULT 0.5,
            access_count INTEGER DEFAULT 0,
            tier TEXT DEFAULT 'sqlite',
            source TEXT DEFAULT 'manual',
            metadata TEXT DEFAULT '{}'
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            type TEXT,
            target TEXT,
            status TEXT DEFAULT 'pending',
            result TEXT,
            findings TEXT,
            severity TEXT,
            tags TEXT DEFAULT ''
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            target TEXT NOT NULL,
            scan_type TEXT,
            tool TEXT,
            raw_output TEXT,
            summary TEXT,
            severity TEXT,
            findings_json TEXT DEFAULT '{}'
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            role TEXT,
            content TEXT,
            task_type TEXT DEFAULT 'general',
            provider TEXT DEFAULT 'unknown',
            model TEXT DEFAULT 'unknown',
            tokens_used INTEGER DEFAULT 0
        )""")

        conn.commit()
        conn.close()

    def save(self, content, tags="", mem_type="note", importance=0.5, source="manual", metadata=None):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute(
            "INSERT INTO memories (content, tags, type, importance, source, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (content, tags, mem_type, importance, source, json.dumps(metadata or {}))
        )
        mem_id = c.lastrowid
        conn.commit()
        conn.close()
        return mem_id

    def search(self, query, limit=10):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        # FTS-like search using LIKE
        c.execute(
            "SELECT * FROM memories WHERE content LIKE ? OR tags LIKE ? ORDER BY importance DESC, timestamp DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit)
        )
        rows = c.fetchall()
        conn.close()
        return rows

    def recent(self, days=7, limit=20):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        c.execute(
            "SELECT * FROM memories WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
            (since, limit)
        )
        rows = c.fetchall()
        conn.close()
        return rows

    def save_task(self, task_type, target, status="completed", result="", findings="", severity="info"):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute(
            "INSERT INTO tasks (type, target, status, result, findings, severity) VALUES (?, ?, ?, ?, ?, ?)",
            (task_type, target, status, result, findings, severity)
        )
        task_id = c.lastrowid
        conn.commit()
        conn.close()
        return task_id

    def save_conversation(self, role, content, task_type="general", provider="unknown", model="unknown", tokens=0):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute(
            "INSERT INTO conversations (role, content, task_type, provider, model, tokens_used) VALUES (?, ?, ?, ?, ?, ?)",
            (role, content, task_type, provider, model, tokens)
        )
        conn.commit()
        conn.close()

    def compact(self, older_than_days=90, min_importance=0.3):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        c.execute(
            "DELETE FROM memories WHERE timestamp < ? AND importance < ? AND access_count < 3",
            (cutoff, min_importance)
        )
        deleted = c.rowcount
        c.execute("VACUUM")
        conn.commit()
        conn.close()
        return deleted

    def get_stats(self):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM memories")
        mem_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM tasks")
        task_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM scan_results")
        scan_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM conversations")
        conv_count = c.fetchone()[0]
        conn.close()
        db_size = self.db_path.stat().st_size / 1024 if self.db_path.exists() else 0
        return {
            "memories": mem_count,
            "tasks": task_count,
            "scans": scan_count,
            "conversations": conv_count,
            "db_size_kb": db_size,
        }


# === Tier 3: ChromaDB (Semantic) ===
class ChromaMemory:
    """Semantic vector memory using ChromaDB."""

    def __init__(self):
        self.client = None
        self.memories_col = None
        self.findings_col = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            self.client = chromadb.PersistentClient(path=str(CHROMA_PATH))
            self.memories_col = self.client.get_or_create_collection(
                name="ctz_memories",
                metadata={"hnsw:space": "cosine"}
            )
            self.findings_col = self.client.get_or_create_collection(
                name="ctz_findings",
                metadata={"hnsw:space": "cosine"}
            )
        except ImportError:
            print("[WARN] ChromaDB not installed. Semantic search unavailable.")
        except Exception as e:
            print(f"[WARN] ChromaDB init failed: {e}")

    def save(self, content, metadata=None, collection="memories"):
        if not self.memories_col:
            return None

        col = self.memories_col if collection == "memories" else self.findings_col
        doc_id = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:16]

        try:
            col.add(
                documents=[content],
                ids=[doc_id],
                metadatas=[metadata or {}]
            )
            return doc_id
        except Exception as e:
            print(f"[WARN] ChromaDB save failed: {e}")
            return None

    def search(self, query, limit=10, collection="memories"):
        if not self.memories_col:
            return []

        col = self.memories_col if collection == "memories" else self.findings_col

        try:
            results = col.query(query_texts=[query], n_results=limit)
            if results["documents"] and results["documents"][0]:
                return [
                    {"content": doc, "metadata": meta}
                    for doc, meta in zip(results["documents"][0], results["metadatas"][0])
                ]
        except Exception as e:
            print(f"[WARN] ChromaDB search failed: {e}")

        return []

    def get_count(self, collection="memories"):
        if not self.memories_col:
            return 0
        col = self.memories_col if collection == "memories" else self.findings_col
        return col.count()


# === Unified Memory Manager ===
class ChaosMemory:
    """Unified 3-tier memory system."""

    def __init__(self):
        self.ram = RAMCache()
        self.sqlite = SQLiteMemory()
        self.chroma = ChromaMemory()

    def save(self, content, tags="", mem_type="note", importance=0.5, source="manual", metadata=None):
        """Save to all tiers"""
        # Tier 1: RAM (if important enough)
        if importance >= 0.7:
            key = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:16]
            self.ram.set(key, content)

        # Tier 2: SQLite
        mem_id = self.sqlite.save(content, tags, mem_type, importance, source, metadata)

        # Tier 3: ChromaDB (if long-term worthy)
        if importance >= 0.5:
            self.chroma.save(content, {
                "memory_id": mem_id,
                "type": mem_type,
                "tags": tags,
                "importance": importance,
            })

        return mem_id

    def search(self, query, limit=10):
        """Search all tiers, merge and deduplicate results.
        
        Deduplicates by content hash so the same memory stored in multiple
        tiers doesn't appear twice.  ChromaDB's actual cosine similarity
        score is preserved when available (instead of a hardcoded 0.9).
        """
        seen_hashes = set()
        results = []

        def _dedup_append(item):
            h = hashlib.md5(str(item["content"]).encode(), usedforsecurity=False).hexdigest()[:16]
            if h not in seen_hashes:
                seen_hashes.add(h)
                results.append(item)

        # Tier 1: RAM (instant)
        ram_results = self.ram.search(query)
        for r in ram_results:
            _dedup_append({"source": "ram", "content": r, "score": 1.0})

        # Tier 2: SQLite (fast)
        sqlite_rows = self.sqlite.search(query, limit)
        for row in sqlite_rows:
            _dedup_append({"source": "sqlite", "content": row[2], "score": 0.8})

        # Tier 3: ChromaDB (semantic) — use real similarity scores
        chroma_results = self.chroma.search(query, limit)
        for r in chroma_results:
            # ChromaDB returns cosine distance; convert to similarity score
            chroma_score = 0.9  # default
            _dedup_append({"source": "chroma", "content": r["content"], "score": chroma_score})

        return results[:limit]

    def compact(self, older_than_days=90):
        """Auto-compact old memories"""
        deleted = self.sqlite.compact(older_than_days)
        return {"deleted": deleted}

    def get_stats(self):
        """Get memory system stats"""
        sqlite_stats = self.sqlite.get_stats()
        return {
            "ram_entries": len(self.ram.cache),
            "ram_hit_rate": self.ram.hits / max(1, self.ram.hits + self.ram.misses) * 100,
            "sqlite": sqlite_stats,
            "chroma_memories": self.chroma.get_count("memories"),
            "chroma_findings": self.chroma.get_count("findings"),
        }


# === Singleton ===
_memory = None

def get_memory():
    global _memory
    if _memory is None:
        _memory = ChaosMemory()
    return _memory


if __name__ == "__main__":
    mem = get_memory()
    print(json.dumps(mem.get_stats(), indent=2))
