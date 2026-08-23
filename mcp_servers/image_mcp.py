#!/usr/bin/env python3
"""CTZ MCP — Image Processing (Pillow via subprocess)"""
import json
import sys
import subprocess

SERVER_INFO = {"name": "image-mcp", "version": "1.0.0"}
PY = sys.executable or "python"

INFO_SCRIPT = (
    "import json,sys,os\n"
    "from PIL import Image\n"
    "im=Image.open(sys.argv[1])\n"
    "print(json.dumps({'file':os.path.basename(sys.argv[1]),'format':im.format,'mode':im.mode,"
    "'width':im.width,'height':im.height,'animated':getattr(im,'is_animated',False),"
    "'frames':getattr(im,'n_frames',1),'bytes':os.path.getsize(sys.argv[1])}))\n"
)

RESIZE_SCRIPT = (
    "import sys\n"
    "from PIL import Image\n"
    "im=Image.open(sys.argv[1])\n"
    "im=im.resize((int(sys.argv[2]),int(sys.argv[3])))\n"
    "out=sys.argv[4]\n"
    "if out.lower().endswith(('.jpg','.jpeg')) and im.mode in ('RGBA','P','LA'):\n"
    "    im=im.convert('RGB')\n"
    "im.save(out)\n"
    "print('OK',out,im.size)\n"
)

CONVERT_SCRIPT = (
    "import sys\n"
    "from PIL import Image\n"
    "fmt=sys.argv[2].upper()\n"
    "if fmt=='JPG': fmt='JPEG'\n"
    "im=Image.open(sys.argv[1])\n"
    "if fmt in ('JPEG','PDF'): im=im.convert('RGB')\n"
    "im.save(sys.argv[3],format=fmt)\n"
    "print('OK',sys.argv[3],fmt)\n"
)

THUMBNAIL_SCRIPT = (
    "import sys,os,json\n"
    "from PIL import Image\n"
    "s=int(sys.argv[3])\n"
    "im=Image.open(sys.argv[1])\n"
    "orig=(im.width,im.height)\n"
    "im.thumbnail((s,s))\n"
    "out=sys.argv[2]\n"
    "if out.lower().endswith(('.jpg','.jpeg')) and im.mode in ('RGBA','P','LA'):\n"
    "    im=im.convert('RGB')\n"
    "im.save(out)\n"
    "print(json.dumps({'ok':True,'output':out,'original':list(orig),'thumbnail':[im.width,im.height]}))\n"
)

EXIF_SCRIPT = (
    "import sys,json\n"
    "from PIL import Image\n"
    "from PIL.ExifTags import TAGS\n"
    "im=Image.open(sys.argv[1])\n"
    "exif=im.getexif()\n"
    "data={TAGS.get(k,str(k)):str(v)[:300] for k,v in exif.items()}\n"
    "print(json.dumps({'file':sys.argv[1],'exif_fields':len(data),'exif':data}))\n"
)

TOOLS = [
    {"name": "image_info", "description": "Get image format, mode, dimensions and file size.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "image_resize", "description": "Resize an image to exact width x height.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "output": {"type": "string"}}, "required": ["file_path", "width", "height", "output"]}},
    {"name": "image_convert", "description": "Convert image to another format (PNG/JPEG/BMP/PDF/WEBP).", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "format": {"type": "string"}, "output": {"type": "string"}}, "required": ["file_path", "format", "output"]}},
    {"name": "image_thumbnail", "description": "Create a thumbnail preserving aspect ratio (max side = size).", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "output": {"type": "string"}, "size": {"type": "integer", "default": 256}}, "required": ["file_path", "output"]}},
    {"name": "image_exif", "description": "Extract EXIF metadata from an image.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
]


def _run(args, timeout=60):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Timed out"}
    except FileNotFoundError:
        return {"error": "Python/Pillow not available"}


def _json_out(res):
    if isinstance(res, dict) and res.get("returncode") == 0:
        lines = [l for l in res.get("stdout", "").strip().splitlines() if l.strip()]
        if lines:
            try:
                return json.loads(lines[-1])
            except json.JSONDecodeError:
                return {"success": True, "message": lines[-1]}
        return res
    if isinstance(res, dict):
        if res.get("error") == "Python/Pillow not available":
            return {"error": "Python not found on PATH"}
        combined = ((res.get("stderr") or "") + (res.get("stdout") or ""))[:1000]
        hint = {"hint": "Requires Pillow: pip install Pillow"} if ("ModuleNotFoundError" in combined or "PIL" in combined) else {}
        return {**res, **hint}
    return res


def image_info(file_path):
    return _json_out(_run([PY, "-c", INFO_SCRIPT, str(file_path)]))


def image_resize(file_path, width, height, output):
    return _json_out(_run([PY, "-c", RESIZE_SCRIPT, str(file_path), str(int(width)), str(int(height)), str(output)]))


def image_convert(file_path, format, output):
    return _json_out(_run([PY, "-c", CONVERT_SCRIPT, str(file_path), str(format), str(output)]))


def image_thumbnail(file_path, output, size=256):
    return _json_out(_run([PY, "-c", THUMBNAIL_SCRIPT, str(file_path), str(output), str(int(size))]))


def image_exif(file_path):
    return _json_out(_run([PY, "-c", EXIF_SCRIPT, str(file_path)]))


HANDLERS = {
    "image_info": image_info,
    "image_resize": image_resize,
    "image_convert": image_convert,
    "image_thumbnail": image_thumbnail,
    "image_exif": image_exif,
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
