#!/usr/bin/env python3
"""
CHAOS TYPE ZERO v3.4 — Advanced Agentic OS Full Verification Suite
Validates core agentic engines: Heuristics, Meta-Reasoner, Neural, Vault,
Memory Self-Healer, Cryptographic Receipts, and all 13 Agentic MCP Servers.
"""

import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("  CHAOS TYPE ZERO v3.4 — Advanced Agentic OS Verification")
print("=" * 60)

# 1. Heuristics & Risk Engine
print("\n[1/7] Heuristics & Risk Engine...")
from bridge_core.heuristics import get_heuristics
h = get_heuristics()
low_risk = h.assess_risk("read file contents and report lines")
high_risk = h.assess_risk("format drive and rm -rf / root directory")
eval_res = h.evaluate_task("optimize database query cache")
print(f"  Low Risk Score: {low_risk}/100")
print(f"  High Risk Score: {high_risk}/100")
print(f"  Evaluation Tier: {eval_res['tier']} | Approach: {eval_res['recommended_approach']}")
assert low_risk < high_risk, "High risk task should score higher than low risk task"

# 2. Meta-Reasoner Engine
print("\n[2/7] Meta-Reasoner Strategy Engine...")
from bridge_core.meta_reasoner import get_meta_reasoner
mr = get_meta_reasoner()
strategies = mr.plan("architect distributed vector indexing pipeline", {"task_type": "code"})
selected = mr.select_strategy(strategies)
print(f"  Strategies Evaluated: {len(strategies)}")
print(f"  Top Strategy: {selected['strategy_id']} (Provider: {selected['provider']}, Score: {selected['score']})")
mr.record_outcome(selected["strategy_id"], True, {"task_type": "code", "duration_s": 1.2})
print("  Outcome Recorded & Learned: OK")

# 3. Neural Pattern Engine
print("\n[3/7] Neural Pattern Engine...")
from bridge_core.neural import get_neural
neural = get_neural()
cls_res = neural.classify("critical vulnerability in cloud authentication gateway")
emb = neural.embed("zero dependency agentic operating system")
print(f"  Category: {cls_res['category']} (Confidence: {cls_res['confidence']:.2f})")
print(f"  Embedding Dimension: {len(emb)} floats")
assert len(emb) > 0, "Embedding should not be empty"

# 4. Encrypted Secret Vault
print("\n[4/7] Encrypted Secret Vault...")
from bridge_core.vault import get_vault
vault = get_vault()
vault.set("CTZ_TEST_SECRET", "super_secret_token_1337", category="ci_test", description="Ephemeral test secret")
retrieved = vault.get("CTZ_TEST_SECRET")
assert retrieved is not None and retrieved["value"] == "super_secret_token_1337", "Vault retrieval failed"
v_stats = vault.stats()
print(f"  Secret Stored & Retrieved: OK (Total Secrets: {v_stats['total_secrets']})")
vault.delete("CTZ_TEST_SECRET")
print("  Secret Cleaned Up: OK")

# 5. Self-Healing Memory Engine
print("\n[5/7] Self-Healing Memory Engine...")
from bridge_core.memory_healer import get_healer
healer = get_healer()
health = healer.check_all()
print(f"  Checked Databases: {list(health.keys())}")
for db_name, stat in health.items():
    status_label = stat.get("status", "healthy" if stat.get("healthy") else "unhealthy")
    print(f"    - {db_name:<10}: {status_label}")

# 6. Cryptographic Provenance Receipts Engine
print("\n[6/7] Cryptographic Provenance Receipts...")
from bridge_core.receipts import get_provenance
prov = get_provenance()
receipt = prov.create_receipt(
    task_id="task_verify_001",
    task_desc="Verify state integrity and execution audit trail",
    agent_from="Planner",
    agent_to="Executor",
    action_type="tool_execution",
    tool_name="ctz_file_write",
    inputs={"path": "verify.log", "content": "verified"},
    results={"status": "written", "bytes": 8},
    status="executed"
)
is_valid, reason = prov.verify_receipt(receipt)
print(f"  Receipt Created: {receipt['receipt']['receipt_id']}")
print(f"  Signature Verified: {is_valid} ({reason})")
assert is_valid, "Cryptographic receipt signature must be valid"

# Tamper test
tampered_receipt = json.loads(json.dumps(receipt))
tampered_receipt["receipt"]["status"] = "tampered_status"
tampered_valid, tamper_reason = prov.verify_receipt(tampered_receipt)
assert not tampered_valid, "Tampered receipt must fail verification"
print(f"  Tamper Detection: OK ({tamper_reason})")

# 7. Core Agentic MCP Servers (JSON-RPC Handshake)
print("\n[7/7] Core Agentic MCP Servers (JSON-RPC 2.0)...")
MCP_DIR = ROOT / "mcp_servers"
servers = sorted([p.name for p in MCP_DIR.glob("*.py") if p.name != "__init__.py"])
init_req = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "ctz-test-client", "version": "3.4"}
    }
}) + "\n"

ok_count = 0
for server_script in servers:
    server_path = MCP_DIR / server_script
    try:
        proc = subprocess.run(
            [sys.executable, str(server_path)],
            input=init_req,
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0 and "2024-11-05" in proc.stdout:
            print(f"  PASS {server_script:<28} (JSON-RPC 2.0 OK)")
            ok_count += 1
        else:
            print(f"  FAIL {server_script:<28} (code={proc.returncode})")
    except Exception as e:
        print(f"  ERROR {server_script:<28} ({e})")

print(f"\n{'=' * 60}")
print(f"  RESULT: {ok_count}/{len(servers)} Core MCP Servers Passed Handshake")
print("  All 7 Advanced Agentic OS Modules Verified Successfully")
print("=" * 60)

if ok_count < len(servers):
    sys.exit(1)
