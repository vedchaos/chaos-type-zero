"""
CHAOS TYPE ZERO — Cryptographic Provenance & Portable Signed Receipt Engine
Generates tamper-evident cryptographic receipts for agent handoffs, consequential
tool executions, state modifications, and artifacts leaving CTZ.

Workflow:
  Task Ingestion -> Orchestrator Delegation -> Consequential Tool Execution ->
  State Change Hash -> Signed Portable Receipt -> Downstream / Reviewer / CI
"""

import os
import sys
import json
import time
import hmac
import hashlib
import secrets
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data" / "provenance"
RECEIPTS_DB = DATA_DIR / "receipts.db"
KEY_FILE = DATA_DIR / "agent_signer.key"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _hash_payload(data: Any) -> str:
    """Generate deterministic SHA-256 hash of arbitrary data."""
    if isinstance(data, (dict, list)):
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(data, str):
        serialized = data.encode("utf-8")
    elif isinstance(data, bytes):
        serialized = data
    else:
        serialized = str(data).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class AgentSigner:
    """
    Cryptographic signer for CTZ agents.
    Uses HMAC-SHA256 with an authenticated per-installation secret key.
    Produces portable signatures that can be verified independently.
    """

    def __init__(self, key_path: Optional[Path] = None):
        self.key_path = key_path or KEY_FILE
        self.key, self.key_id = self._load_or_create_key()

    def _load_or_create_key(self) -> Tuple[bytes, str]:
        env_key = os.environ.get("CTZ_SIGNER_KEY")
        if env_key:
            key_bytes = env_key.encode("utf-8")
            key_id = "key-" + hashlib.sha256(key_bytes).hexdigest()[:12]
            return key_bytes, key_id

        if self.key_path.exists():
            try:
                content = json.loads(self.key_path.read_text(encoding="utf-8"))
                key_bytes = bytes.fromhex(content["key_hex"])
                key_id = content["key_id"]
                return key_bytes, key_id
            except Exception:
                pass

        # Generate new 256-bit cryptographically secure key
        key_bytes = secrets.token_bytes(32)
        key_id = "key-" + hashlib.sha256(key_bytes).hexdigest()[:12]
        payload = {
            "key_id": key_id,
            "key_hex": key_bytes.hex(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "algorithm": "HMAC-SHA256",
        }
        self.key_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return key_bytes, key_id

    def sign(self, message: str) -> str:
        """Sign a canonical string message."""
        return hmac.new(self.key, message.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, message: str, signature: str) -> bool:
        """Verify signature against message."""
        expected = self.sign(message)
        return hmac.compare_digest(expected, signature)


class ProvenanceEngine:
    """
    Manages generation, storage, export, and verification of portable receipts.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or RECEIPTS_DB
        self.signer = AgentSigner()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                receipt_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                task_id TEXT NOT NULL,
                agent_from TEXT NOT NULL,
                agent_to TEXT NOT NULL,
                action_type TEXT NOT NULL,
                tool_name TEXT,
                input_hash TEXT NOT NULL,
                result_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                key_id TEXT NOT NULL,
                signature TEXT NOT NULL,
                receipt_json TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_receipts_task ON receipts (task_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts (status)")
        conn.commit()
        conn.close()

    def create_receipt(
        self,
        task_id: str,
        task_desc: str,
        agent_from: str,
        agent_to: str,
        action_type: str,
        tool_name: Optional[str],
        inputs: Any,
        results: Any,
        status: str = "executed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a verifiable portable signed receipt.
        
        status values: 'executed', 'blocked', 'failed', 'exported', 'handed_off'
        """
        now = datetime.now(timezone.utc).isoformat()
        receipt_id = f"rcpt_{int(time.time())}_{secrets.token_hex(6)}"

        input_hash = _hash_payload(inputs)
        result_hash = _hash_payload(results)

        canonical_body = {
            "receipt_id": receipt_id,
            "timestamp": now,
            "task_id": task_id,
            "task_description": task_desc,
            "handoff": {
                "from_agent": agent_from,
                "to_agent": agent_to,
            },
            "action": {
                "action_type": action_type,
                "tool_name": tool_name or "internal",
            },
            "provenance": {
                "input_hash": input_hash,
                "result_hash": result_hash,
            },
            "status": status,
            "signer": {
                "key_id": self.signer.key_id,
                "algorithm": "HMAC-SHA256",
            },
        }
        if metadata:
            canonical_body["metadata"] = metadata

        # Generate canonical message for signature (sorted keys json)
        sign_string = json.dumps(canonical_body, sort_keys=True, separators=(",", ":"))
        signature = self.signer.sign(sign_string)

        full_receipt = {
            "version": "ctz-receipt-v1.0",
            "receipt": canonical_body,
            "signature": signature,
        }

        # Store in ledger
        try:
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            c.execute("""
                INSERT INTO receipts (
                    receipt_id, timestamp, task_id, agent_from, agent_to,
                    action_type, tool_name, input_hash, result_hash,
                    status, key_id, signature, receipt_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt_id, now, task_id, agent_from, agent_to,
                action_type, tool_name, input_hash, result_hash,
                status, self.signer.key_id, signature, json.dumps(full_receipt)
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            sys.stderr.write(f"[WARN] Failed to write receipt to ledger: {e}\n")

        return full_receipt

    def verify_receipt(self, receipt_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verify the cryptographic signature and integrity of a receipt.
        Returns (is_valid: bool, reason: str).
        """
        if "receipt" not in receipt_data or "signature" not in receipt_data:
            return False, "Malformed receipt: missing receipt body or signature"

        canonical_body = receipt_data["receipt"]
        signature = receipt_data["signature"]

        sign_string = json.dumps(canonical_body, sort_keys=True, separators=(",", ":"))
        if not self.signer.verify(sign_string, signature):
            return False, "Signature verification failed: receipt has been tampered with or signed by unknown key"

        return True, "Valid cryptographic receipt (integrity verified)"

    def export_receipt_for_artifact(self, artifact_path: Path, receipt: Dict[str, Any]) -> Path:
        """
        Attach a sidecar receipt file alongside an artifact leaving CTZ.
        Example: report.md -> report.md.ctz-receipt.json
        """
        artifact_path = Path(artifact_path)
        receipt_path = artifact_path.parent / f"{artifact_path.name}.ctz-receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt_path

    def list_recent_receipts(self, limit: int = 20) -> list:
        """Query recent provenance receipts from the ledger."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM receipts ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows


# Singleton instance
_provenance_engine: Optional[ProvenanceEngine] = None

def get_provenance() -> ProvenanceEngine:
    global _provenance_engine
    if _provenance_engine is None:
        _provenance_engine = ProvenanceEngine()
    return _provenance_engine


if __name__ == "__main__":
    # Self-test CLI
    engine = get_provenance()
    print("=== CTZ Provenance & Portable Receipt Engine ===")
    demo = engine.create_receipt(
        task_id="task-demo-001",
        task_desc="Analyze git security and export audit report",
        agent_from="PlannerAgent",
        agent_to="ExecutorAgent",
        action_type="consequential_tool_call",
        tool_name="git_mcp.ctz_git_status",
        inputs={"path": "."},
        results={"status": "clean", "branch": "main"},
        status="executed"
    )
    print("Created Receipt ID:", demo["receipt"]["receipt_id"])
    valid, reason = engine.verify_receipt(demo)
    print("Verification:", valid, "-", reason)
