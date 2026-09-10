#!/usr/bin/env python3
"""
CHAOS TYPE ZERO - Unified Zero-Dependency Test Suite Runner
Runs all unit test classes and all 71 MCP server tool definitions.
"""

import sys
import os
import time
import inspect
import importlib
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

def run_unit_tests():
    test_modules = [
        "test_smart_brain",
        "test_memory_3tier",
        "test_heuristics",
        "test_meta_reasoner",
        "test_neural",
        "test_task_classifier",
        "test_dashboard",
        "test_receipts",
    ]

    print("\n" + "=" * 60)
    print("  PART 1: CORE MODULE UNIT TESTS")
    print("=" * 60)

    total = 0
    passed = 0
    failed = 0
    failures = []

    for mod_name in test_modules:
        try:
            mod = importlib.import_module("tests." + mod_name)
        except Exception as e:
            print(f"  [FAIL] Could not import tests.{mod_name}: {e}")
            failed += 1
            failures.append((mod_name, str(e)))
            continue

        for attr_name in dir(mod):
            if attr_name.startswith("Test"):
                cls = getattr(mod, attr_name)
                if not inspect.isclass(cls):
                    continue
                try:
                    inst = cls()
                except Exception as e:
                    print(f"  [FAIL] Could not instantiate {attr_name}: {e}")
                    failed += 1
                    failures.append((f"{mod_name}.{attr_name}", str(e)))
                    continue

                for m_name in dir(inst):
                    if m_name.startswith("test_"):
                        fn = getattr(inst, m_name)
                        if not callable(fn):
                            continue
                        total += 1
                        try:
                            fn()
                            passed += 1
                            print(f"  [PASS] {mod_name}.{attr_name}.{m_name}")
                        except Exception as e:
                            failed += 1
                            failures.append((f"{mod_name}.{attr_name}.{m_name}", str(e)))
                            print(f"  [FAIL] {mod_name}.{attr_name}.{m_name}: {e}")

    return total, passed, failed, failures

def run_mcp_tests():
    print("\n" + "=" * 60)
    print("  PART 2: CORE AGENTIC MCP TOOLS VALIDATION")
    print("=" * 60)
    try:
        from tests import test_all_mcps
        p = len(test_all_mcps.results["passed"])
        f = len(test_all_mcps.results["failed"])
        t = test_all_mcps.total_tools
        return p, f, t
    except Exception as e:
        print(f"  [ERROR] Running MCP tests: {e}")
        return 0, 1, 0

if __name__ == "__main__":
    start_time = time.time()
    print("CHAOS TYPE ZERO -- Autonomous Agentic AI Test Suite")
    u_tot, u_pass, u_fail, u_errs = run_unit_tests()
    m_pass, m_fail, m_tools = run_mcp_tests()
    m_tot = m_pass + m_fail
    elapsed = round(time.time() - start_time, 2)
    grand_tot = u_tot + m_tot
    grand_pass = u_pass + m_pass
    grand_fail = u_fail + m_fail
    print("\n" + "=" * 60)
    print("  FINAL TEST SUMMARY")
    print("=" * 60)
    print(f"  Core Unit Tests:  {u_pass}/{u_tot} passed")
    print(f"  MCP Server Tests: {m_pass}/{m_tot} passed ({m_tools} tools registered)")
    print(f"  Total Tests:      {grand_pass}/{grand_tot} passed in {elapsed}s")
    print("=" * 60)
    if grand_fail > 0:
        print(f"  STATUS: FAILED ({grand_fail} failures)")
        for target, err in u_errs:
            print(f"    - {target}: {err}")
        sys.exit(1)
    else:
        print("  STATUS: ALL TESTS PASSED (100% SUCCESS)")
        sys.exit(0)
