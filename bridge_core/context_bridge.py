#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Context Bridge
Cross-session memory persistence — remember everything across sessions.

Features:
- Session tracking with metadata
- Context saving (decisions, facts, task outcomes, preferences)
- Context restoration for new sessions
- Semantic search across all past sessions (ChromaDB)
- Auto-extraction of key facts
- Session linking (related sessions)
- Context summarization
- Auto-compaction of old contexts
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data"
CONTEXT_DIR = DATA_DIR / "context"
DB_PATH = CONTEXT_DIR / "context_bridge.db"
CHROMA_PATH = CONTEXT_DIR / "chromadb"

# Auto-create dirs
CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_PATH.mkdir(parents=True, exist_ok=True)


class ContextBridge:
    """
    Cross-session memory persistence.
    
    Stores:
    - Sessions: metadata about each chat session
    - Context entries: decisions, facts, outcomes, preferences
    - Key facts: extracted facts that persist across sessions
    - Session links: relationships between sessions
    """
    
    def __init__(self, db_path=None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
        self._chroma = None  # Lazy init
    
    def _init_db(self):
        """Initialize SQLite tables."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Sessions table
        c.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,
            tags TEXT DEFAULT '[]',
            summary TEXT DEFAULT '',
            model TEXT DEFAULT '',
            total_messages INTEGER DEFAULT 0,
            task_types TEXT DEFAULT '[]',
            is_active INTEGER DEFAULT 1
        )""")
        
        # Context entries — individual pieces of context
        c.execute("""CREATE TABLE IF NOT EXISTS context_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            entry_type TEXT NOT NULL,
            content TEXT NOT NULL,
            importance REAL DEFAULT 0.5,
            tags TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )""")
        
        # Key facts — extracted facts that persist across all sessions
        c.execute("""CREATE TABLE IF NOT EXISTS key_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source_session TEXT,
            confidence REAL DEFAULT 0.8,
            times_recalled INTEGER DEFAULT 0,
            last_recalled DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )""")
        
        # Session links — relationships between sessions
        c.execute("""CREATE TABLE IF NOT EXISTS session_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_session TEXT,
            to_session TEXT,
            link_type TEXT DEFAULT 'related',
            reason TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_session) REFERENCES sessions(id),
            FOREIGN KEY (to_session) REFERENCES sessions(id)
        )""")
        
        # Conversation snapshots — key messages for context restore
        c.execute("""CREATE TABLE IF NOT EXISTS conversation_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            message_index INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )""")
        
        conn.commit()
        conn.close()
    
    def _get_chroma(self):
        """Lazy-init ChromaDB collection."""
        if self._chroma is None:
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(CHROMA_PATH))
                self._chroma = client.get_or_create_collection(
                    name="context_bridge",
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception:
                self._chroma = None
        return self._chroma
    
    # === Session Management ===
    
    def start_session(self, title="", tags=None, model=""):
        """Start a new session. Returns session ID."""
        session_id = f"ses_{int(time.time())}_{os.urandom(4).hex()}"
        tags = tags or []
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO sessions (id, title, tags, model, is_active) VALUES (?, ?, ?, ?, 1)",
            (session_id, title, json.dumps(tags), model)
        )
        conn.commit()
        conn.close()
        return session_id
    
    def end_session(self, session_id, summary="", tags=None):
        """End a session and save summary."""
        tags = tags or []
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP, summary = ?, tags = ?, is_active = 0 WHERE id = ?",
            (summary, json.dumps(tags), session_id)
        )
        conn.commit()
        conn.close()
    
    def get_active_sessions(self):
        """Get all currently active sessions."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM sessions WHERE is_active = 1 ORDER BY started_at DESC")
        rows = c.fetchall()
        conn.close()
        return rows
    
    def get_session(self, session_id):
        """Get session by ID."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        return row
    
    def list_sessions(self, limit=20, tags=None):
        """List recent sessions."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if tags:
            tag_filter = "%".join(tags)
            c.execute(
                "SELECT * FROM sessions WHERE tags LIKE ? ORDER BY started_at DESC LIMIT ?",
                (f"%{tag_filter}%", limit)
            )
        else:
            c.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows
    
    # === Context Entries ===
    
    def save_context(self, session_id, entry_type, content, importance=0.5, tags=None, metadata=None):
        """
        Save a context entry to a session.
        
        entry_type: 'decision', 'fact', 'task_outcome', 'preference', 'note', 'error', 'insight'
        """
        tags = tags or []
        metadata = metadata or {}
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO context_entries (session_id, entry_type, content, importance, tags, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, entry_type, content, importance, json.dumps(tags), json.dumps(metadata))
        )
        entry_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Also add to ChromaDB for semantic search
        chroma = self._get_chroma()
        if chroma:
            try:
                chroma.add(
                    documents=[content],
                    metadatas=[{
                        "session_id": session_id,
                        "entry_type": entry_type,
                        "importance": importance,
                        "tags": json.dumps(tags),
                        "timestamp": datetime.now().isoformat()
                    }],
                    ids=[f"ctx_{entry_id}"]
                )
            except Exception:
                pass  # ChromaDB optional
        
        return entry_id
    
    def get_context(self, session_id, entry_type=None, limit=20):
        """Get context entries for a session."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if entry_type:
            c.execute(
                "SELECT * FROM context_entries WHERE session_id = ? AND entry_type = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
                (session_id, entry_type, limit)
            )
        else:
            c.execute(
                "SELECT * FROM context_entries WHERE session_id = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
                (session_id, limit)
            )
        rows = c.fetchall()
        conn.close()
        return rows
    
    def search_context(self, query, limit=10, entry_type=None):
        """Search context entries across all sessions using ChromaDB."""
        chroma = self._get_chroma()
        if chroma:
            try:
                where_filter = None
                if entry_type:
                    where_filter = {"entry_type": entry_type}
                
                results = chroma.query(
                    query_texts=[query],
                    n_results=limit,
                    where=where_filter
                )
                
                # Format results
                output = []
                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        distance = results["distances"][0][i] if results["distances"] else 0
                        output.append({
                            "content": doc,
                            "session_id": meta.get("session_id", ""),
                            "entry_type": meta.get("entry_type", ""),
                            "importance": meta.get("importance", 0.5),
                            "relevance": round(1 - distance, 3),
                            "timestamp": meta.get("timestamp", "")
                        })
                return output
            except Exception:
                pass
        
        # Fallback to SQLite LIKE search
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if entry_type:
            c.execute(
                "SELECT * FROM context_entries WHERE content LIKE ? AND entry_type = ? ORDER BY importance DESC LIMIT ?",
                (f"%{query}%", entry_type, limit)
            )
        else:
            c.execute(
                "SELECT * FROM context_entries WHERE content LIKE ? ORDER BY importance DESC LIMIT ?",
                (f"%{query}%", limit)
            )
        rows = c.fetchall()
        conn.close()
        output = []
        for r in rows:
            output.append({
                "id": r[0],
                "session_id": r[1],
                "entry_type": r[2],
                "content": r[3],
                "importance": r[4],
                "tags": r[5],
                "metadata": r[6],
                "timestamp": str(r[7]),
                "relevance": 1.0,
            })
        return output
    
    # === Key Facts ===
    
    def save_fact(self, fact, category="general", source_session="", confidence=0.8):
        """Save a key fact that persists across all sessions."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Check for duplicate
        c.execute("SELECT id FROM key_facts WHERE fact = ? AND is_active = 1", (fact,))
        existing = c.fetchone()
        
        if existing:
            # Update existing fact
            c.execute(
                "UPDATE key_facts SET updated_at = CURRENT_TIMESTAMP, confidence = MAX(confidence, ?) WHERE id = ?",
                (confidence, existing[0])
            )
            fact_id = existing[0]
        else:
            c.execute(
                "INSERT INTO key_facts (fact, category, source_session, confidence) VALUES (?, ?, ?, ?)",
                (fact, category, source_session, confidence)
            )
            fact_id = c.lastrowid
        
        conn.commit()
        conn.close()
        
        # Also add to ChromaDB
        chroma = self._get_chroma()
        if chroma:
            try:
                chroma.add(
                    documents=[fact],
                    metadatas=[{
                        "category": category,
                        "source_session": source_session,
                        "confidence": confidence,
                        "type": "key_fact"
                    }],
                    ids=[f"fact_{fact_id}"]
                )
            except Exception:
                pass
        
        return fact_id
    
    def get_facts(self, category=None, limit=50):
        """Get key facts, optionally filtered by category."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if category:
            c.execute(
                "SELECT * FROM key_facts WHERE category = ? AND is_active = 1 ORDER BY confidence DESC, times_recalled DESC LIMIT ?",
                (category, limit)
            )
        else:
            c.execute(
                "SELECT * FROM key_facts WHERE is_active = 1 ORDER BY confidence DESC, times_recalled DESC LIMIT ?",
                (limit,)
            )
        rows = c.fetchall()
        conn.close()
        return rows
    
    def recall_fact(self, fact_id):
        """Mark a fact as recalled (increment counter)."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "UPDATE key_facts SET times_recalled = times_recalled + 1, last_recalled = CURRENT_TIMESTAMP WHERE id = ?",
            (fact_id,)
        )
        conn.commit()
        conn.close()
    
    def search_facts(self, query, limit=10):
        """Search key facts semantically."""
        chroma = self._get_chroma()
        if chroma:
            try:
                results = chroma.query(
                    query_texts=[query],
                    n_results=limit,
                    where={"type": "key_fact"}
                )
                output = []
                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        distance = results["distances"][0][i] if results["distances"] else 0
                        output.append({
                            "fact": doc,
                            "category": meta.get("category", ""),
                            "confidence": meta.get("confidence", 0.8),
                            "relevance": round(1 - distance, 3)
                        })
                return output
            except Exception:
                pass
        
        # Fallback
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT * FROM key_facts WHERE fact LIKE ? AND is_active = 1 ORDER BY confidence DESC LIMIT ?",
            (f"%{query}%", limit)
        )
        rows = c.fetchall()
        conn.close()
        output = []
        for r in rows:
            output.append({
                "id": r[0],
                "fact": r[1],
                "category": r[2],
                "source_session": r[3],
                "confidence": r[4],
                "times_recalled": r[5],
                "last_recalled": str(r[6]),
                "created_at": str(r[7]),
                "relevance": 1.0,
            })
        return output
    
    def delete_fact(self, fact_id):
        """Soft-delete a key fact."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE key_facts SET is_active = 0 WHERE id = ?", (fact_id,))
        conn.commit()
        conn.close()
    
    # === Session Links ===
    
    def link_sessions(self, from_session, to_session, link_type="related", reason=""):
        """Create a link between two sessions."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO session_links (from_session, to_session, link_type, reason) VALUES (?, ?, ?, ?)",
            (from_session, to_session, link_type, reason)
        )
        conn.commit()
        conn.close()
    
    def get_linked_sessions(self, session_id):
        """Get all sessions linked to a given session."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """SELECT s.*, sl.link_type, sl.reason FROM sessions s 
               JOIN session_links sl ON (s.id = sl.to_session OR s.id = sl.from_session)
               WHERE (sl.from_session = ? OR sl.to_session = ?) AND s.id != ?
               ORDER BY s.started_at DESC""",
            (session_id, session_id, session_id)
        )
        rows = c.fetchall()
        conn.close()
        return rows
    
    # === Conversation Snapshots ===
    
    def save_message(self, session_id, role, content, message_index=0):
        """Save a key message for context restore."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO conversation_snapshots (session_id, role, content, message_index) VALUES (?, ?, ?, ?)",
            (session_id, role, content, message_index)
        )
        conn.commit()
        conn.close()
    
    def get_session_messages(self, session_id, limit=50):
        """Get messages from a session."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT * FROM conversation_snapshots WHERE session_id = ? ORDER BY message_index ASC LIMIT ?",
            (session_id, limit)
        )
        rows = c.fetchall()
        conn.close()
        return rows
    
    # === Context Restore (The Magic) ===
    
    def restore_context(self, query, max_tokens=2000):
        """
        Restore context for a new session based on a query.
        Returns a structured context block that can be injected into a new session.
        
        This is the CORE feature — it finds everything relevant from past sessions
        and returns it in a format ready to use.
        """
        context_parts = []
        total_chars = 0
        
        # 1. Search key facts
        facts = self.search_facts(query, limit=10)
        if facts:
            facts_text = "\n".join([f"• {f['fact']} (confidence: {f['confidence']})" for f in facts])
            context_parts.append(f"## Key Facts\n{facts_text}")
            total_chars += len(facts_text)
        
        # 2. Search context entries
        entries = self.search_context(query, limit=10)
        if entries:
            entries_text = "\n".join([
                f"• [{e['entry_type']}] {e['content'][:200]} (session: {e['session_id'][:15]}...)"
                for e in entries
            ])
            context_parts.append(f"## Relevant Context\n{entries_text}")
            total_chars += len(entries_text)
        
        # 3. Find recent session summaries
        recent = self.list_sessions(limit=5)
        if recent:
            summaries = []
            for s in recent:
                if s[6]:  # summary exists
                    summaries.append(f"• {s[1] or 'Untitled'}: {s[6][:150]}")
            if summaries:
                context_parts.append(f"## Recent Sessions\n" + "\n".join(summaries))
                total_chars += sum(len(s) for s in summaries)
        
        # 4. Truncate if too long
        full_context = "\n\n".join(context_parts)
        if total_chars > max_tokens * 4:  # rough char estimate
            full_context = full_context[:max_tokens * 4] + "\n\n[Context truncated]"
        
        return {
            "context": full_context,
            "facts_count": len(facts),
            "entries_count": len(entries),
            "sessions_count": len(recent),
            "total_chars": total_chars
        }
    
    # === Auto-Compaction ===
    
    def compact(self, days_old=90, min_importance=0.3):
        """
        Auto-compact old context entries.
        - Entries older than days_old with low importance → archived
        - Key facts with low recall count → deactivated
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days_old)).isoformat()
        
        # Archive old low-importance entries
        c.execute(
            "UPDATE context_entries SET importance = importance * 0.5 WHERE created_at < ? AND importance < ?",
            (cutoff, min_importance)
        )
        archived_entries = c.rowcount
        
        # Deactivate rarely-recalled facts
        c.execute(
            "UPDATE key_facts SET is_active = 0 WHERE created_at < ? AND times_recalled < 3 AND confidence < 0.5",
            (cutoff,)
        )
        deactivated_facts = c.rowcount
        
        # Clean old conversation snapshots (keep last 7 days)
        snap_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        c.execute("DELETE FROM conversation_snapshots WHERE created_at < ?", (snap_cutoff,))
        deleted_snaps = c.rowcount
        
        conn.commit()
        conn.close()
        
        return {
            "archived_entries": archived_entries,
            "deactivated_facts": deactivated_facts,
            "deleted_snapshots": deleted_snaps
        }
    
    # === Stats ===
    
    def stats(self):
        """Get context bridge statistics."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
        active_sessions = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM context_entries")
        total_entries = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM key_facts WHERE is_active = 1")
        active_facts = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM session_links")
        total_links = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM conversation_snapshots")
        total_messages = c.fetchone()[0]
        
        conn.close()
        
        # ChromaDB count
        chroma_count = 0
        chroma = self._get_chroma()
        if chroma:
            try:
                chroma_count = chroma.count()
            except Exception:
                pass
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "total_entries": total_entries,
            "active_facts": active_facts,
            "total_links": total_links,
            "total_messages": total_messages,
            "chroma_documents": chroma_count,
            "db_path": self.db_path
        }


# Singleton
_bridge = None

def get_bridge(db_path=None):
    """Get or create ContextBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = ContextBridge(db_path)
    return _bridge


if __name__ == "__main__":
    # Quick test
    bridge = get_bridge()
    
    # Start session
    sid = bridge.start_session("Test Session", tags=["test"])
    print(f"Started session: {sid}")
    
    # Save context
    bridge.save_context(sid, "decision", "Decided to use ChromaDB for semantic search", importance=0.8)
    bridge.save_context(sid, "fact", "CTZ has 14 LLM providers", importance=0.7)
    bridge.save_context(sid, "preference", "User prefers Hinglish communication", importance=0.9)
    
    # Save key fact
    bridge.save_fact("CTZ project renamed from NEXUS to CHAOS TYPE ZERO", category="project")
    bridge.save_fact("GitHub repo: vedchaos/chaos-type-zero", category="project")
    
    # End session
    bridge.end_session(sid, summary="Test session completed successfully")
    
    # Restore context
    result = bridge.restore_context("CTZ project")
    print(f"\nRestored context:")
    print(f"  Facts: {result['facts_count']}")
    print(f"  Entries: {result['entries_count']}")
    print(f"  Sessions: {result['sessions_count']}")
    print(f"  Chars: {result['total_chars']}")
    print(f"\n{result['context'][:500]}...")
    
    # Stats
    print(f"\nStats: {json.dumps(bridge.stats(), indent=2)}")
