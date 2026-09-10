"""Tests for Cryptographic Provenance and Portable Signed Receipts."""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge_core.receipts import get_provenance, AgentSigner, _hash_payload


class TestProvenanceReceipts:
    """Test receipt generation, signature verification, and tamper resistance."""

    def test_signer_init(self):
        signer = AgentSigner()
        assert signer.key is not None
        assert signer.key_id.startswith("key-")

    def test_signature_roundtrip(self):
        signer = AgentSigner()
        msg = "canonical-test-payload-12345"
        sig = signer.sign(msg)
        assert signer.verify(msg, sig) is True
        assert signer.verify("tampered-message", sig) is False

    def test_create_and_verify_receipt(self):
        prov = get_provenance()
        receipt = prov.create_receipt(
            task_id="task-audit-100",
            task_desc="Run security assessment",
            agent_from="Planner",
            agent_to="Executor",
            action_type="tool_execution",
            tool_name="git_mcp.ctz_git_status",
            inputs={"path": "."},
            results={"status": "clean"},
            status="executed"
        )
        assert "receipt" in receipt
        assert "signature" in receipt
        assert receipt["receipt"]["task_id"] == "task-audit-100"

        # Verify receipt
        valid, reason = prov.verify_receipt(receipt)
        assert valid is True
        assert "integrity verified" in reason

    def test_tamper_detection(self):
        prov = get_provenance()
        receipt = prov.create_receipt(
            task_id="task-tamper-test",
            task_desc="Modifying file",
            agent_from="Orchestrator",
            agent_to="Coder",
            action_type="file_write",
            tool_name="file_mcp",
            inputs={"path": "important.txt"},
            results={"bytes": 42},
            status="executed"
        )

        # Tamper with the receipt body
        tampered = json.loads(json.dumps(receipt))
        tampered["receipt"]["status"] = "failed"  # Tamper status

        valid, reason = prov.verify_receipt(tampered)
        assert valid is False
        assert "tampered" in reason.lower()

    def test_receipt_ledger_query(self):
        prov = get_provenance()
        receipts = prov.list_recent_receipts(limit=5)
        assert isinstance(receipts, list)
        assert len(receipts) > 0
