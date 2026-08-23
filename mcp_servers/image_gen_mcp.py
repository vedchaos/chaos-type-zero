#!/usr/bin/env python3
"""CHAOS TYPE ZERO MCP — Image Generation Server"""

import json
import os
import sys
import uuid
import hashlib
import base64
import struct
import zlib
import math
import time
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "images"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HF_TOKEN = os.environ.get("HF_TOKEN", os.environ.get("HUGGINGFACE_HUB_TOKEN", ""))

ASCII_CHARS = "@%#*+=-:. "

TOOLS = [
    {"name": "ctz_image_generate", "description": "Generate image from text prompt via HuggingFace Stable Diffusion XL (graceful fallback to ASCII art)", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "width": {"type": "integer", "default": 512}, "height": {"type": "integer", "default": 512}, "filename": {"type": "string", "default": ""}}, "required": ["prompt"]}},
    {"name": "ctz_image_analyze", "description": "Analyze an image description and return structured info", "inputSchema": {"type": "object", "properties": {"image_path": {"type": "string"}, "prompt": {"type": "string", "default": ""}}, "required": ["image_path"]}},
    {"name": "ctz_image_edit", "description": "Edit image (brightness, contrast, crop) using PIL if available", "inputSchema": {"type": "object", "properties": {"image_path": {"type": "string"}, "operation": {"type": "string", "enum": ["brightness", "contrast", "crop", "grayscale", "resize", "rotate", "flip"]}, "value": {"type": "number", "default": 1.0}, "width": {"type": "integer"}, "height": {"type": "integer"}}, "required": ["image_path", "operation"]}},
    {"name": "ctz_image_convert", "description": "Convert image between formats (PNG, BMP, etc.)", "inputSchema": {"type": "object", "properties": {"image_path": {"type": "string"}, "target_format": {"type": "string", "default": "png"}}, "required": ["image_path"]}},
    {"name": "ctz_image_ascii", "description": "Convert text input into ASCII art", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "width": {"type": "integer", "default": 60}}, "required": ["text"]}},
    {"name": "ctz_image_meme", "description": "Generate a meme template with top/bottom text", "inputSchema": {"type": "object", "properties": {"top_text": {"type": "string"}, "bottom_text": {"type": "string"}, "template": {"type": "string", "default": "default"}, "width": {"type": "integer", "default": 400}, "height": {"type": "integer", "default": 400}}, "required": ["top_text", "bottom_text"]}},
    {"name": "ctz_image_gallery", "description": "List all generated images in the gallery", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}}},
]


def _generate_png(width, height, pixels_rgb):
    """Generate a minimal PNG from raw RGB pixel data."""
    def _chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            idx = (y * width + x) * 3
            raw += bytes(pixels_rgb[idx:idx + 3])
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


def _grayscale_to_png(width, height, gray_pixels):
    """Convert grayscale array [0-255] to PNG bytes."""
    rgb = []
    for v in gray_pixels:
        rgb.extend([v, v, v])
    return _generate_png(width, height, rgb)


def _save_png(data, filename):
    path = DATA_DIR / filename
    path.write_bytes(data)
    return str(path)


def _hash_prompt(prompt):
    return hashlib.md5(prompt.encode(), usedforsecurity=False).hexdigest()[:8]


def _text_to_gray_image(text, width):
    """Render text as a 2D array of grayscale pixel values using a simple bitmap font."""
    font = {
        " ": [0b00000]*5, "!": [0b00100,0b00100,0b00100,0b00000,0b00100], '"': [0b01010,0b01010,0b00000,0b00000,0b00000],
        "#": [0b01010,0b11111,0b01010,0b11111,0b01010], "$": [0b00100,0b01111,0b01100,0b00111,0b11110],
        "%": [0b11000,0b11001,0b00010,0b00100,0b01111], "&": [0b01100,0b10010,0b01100,0b10101,0b01010],
        "'": [0b00100,0b00100,0b00000,0b00000,0b00000], "(": [0b00010,0b00100,0b00100,0b00100,0b00010],
        ")": [0b01000,0b00100,0b00100,0b00100,0b01000], "*": [0b00000,0b01010,0b00100,0b01010,0b00000],
        "+": [0b00000,0b00100,0b01110,0b00100,0b00000], ",": [0b00000,0b00000,0b00000,0b00010,0b00100],
        "-": [0b00000,0b00000,0b01110,0b00000,0b00000], ".": [0b00000,0b00000,0b00000,0b00000,0b00100],
        "/": [0b00001,0b00010,0b00100,0b01000,0b10000], "0": [0b01110,0b10001,0b10101,0b10001,0b01110],
        "1": [0b00100,0b01100,0b00100,0b00100,0b01110], "2": [0b01110,0b10001,0b00010,0b00100,0b11111],
        "3": [0b01110,0b10001,0b00110,0b10001,0b01110], "4": [0b00010,0b00110,0b01010,0b11111,0b00010],
        "5": [0b11111,0b10000,0b11110,0b00001,0b11110], "6": [0b01110,0b10000,0b11110,0b10001,0b01110],
        "7": [0b11111,0b00001,0b00010,0b00100,0b00100], "8": [0b01110,0b10001,0b01110,0b10001,0b01110],
        "9": [0b01110,0b10001,0b01111,0b00001,0b01110], ":": [0b00000,0b00100,0b00000,0b00100,0b00000],
        ";": [0b00000,0b00100,0b00000,0b00010,0b00100], "<": [0b00010,0b00100,0b01000,0b00100,0b00010],
        "=": [0b00000,0b01110,0b00000,0b01110,0b00000], ">": [0b01000,0b00100,0b00010,0b00100,0b01000],
        "?": [0b01110,0b10001,0b00010,0b00000,0b00010], "@": [0b01110,0b10001,0b10111,0b10100,0b01110],
        "A": [0b01110,0b10001,0b11111,0b10001,0b10001], "B": [0b11110,0b10001,0b11110,0b10001,0b11110],
        "C": [0b01110,0b10000,0b10000,0b10000,0b01110], "D": [0b11100,0b10010,0b10001,0b10010,0b11100],
        "E": [0b11111,0b10000,0b11110,0b10000,0b11111], "F": [0b11111,0b10000,0b11110,0b10000,0b10000],
        "G": [0b01110,0b10000,0b10111,0b10001,0b01110], "H": [0b10001,0b10001,0b11111,0b10001,0b10001],
        "I": [0b01110,0b00100,0b00100,0b00100,0b01110], "J": [0b00111,0b00010,0b00010,0b10010,0b01100],
        "K": [0b10001,0b10010,0b11100,0b10010,0b10001], "L": [0b10000,0b10000,0b10000,0b10000,0b11111],
        "M": [0b10001,0b11011,0b10101,0b10001,0b10001], "N": [0b10001,0b11001,0b10101,0b10011,0b10001],
        "O": [0b01110,0b10001,0b10001,0b10001,0b01110], "P": [0b11110,0b10001,0b11110,0b10000,0b10000],
        "Q": [0b01110,0b10001,0b10101,0b10010,0b01101], "R": [0b11110,0b10001,0b11110,0b10010,0b10001],
        "S": [0b01110,0b10000,0b01110,0b00001,0b11110], "T": [0b11111,0b00100,0b00100,0b00100,0b00100],
        "U": [0b10001,0b10001,0b10001,0b10001,0b01110], "V": [0b10001,0b10001,0b10001,0b01010,0b00100],
        "W": [0b10001,0b10001,0b10101,0b11011,0b10001], "X": [0b10001,0b01010,0b00100,0b01010,0b10001],
        "Y": [0b10001,0b01010,0b00100,0b00100,0b00100], "Z": [0b11111,0b00001,0b00010,0b01000,0b11111],
        "[": [0b01110,0b00100,0b00100,0b00100,0b01110], "\\": [0b10000,0b01000,0b00100,0b00010,0b00001],
        "]": [0b01110,0b00100,0b00100,0b00100,0b01110], "^": [0b00100,0b01010,0b10001,0b00000,0b00000],
        "_": [0b00000,0b00000,0b00000,0b00000,0b11111], "`": [0b01000,0b00100,0b00000,0b00000,0b00000],
        "a": [0b00000,0b01110,0b00001,0b01111,0b01111], "b": [0b10000,0b11110,0b10001,0b10001,0b11110],
        "c": [0b00000,0b01110,0b10000,0b10000,0b01110], "d": [0b00001,0b01111,0b10001,0b10001,0b01111],
        "e": [0b01110,0b10001,0b11111,0b10000,0b01110], "f": [0b00110,0b01001,0b11100,0b01000,0b01000],
        "g": [0b01111,0b10001,0b01111,0b00001,0b01110], "h": [0b10000,0b11110,0b10001,0b10001,0b10001],
        "i": [0b00100,0b00000,0b00100,0b00100,0b00100], "j": [0b00010,0b00000,0b00010,0b00010,0b01100],
        "k": [0b10000,0b10010,0b11100,0b10010,0b10001], "l": [0b01100,0b00100,0b00100,0b00100,0b01110],
        "m": [0b00000,0b11010,0b10101,0b10001,0b10001], "n": [0b00000,0b11110,0b10001,0b10001,0b10001],
        "o": [0b00000,0b01110,0b10001,0b10001,0b01110], "p": [0b00000,0b11110,0b10001,0b11110,0b10000],
        "q": [0b00000,0b01111,0b10001,0b01111,0b00001], "r": [0b00000,0b01110,0b10000,0b10000,0b10000],
        "s": [0b00000,0b01110,0b01100,0b00110,0b01110], "t": [0b01000,0b11100,0b01000,0b01001,0b00110],
        "u": [0b00000,0b10001,0b10001,0b10001,0b01111], "v": [0b00000,0b10001,0b10001,0b01010,0b00100],
        "w": [0b00000,0b10001,0b10101,0b10101,0b01010], "x": [0b00000,0b10001,0b01010,0b01010,0b10001],
        "y": [0b00000,0b10001,0b01010,0b00100,0b01100], "z": [0b00000,0b11111,0b00010,0b01000,0b11111],
        "{": [0b00110,0b00100,0b11000,0b00100,0b00110], "|": [0b00100,0b00100,0b00100,0b00100,0b00100],
        "}": [0b01100,0b00100,0b00011,0b00100,0b01100], "~": [0b01000,0b10101,0b00010,0b00000,0b00000],
    }
    char_w, char_h = 5, 7
    text = text.upper()
    img_w = min(len(text) * char_w + char_w, width)
    img_h = char_h
    pixels = [0] * (img_w * img_h)
    for ci, ch in enumerate(text):
        glyph = font.get(ch, font.get("?", [0b01110,0b10001,0b00010,0b00100,0b00100]))
        for gy in range(5):
            row = glyph[gy] if gy < len(glyph) else 0
            for gx in range(char_w):
                bit = (row >> (4 - gx)) & 1
                px = ci * char_w + gx
                if px < img_w:
                    pixels[gy * img_w + px] = 255 if bit else 0
        pixels[5 * img_w + ci * char_w] = 0
        pixels[6 * img_w + ci * char_w] = 0
    return img_w, char_h, pixels


def _text_to_ascii_art(text, width=60):
    """Convert text to displayable ASCII art string."""
    img_w, img_h, gray = _text_to_gray_image(text, width)
    lines = []
    for y in range(img_h):
        row = ""
        for x in range(img_w):
            v = gray[y * img_w + x]
            row += ASCII_CHARS[min(v * len(ASCII_CHARS) // 256, len(ASCII_CHARS) - 1)]
        lines.append(row)
    return "\n".join(lines)


def _generate_meme_png(top_text, bottom_text, width, height):
    """Generate a meme image with top/bottom white text on dark bg."""
    bg_r, bg_g, bg_b = 30, 30, 30
    fg_r, fg_g, fg_b = 255, 255, 255
    pixels = [bg_r, bg_g, bg_b] * (width * height)
    top_img_w, top_img_h, top_gray = _text_to_gray_image(top_text, width)
    bot_img_w, bot_img_h, bot_gray = _text_to_gray_image(bottom_text, width)
    top_img_w = min(top_img_w, width)
    bot_img_w = min(bot_img_w, width)

    def _stamp(gray_data, gw, gh, off_x, off_y):
        for gy in range(gh):
            for gx in range(gw):
                v = gray_data[gy * gw + gx]
                if v > 128:
                    px = off_x + gx
                    py = off_y + gy
                    if 0 <= px < width and 0 <= py < height:
                        idx = (py * width + px) * 3
                        pixels[idx] = fg_r
                        pixels[idx + 1] = fg_g
                        pixels[idx + 2] = fg_b

    _stamp(top_gray, top_img_w, top_img_h, (width - top_img_w) // 2, 10)
    _stamp(bot_gray, bot_img_w, bot_img_h, (width - bot_img_w) // 2, height - bot_img_h - 10)
    return _generate_png(width, height, pixels)


def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-image-gen", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            if name == "ctz_image_generate":
                prompt = args["prompt"]
                w, h = args.get("width", 512), args.get("height", 512)
                filename = args.get("filename") or f"gen_{_hash_prompt(prompt)}_{int(time.time())}.png"
                if HF_TOKEN:
                    try:
                        payload = json.dumps({"inputs": prompt}).encode()
                        req = urllib.request.Request(
                            f"https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
                            data=payload,
                            headers={"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
                        )
                        with urllib.request.urlopen(req, timeout=120) as resp:
                            img_data = resp.read()
                            if len(img_data) > 8 and img_data[:4] == b'\x89PNG':
                                path = _save_png(img_data, filename)
                                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"status": "generated", "path": path, "filename": filename, "source": "huggingface_sdxl", "prompt": prompt})}]}}
                    except Exception:
                        pass
                fallback_img = _text_to_gray_image(prompt[:40], w)
                png_data = _grayscale_to_png(fallback_img[0], fallback_img[1], fallback_img[2])
                path = _save_png(png_data, filename)
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"status": "fallback_ascii", "path": path, "filename": filename, "prompt": prompt, "note": "No HF_TOKEN set or API unavailable. Generated text-to-pixel fallback."})}]}}

            elif name == "ctz_image_analyze":
                img_path = args["image_path"]
                p = Path(img_path)
                if not p.exists():
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": f"File not found: {img_path}"})}], "isError": True}}
                stat = p.stat()
                ext = p.suffix.lower()
                info = {"path": str(p), "size_bytes": stat.st_size, "extension": ext, "name": p.name}
                try:
                    with open(p, "rb") as f:
                        header = f.read(32)
                    if header[:4] == b'\x89PNG':
                        info["format"] = "PNG"
                        ihdr = header[16:24]
                        info["width"] = struct.unpack(">I", ihdr[0:4])[0]
                        info["height"] = struct.unpack(">I", ihdr[4:8])[0]
                    elif header[:2] == b'BM':
                        info["format"] = "BMP"
                    else:
                        info["format"] = "unknown"
                except Exception:
                    info["format"] = "unreadable"
                if args.get("prompt"):
                    info["analysis_prompt"] = args["prompt"]
                    info["note"] = "Full AI analysis requires external vision model."
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(info, indent=2)}]}}

            elif name == "ctz_image_edit":
                img_path = args["image_path"]
                op = args["operation"]
                p = Path(img_path)
                if not p.exists():
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": f"File not found: {img_path}"})}], "isError": True}}
                try:
                    from PIL import Image, ImageEnhance, ImageOps
                    img = Image.open(p)
                    if op == "brightness":
                        img = ImageEnhance.Brightness(img).enhance(args.get("value", 1.5))
                    elif op == "contrast":
                        img = ImageEnhance.Contrast(img).enhance(args.get("value", 1.5))
                    elif op == "grayscale":
                        img = ImageOps.grayscale(img)
                    elif op == "resize":
                        img = img.resize((args.get("width", img.width), args.get("height", img.height)))
                    elif op == "rotate":
                        img = img.rotate(args.get("value", 90), expand=True)
                    elif op == "flip":
                        img = ImageOps.flip(img) if args.get("value", 0) >= 0 else ImageOps.mirror(img)
                    elif op == "crop":
                        w, h = img.size
                        cw = args.get("width", w // 2)
                        ch = args.get("height", h // 2)
                        left = max(0, (w - cw) // 2)
                        top = max(0, (h - ch) // 2)
                        img = img.crop((left, top, left + cw, top + ch))
                    out_name = f"edit_{op}_{p.stem}_{int(time.time())}.png"
                    out_path = DATA_DIR / out_name
                    img.save(str(out_path))
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"status": "edited", "operation": op, "path": str(out_path), "filename": out_name})}]}}
                except ImportError:
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": "PIL/Pillow not installed. Install with: pip install Pillow", "operation": op})}], "isError": True}}

            elif name == "ctz_image_convert":
                img_path = args["image_path"]
                target = args.get("target_format", "png").lower()
                p = Path(img_path)
                if not p.exists():
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": f"File not found: {img_path}"})}], "isError": True}}
                try:
                    from PIL import Image
                    img = Image.open(p)
                    out_name = f"conv_{p.stem}_{int(time.time())}.{target}"
                    out_path = DATA_DIR / out_name
                    fmt_map = {"png": "PNG", "bmp": "BMP", "jpg": "JPEG", "jpeg": "JPEG", "gif": "GIF"}
                    img.save(str(out_path), fmt_map.get(target, target.upper()))
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"status": "converted", "path": str(out_path), "filename": out_name, "format": target})}]}}
                except ImportError:
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": "PIL/Pillow not installed. Install with: pip install Pillow"})}], "isError": True}}

            elif name == "ctz_image_ascii":
                text = args["text"]
                w = args.get("width", 60)
                art = _text_to_ascii_art(text, w)
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": art}]}}

            elif name == "ctz_image_meme":
                top = args.get("top_text", "")
                bot = args.get("bottom_text", "")
                w, h = args.get("width", 400), args.get("height", 400)
                filename = f"meme_{_hash_prompt(top+bot)}_{int(time.time())}.png"
                png_data = _generate_meme_png(top, bot, w, h)
                path = _save_png(png_data, filename)
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"status": "generated", "path": path, "filename": filename, "top_text": top, "bottom_text": bot})}]}}

            elif name == "ctz_image_gallery":
                limit = args.get("limit", 20)
                files = sorted(DATA_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
                gallery = []
                for f in files:
                    stat = f.stat()
                    gallery.append({"name": f.name, "path": str(f), "size_bytes": stat.st_size, "modified": stat.st_mtime})
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"count": len(gallery), "images": gallery}, indent=2)}]}}

        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown method"}}


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = handle_request(json.loads(line.strip()))
            if r:
                sys.stdout.write(json.dumps(r) + "\n")
                sys.stdout.flush()
        except: pass
