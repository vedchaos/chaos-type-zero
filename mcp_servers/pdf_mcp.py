#!/usr/bin/env python3
"""CTZ MCP — PDF (PyPDF2/pypdf)"""
import json
import os
import sys

try:
    import PyPDF2
except ImportError:
    try:
        import pypdf as PyPDF2
    except ImportError:
        PyPDF2 = None

SERVER_INFO = {"name": "pdf-mcp", "version": "1.0.0"}

TOOLS = [
    {"name": "pdf_extract_text", "description": "Extract text from all pages of a PDF.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "pdf_metadata", "description": "Read PDF metadata and page count.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "pdf_merge", "description": "Merge multiple PDFs into one output file.", "inputSchema": {"type": "object", "properties": {"file_list": {"type": "array", "items": {"type": "string"}}, "output": {"type": "string"}}, "required": ["file_list", "output"]}},
    {"name": "pdf_split", "description": "Split a PDF into single-page files; pages spec like '1-3,5' (default: all pages).", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "pages": {"type": "string"}}, "required": ["file_path"]}},
]


def _need():
    if PyPDF2 is None:
        return {"error": "Neither PyPDF2 nor pypdf is installed. Run: pip install PyPDF2"}
    return None


def _reader(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"No such file: {file_path}")
    return PyPDF2.PdfReader(file_path)


def pdf_extract_text(file_path):
    err = _need()
    if err:
        return err
    try:
        reader = _reader(file_path)
        parts = []
        for i, page in enumerate(reader.pages):
            try:
                parts.append(page.extract_text() or "")
            except Exception as exc:
                parts.append(f"<page {i + 1} extraction error: {exc}>")
        text = "\n".join(parts)
        return {"file": file_path, "pages": len(reader.pages), "chars": len(text), "text": text[:8000]}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def pdf_metadata(file_path):
    err = _need()
    if err:
        return err
    try:
        reader = _reader(file_path)
        meta = reader.metadata
        fields = {}
        if meta:
            try:
                for k, v in dict(meta).items():
                    fields[str(k).lstrip("/")] = str(v)
            except Exception:
                for attr in ("title", "author", "subject", "creator", "producer", "creation_date", "modification_date"):
                    val = getattr(meta, attr, None)
                    if val:
                        fields[attr] = str(val)
        return {"file": file_path, "pages": len(reader.pages), "encrypted": bool(reader.is_encrypted), "metadata": fields}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def pdf_merge(file_list, output):
    err = _need()
    if err:
        return err
    try:
        writer = PyPDF2.PdfWriter()
        merged_pages = 0
        per_file = []
        for path in file_list:
            reader = _reader(path)
            n = len(reader.pages)
            for page in reader.pages:
                writer.add_page(page)
            per_file.append({"file": path, "pages": n})
            merged_pages += n
        with open(output, "wb") as fh:
            writer.write(fh)
        return {"success": True, "inputs": per_file, "total_pages": merged_pages, "output": os.path.abspath(output)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _parse_pages(spec, total):
    if not spec or str(spec).strip().lower() in ("all", "*", ""):
        return list(range(1, total + 1))
    nums = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            nums.extend(range(int(a), int(b) + 1))
        else:
            nums.append(int(part))
    valid = sorted({n for n in nums if 1 <= n <= total})
    if not valid:
        raise ValueError(f"No valid pages in '{spec}' (document has {total} pages)")
    return valid


def pdf_split(file_path, pages=None):
    err = _need()
    if err:
        return err
    try:
        reader = _reader(file_path)
        page_nums = _parse_pages(pages, len(reader.pages))
        base = os.path.splitext(os.path.basename(file_path))[0]
        outdir = os.path.dirname(file_path) or "."
        created = []
        for n in page_nums:
            writer = PyPDF2.PdfWriter()
            writer.add_page(reader.pages[n - 1])
            out_path = os.path.join(outdir, f"{base}_page_{n:04d}.pdf")
            with open(out_path, "wb") as fh:
                writer.write(fh)
            created.append(out_path)
        return {"success": True, "source_pages_total": len(reader.pages), "split_pages": page_nums, "created_files": created}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


HANDLERS = {
    "pdf_extract_text": pdf_extract_text,
    "pdf_metadata": pdf_metadata,
    "pdf_merge": pdf_merge,
    "pdf_split": pdf_split,
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
