#!/usr/bin/env python3
"""CTZ MCP — HuggingFace"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_INFO = {"name": "huggingface-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "hf_models_search", "description": "Search models on the HuggingFace Hub.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}},
    {"name": "hf_model_info", "description": "Full metadata for a model (model_id like 'bert-base-uncased').", "inputSchema": {"type": "object", "properties": {"model_id": {"type": "string"}}, "required": ["model_id"]}},
    {"name": "hf_inference", "description": "Run inference on a model via the HF Inference API. Text output returned directly; image/audio saved to a temp file.", "inputSchema": {"type": "object", "properties": {"model_id": {"type": "string"}, "inputs": {"type": "string"}, "parameters": {"type": "string"}}, "required": ["model_id", "inputs"]}},
    {"name": "hf_dataset_info", "description": "Metadata for a dataset on the Hub.", "inputSchema": {"type": "object", "properties": {"dataset_id": {"type": "string"}}, "required": ["dataset_id"]}},
]


def _token():
    return os.environ.get("HF_API_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or ""


def _headers():
    h = {"User-Agent": "ctz-hf-mcp/1.0"}
    tok = _token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get_json(url):
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = body[:400] or f"HTTP {exc.code}"
        if exc.code == 404:
            msg = "Not found on HuggingFace Hub"
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}


def hf_models_search(query, limit=10):
    params = {"search": query, "limit": min(int(limit), 100)}
    url = "https://huggingface.co/api/models?" + urllib.parse.urlencode(params)
    data = _get_json(url)
    if isinstance(data, dict) and "error" in data:
        return data
    trimmed = [{"id": m.get("modelId") or m.get("id"), "pipeline_tag": m.get("pipeline_tag"),
                "downloads": m.get("downloads"), "likes": m.get("likes")} for m in data[:int(limit)]]
    return {"count": len(trimmed), "models": trimmed}


def hf_model_info(model_id):
    url = "https://huggingface.co/api/models/" + urllib.parse.quote(model_id, safe="")
    data = _get_json(url)
    if isinstance(data, dict) and "error" in data:
        return data
    siblings = [s.get("rfilename") for s in (data.get("siblings") or [])][:50]
    return {
        "id": data.get("modelId") or data.get("id"),
        "author": data.get("author"),
        "last_modified": data.get("lastModified"),
        "tags": (data.get("tags") or [])[:25],
        "pipeline_tag": data.get("pipeline_tag"),
        "downloads": data.get("downloads"),
        "likes": data.get("likes"),
        "files_sample": siblings,
    }


def hf_inference(model_id, inputs, parameters=None):
    if not _token():
        return {"error": "HF_API_TOKEN environment variable is not set (required for inference)"}
    url = "https://api-inference.huggingface.co/models/" + urllib.parse.quote(model_id, safe="/")
    body = {"inputs": inputs}
    if parameters:
        try:
            body["parameters"] = json.loads(parameters) if isinstance(parameters, str) else parameters
        except json.JSONDecodeError as exc:
            return {"error": f"Invalid parameters JSON: {exc}"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={**_headers(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = detail[:500] or f"HTTP {exc.code}"
        try:
            parsed = json.loads(detail)
            msg = parsed.get("error") or msg
        except json.JSONDecodeError:
            pass
        return {"error": msg, "status": exc.code}
    except Exception as exc:
        return {"error": str(exc)}
    if "json" in ctype:
        try:
            return {"content_type": ctype, "result": json.loads(raw.decode("utf-8", errors="replace"))}
        except json.JSONDecodeError:
            pass
    if ctype.startswith(("image/", "audio/")):
        import tempfile
        suffix = ".png" if "png" in ctype else ".jpg" if "jpeg" in ctype else ".wav" if "audio" in ctype else ".bin"
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="hf_out_")
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        return {"saved_to": path, "content_type": ctype, "bytes": len(raw)}
    return {"content_type": ctype, "text_preview": raw.decode("utf-8", errors="replace")[:8000]}


def hf_dataset_info(dataset_id):
    url = "https://huggingface.co/api/datasets/" + urllib.parse.quote(dataset_id, safe="")
    data = _get_json(url)
    if isinstance(data, dict) and "error" in data:
        return data
    return {
        "id": data.get("id"),
        "author": data.get("author"),
        "last_modified": data.get("lastModified"),
        "tags": (data.get("tags") or [])[:25],
        "downloads": data.get("downloads"),
        "likes": data.get("likes"),
        "features": data.get("cardData", {}).get("dataset_info", {}).get("features"),
    }


HANDLERS = {
    "hf_models_search": hf_models_search,
    "hf_model_info": hf_model_info,
    "hf_inference": hf_inference,
    "hf_dataset_info": hf_dataset_info,
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
