#!/usr/bin/env python3
"""Test Context Bridge module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from bridge_core.context_bridge import get_bridge
import json

print("=== CTZ Context Bridge Test ===\n")

# Init
bridge = get_bridge()
print("[OK] Bridge initialized")

# Start session
sid = bridge.start_session("Test Session", tags=["test", "v2.3"])
print(f"[OK] Started session: {sid}")

# Save context entries
bridge.save_context(sid, "decision", "Decided to use ChromaDB for semantic search in context bridge", importance=0.8)
bridge.save_context(sid, "fact", "CTZ has 14 LLM providers", importance=0.7)
bridge.save_context(sid, "preference", "User prefers Hinglish communication style", importance=0.9)
bridge.save_context(sid, "task_outcome", "Context bridge module created and tested successfully", importance=0.6)
print("[OK] Saved 4 context entries")

# Save key facts
f1 = bridge.save_fact("CTZ project renamed from NEXUS to CHAOS TYPE ZERO", category="project")
f2 = bridge.save_fact("GitHub repo: vedchaos/chaos-type-zero", category="project")
f3 = bridge.save_fact("Token expires: never (no expiration)", category="config")
print(f"[OK] Saved 3 key facts (IDs: {f1}, {f2}, {f3})")

# Save a message snapshot
bridge.save_message(sid, "user", "Context bridge karo sabse pehle", 0)
bridge.save_message(sid, "assistant", "Chal bhai, Context Bridge banata hoon!", 1)
print("[OK] Saved 2 message snapshots")

# End session
bridge.end_session(sid, summary="Context bridge module built and tested")
print("[OK] Session ended")

# Start another session for linking
sid2 = bridge.start_session("Session 2", tags=["test"])
bridge.link_sessions(sid, sid2, link_type="continuation", reason="Following up on context bridge work")
print(f"[OK] Started session 2: {sid2} (linked to session 1)")

# Restore context
result = bridge.restore_context("CTZ project")
print(f"\n[OK] Context restored:")
print(f"  Facts: {result['facts_count']}")
print(f"  Entries: {result['entries_count']}")
print(f"  Sessions: {result['sessions_count']}")
print(f"  Total chars: {result['total_chars']}")

# Search
entries = bridge.search_context("ChromaDB")
print(f"\n[OK] Search 'ChromaDB': {len(entries)} results")

facts = bridge.search_facts("GitHub")
print(f"[OK] Search facts 'GitHub': {len(facts)} results")

# Stats
stats = bridge.stats()
print(f"\n=== Stats ===")
print(json.dumps(stats, indent=2))

# Cleanup test data
import os
bridge.end_session(sid2, summary="Test session 2")
print("\n[OK] All tests passed!")
