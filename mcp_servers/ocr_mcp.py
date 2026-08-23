#!/usr/bin/env python3
"""CTZ MCP — OCR (tesseract)"""
import json
import os
import sys
import subprocess
import tempfile

SERVER_INFO = {"name": "ocr-mcp", "version": "1.0.0"}
PY = sys.executable or "python"

CROP_SCRIPT = (
    "import sys\n"
    "from PIL import Image\n"
    "im=Image.open(sys.argv[1])\n"
    "im.crop((int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]))).save(sys.argv[6])\n"
)

TOOLS = [
    {"name": "ocr_extract", "description": "Extract text from an image with tesseract OCR.", "inputSchema": {"type": "object", "properties": {"image_file": {"type": "string"}, "language": {"type": "string", "default": "eng"}}, "required": ["image_file"]}},
    {"name": "ocr_extract_region", "description": "OCR a rectangular region (x, y, width, height in pixels).", "inputSchema": {"type": "object", "properties": {"image_file": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}, "w": {"type": "integer"}, "h": {"type": "integer"}, "language": {"type": "string", "default": "eng"}}, "required": ["image_file", "x", "y", "w", "h"]}},
    {"name": "ocr_supported_languages", "description": "List installed tesseract language packs.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


def _run(args, timeout=120):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Tool not installed"}


def ocr_extract(image_file, language="eng"):
    if not os.path.isfile(image_file):
        return {"error": f"No such file: {image_file}"}
    res = _run(["tesseract", str(image_file), "stdout", "-l", language])
    if res.get("returncode") == 0:
        return {"file": image_file, "language": language, "chars": len(res["stdout"]), "text": res["stdout"]}
    return res


def ocr_extract_region(image_file, x, y, w, h, language="eng"):
    if not os.path.isfile(image_file):
        return {"error": f"No such file: {image_file}"}
    fd, tmp_png = tempfile.mkstemp(suffix=".png", prefix="ocr_region_")
    os.close(fd)
    try:
        crop_res = _run([PY, "-c", CROP_SCRIPT, str(image_file), str(int(x)), str(int(y)),
                         str(int(x) + int(w)), str(int(y) + int(h)), tmp_png], timeout=60)
        if crop_res.get("returncode") != 0:
            combined = ((crop_res.get("stderr") or "") + (crop_res.get("stdout") or ""))[:500]
            hint = {"hint": "Region cropping requires Pillow: pip install Pillow"} if ("PIL" in combined or "ModuleNotFoundError" in combined) else {}
            return {**crop_res, **hint}
        res = _run(["tesseract", tmp_png, "stdout", "-l", language])
        if res.get("returncode") == 0:
            return {"file": image_file, "region": [int(x), int(y), int(w), int(h)],
                    "language": language, "chars": len(res["stdout"]), "text": res["stdout"]}
        return res
    finally:
        try:
            os.remove(tmp_png)
        except OSError:
            pass


def ocr_supported_languages():
    res = _run(["tesseract", "--list-langs"])
    if res.get("returncode") == 0:
        langs = [l.strip() for l in res["stdout"].splitlines()[1:] if l.strip()]
        version = _run(["tesseract", "--version"], timeout=20)
        vline = next((l.strip() for l in version.get("stdout", "").splitlines() if l.strip()), "")
        return {"version": vline, "languages": langs}
    return res


HANDLERS = {
    "ocr_extract": ocr_extract,
    "ocr_extract_region": ocr_extract_region,
    "ocr_supported_languages": ocr_supported_languages,
}


def handle_request(request):
    method = request.get("method", "")
    rid = request.get("id")
    if method.startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            params = request.get("params") or {}
            result = {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name", "")
            args = params.get("arguments") or {}
            fn = HANDLERS.get(name)
            if fn is None:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
            try:
                out = fn(**args)
                is_error = isinstance(out, dict) and "error" in out
            except Exception as exc:
                out = {"error": f"{type(exc).__name__}: {exc}"}
                is_error = True
            result = {"content": [{"type": "text", "text": json.dumps(out, indent=2, default=str)}]}
            if is_error:
                result["isError"] = True
        else:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            print(json.dumps(resp))
            sys.stdout.flush()
