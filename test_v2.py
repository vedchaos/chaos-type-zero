#!/usr/bin/env python3
"""CHAOS TYPE ZERO v2.0 — Full System Verification"""

print("=" * 60)
print("  CHAOS TYPE ZERO v2.0 — Full System Verification")
print("=" * 60)

# 1. Voice
print("\n[1/4] Voice Module...")
from bridge_core.voice import get_voice
v = get_voice()
status = v.get_status()
print(f"  STT: {status['stt']}")
print(f"  TTS: {status['tts']}")
print(f"  Language: {status['language']}")

# Test TTS
print("  Testing TTS...")
result = v.speak("CHAOS TYPE ZERO voice module ready")
print(f"  TTS Result: {result}")

# 2. Vision
print("\n[2/4] Vision Module...")
from bridge_core.vision import get_vision
vi = get_vision()
vstatus = vi.get_status()
print(f"  Tesseract: {vstatus['tesseract']}")
print(f"  Screenshots: {vstatus['screenshots_count']}")

# 3. ML Pipeline
print("\n[3/4] ML Pipeline...")
try:
    from bridge_core.ml_pipeline import get_ml_pipeline
    import numpy as np
    ml = get_ml_pipeline()
    print(f"  Models: {ml.get_status()['total_models']}")

    # Quick train test
    X = np.random.rand(50, 4)
    y = (X[:, 0] + X[:, 1] > 1).astype(int)
    result = ml.train_classifier(X, y, model_type="random_forest")
    print(f"  Train accuracy: {result.get('accuracy', 'N/A')}")
    models_count = len(ml.list_models())
except ImportError as e:
    print(f"  [OPTIONAL] ML Pipeline dependencies not installed ({e}). Skipping live ML training.")
    models_count = 0

# 4. All MCP Servers
print("\n[4/4] MCP Servers...")
import subprocess, sys
servers = [
    ("ctz-brain", "mcp_servers/llm_fallback.py"),
    ("ctz-memory", "mcp_servers/memory_mcp.py"),
    ("ctz-router", "mcp_servers/task_router_mcp.py"),
    ("ctz-security", "mcp_servers/pentest_mcp.py"),
    ("ctz-orchestrator", "mcp_servers/ctz_orchestrator_mcp.py"),
    ("ctz-voice", "mcp_servers/voice_mcp.py"),
    ("ctz-vision", "mcp_servers/vision_mcp.py"),
    ("ctz-ml", "mcp_servers/ml_mcp.py"),
    ("ctz-automation", "mcp_servers/automation_mcp.py"),
]
init_req = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
ok = 0
for name, script in servers:
    try:
        r = subprocess.run([sys.executable, script], input=init_req, capture_output=True, text=True, timeout=5)
        if name in r.stdout:
            print(f"  {name}: OK")
            ok += 1
        else:
            print(f"  {name}: FAIL")
    except Exception as e:
        print(f"  {name}: ERROR - {e}")

print(f"\n{'=' * 60}")
print(f"  RESULT: {ok}/{len(servers)} MCP servers OK")
print(f"  Voice: {status['stt']} / {status['tts']}")
print(f"  Tesseract: {vstatus['tesseract']}")
print(f"  Models trained: {models_count}")
print(f"{'=' * 60}")
