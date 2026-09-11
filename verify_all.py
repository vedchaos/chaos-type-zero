#!/usr/bin/env python3
"""
CHAOS TYPE ZERO — Master Full-Stack System Verifier
Runs and validates all test suites across the entire operating system.
"""

import sys
import os
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def run_suite(name, script_rel_path):
    print(f"\n{'=' * 65}")
    print(f"  RUNNING: {name} ({script_rel_path})")
    print(f"{'=' * 65}")
    start = time.time()
    res = subprocess.run([sys.executable, str(ROOT / script_rel_path)], cwd=str(ROOT))
    elapsed = round(time.time() - start, 2)
    status = "PASSED" if res.returncode == 0 else "FAILED"
    return name, status, elapsed

def main():
    print("""
=================================================================
       CHAOS TYPE ZERO v3.4 -- MASTER SYSTEM VERIFICATION
=================================================================""")

    suites = [
        ("Core Unit & 10 Core MCP Suite", "tests/run_all_tests.py"),
        ("Automation Engine Suite", "test_automation.py"),
        ("Context Bridge Persistence", "test_context_bridge.py"),
        ("CTZ v1 Core System Pipeline", "test_ctz.py"),
        ("CTZ v2 System Verification", "test_v2.py"),
    ]

    results = []
    for name, path in suites:
        res_name, status, duration = run_suite(name, path)
        results.append((res_name, status, duration))

    print(f"\n\n{'=' * 65}")
    print("  🏆 MASTER AUDIT SUMMARY REPORT")
    print(f"{'=' * 65}")
    all_passed = True
    for name, status, duration in results:
        sym = "✅" if status == "PASSED" else "❌"
        print(f"  {sym} {name:<35} | {status:<8} ({duration}s)")
        if status != "PASSED":
            all_passed = False

    print(f"{'=' * 65}")
    if all_passed:
        print("  🎉 STATUS: 100% OPERATIONAL — ALL SUITES VERIFIED AND PASSING!")
        sys.exit(0)
    else:
        print("  ⚠️ STATUS: ONE OR MORE SUITES FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
