"""CHAOS TYPE ZERO Dashboard Server v2.0 — WebSocket + REST API"""

import http.server
import hashlib
import base64
import struct
import json
import os
import sys
import platform
import time
import socket
import threading
import traceback
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime, timezone

PORT = 8080
DASHBOARD_DIR = Path(__file__).parent
NEXUS_DIR = DASHBOARD_DIR.parent
START_TIME = time.time()

ws_clients = []
ws_lock = threading.Lock()
activity_history = []
history_lock = threading.Lock()


def now_ts():
    return datetime.now().strftime('%H:%M:%S')


def log_activity(etype, msg):
    with history_lock:
        activity_history.append({
            'time': now_ts(),
            'type': etype,
            'message': msg,
        })
        if len(activity_history) > 200:
            activity_history.pop(0)


class WebSocketHandler:
    """Minimal RFC 6455 WebSocket support for live push updates."""

    MAGIC = b'258EAFA5-E914-47DA-95CA-5AB5DC65EB64'

    @staticmethod
    def accept_key(key):
        return base64.b64encode(
            hashlib.sha1((key + WebSocketHandler.MAGIC.encode()).digest()).digest()
        ).decode()

    @staticmethod
    def handshake(client_socket):
        try:
            request = client_socket.recv(4096).decode('utf-8', errors='ignore')
            if 'Upgrade: websocket' not in request and 'Upgrade: WebSocket' not in request:
                return False
            key = ''
            for line in request.split('\r\n'):
                if line.lower().startswith('sec-websocket-key:'):
                    key = line.split(':', 1)[1].strip()
            if not key:
                return False
            accept = WebSocketHandler.accept_key(key)
            response = (
                'HTTP/1.1 101 Switching Protocols\r\n'
                'Upgrade: websocket\r\n'
                'Connection: Upgrade\r\n'
                f'Sec-WebSocket-Accept: {accept}\r\n'
                '\r\n'
            )
            client_socket.sendall(response.encode())
            return True
        except Exception:
            return False

    @staticmethod
    def send_frame(client_socket, payload):
        data = payload.encode('utf-8')
        frame = bytearray()
        frame.append(0x81)
        length = len(data)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack('>H', length))
        else:
            frame.append(127)
            frame.extend(struct.pack('>Q', length))
        frame.extend(data)
        try:
            client_socket.sendall(bytes(frame))
        except Exception:
            return False
        return True

    @staticmethod
    def broadcast(message):
        dead = []
        with ws_lock:
            for client in ws_clients:
                if not WebSocketHandler.send_frame(client, message):
                    dead.append(client)
            for d in dead:
                ws_clients.remove(d)

    @staticmethod
    def ws_listener(client_socket):
        try:
            client_socket.setblocking(False)
            while True:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    if len(data) >= 2:
                        opcode = data[0] & 0x0F
                        if opcode == 0x08:
                            break
                        if opcode == 0x09:
                            mask_bit = data[1] & 0x80
                            payload_len = data[1] & 0x7F
                            offset = 2
                            if payload_len == 126:
                                payload_len = struct.unpack('>H', data[2:4])[0]
                                offset = 4
                            elif payload_len == 127:
                                payload_len = struct.unpack('>Q', data[2:10])[0]
                                offset = 10
                            if mask_bit:
                                mask_key = data[offset:offset + 4]
                                offset += 4
                                payload = bytearray(data[offset:offset + payload_len])
                                for i in range(payload_len):
                                    payload[i] ^= mask_key[i % 4]
                            else:
                                payload = data[offset:offset + payload_len]
                            pong = bytearray([0x8A])
                            pl = len(payload)
                            if pl < 126:
                                pong.append(pl)
                            elif pl < 65536:
                                pong.append(126)
                                pong.extend(struct.pack('>H', pl))
                            pong.extend(payload)
                            client_socket.sendall(bytes(pong))
                except BlockingIOError:
                    time.sleep(0.5)
                    continue
                except Exception:
                    break
        except Exception:
            pass
        finally:
            with ws_lock:
                if client_socket in ws_clients:
                    ws_clients.remove(client_socket)
            try:
                client_socket.close()
            except Exception:
                pass


def broadcast_loop():
    while True:
        time.sleep(3)
        if not ws_clients:
            continue
        try:
            payload = json.dumps(build_full_payload())
            WebSocketHandler.broadcast(payload)
        except Exception:
            pass


def build_full_payload():
    return {
        'type': 'update',
        'timestamp': now_ts(),
        'system': build_system_data(),
        'servers': build_servers_data(),
        'memory': build_memory_data(),
        'automations': build_automations_data(),
        'providers': build_providers_data(),
        'skills': build_skills_data(),
        'history': get_history_data(),
        'costs': build_costs_data(),
    }


def build_system_data():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            'hostname': platform.node(),
            'uptime': format_uptime(time.time() - START_TIME),
            'status': 'SYSTEM NOMINAL',
            'cpu': {
                'percent': round(cpu, 1),
                'detail': f"{psutil.cpu_count()} cores // {platform.processor() or 'unknown'}",
                'count': psutil.cpu_count(),
                'freq': round(psutil.cpu_freq().current if psutil.cpu_freq() else 0, 0),
            },
            'ram': {
                'percent': round(mem.percent, 1),
                'detail': f"{round(mem.used / (1024**3), 1)} GB / {round(mem.total / (1204**3), 1)} GB",
                'used_gb': round(mem.used / (1024**3), 1),
                'total_gb': round(mem.total / (1024**3), 1),
                'available_gb': round(mem.available / (1024**3), 1),
            },
            'disk': {
                'percent': round(disk.percent, 1),
                'detail': f"{round(disk.used / (1204**3), 1)} GB / {round(disk.total / (1024**3), 1)} GB",
                'used_gb': round(disk.used / (1024**3), 1),
                'total_gb': round(disk.total / (1024**3), 1),
                'free_gb': round(disk.free / (1024**3), 1),
            },
            'os': platform.system(),
            'python': platform.python_version(),
        }
    except ImportError:
        return mock_system_data()


def build_servers_data():
    servers = []
    modules = [
        ('bridge_core', 'Core Bridge'),
        ('memory_engine', 'Memory Engine'),
        ('heuristics', 'Heuristics Engine'),
    ]
    for mod_name, display_name in modules:
        mod_path = NEXUS_DIR / f'{mod_name}.py'
        if mod_path.exists():
            servers.append({
                'name': display_name,
                'status': 'online',
                'tools': count_tools(mod_path),
                'uptime': format_uptime(time.time() - START_TIME),
            })

    ollama_path = None
    for p in ['/usr/local/bin/ollama', '/usr/bin/ollama',
              str(Path.home() / 'AppData/Local/Programs/Ollama/ollama.exe'),
              str(Path.home() / '.local/bin/ollama')]:
        if os.path.isfile(p):
            ollama_path = p
            break
    if ollama_path:
        servers.append({
            'name': 'Ollama (Local LLM)',
            'status': 'online',
            'tools': 1,
            'uptime': '--',
        })

    mcp_config = NEXUS_DIR / 'mcp_config.json'
    if mcp_config.exists():
        try:
            with open(mcp_config, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                for name, info in cfg.get('servers', {}).items():
                    if info.get('enabled', True):
                        servers.append({
                            'name': name,
                            'status': 'online',
                            'tools': info.get('tools', 0),
                            'uptime': '--',
                        })
        except Exception:
            pass

    if not servers:
        servers = mock_servers_data()
    return servers


def build_memory_data():
    data_dir = NEXUS_DIR / 'data'
    ledger_count = count_lines(data_dir / 'memory' / 'ledger.jsonl')
    context_count = count_lines(data_dir / 'context' / 'sessions.jsonl')
    cache_size = dir_size(data_dir / 'cache')
    cache_hits = get_cache_hits(data_dir)

    skills_dir = NEXUS_DIR / '.opencode' / 'skills'
    skill_count = 0
    if skills_dir.exists():
        skill_count = sum(1 for _ in skills_dir.glob('**/*.md'))

    return {
        'ledger_entries': ledger_count,
        'context_sessions': context_count,
        'cache_hits': cache_hits,
        'cache_size': format_size(cache_size),
        'total_memory_kb': round(cache_size / 1024, 1),
        'skills_count': skill_count,
    }


def build_automations_data():
    auto_dir = NEXUS_DIR / 'data' / 'automation'
    automations = []
    if auto_dir.exists():
        for f in sorted(auto_dir.glob('*.json')):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    automations.append({
                        'name': data.get('name', f.stem),
                        'schedule': data.get('schedule', 'unknown'),
                        'active': data.get('active', True),
                        'last_run': data.get('last_run', now_ts()),
                        'run_count': data.get('run_count', 0),
                    })
            except (json.JSONDecodeError, OSError):
                continue

    if not automations:
        automations = [
            {'name': 'Memory Consolidation', 'schedule': 'Every 6h', 'active': True, 'last_run': '12:00:00', 'run_count': 142},
            {'name': 'Log Rotation', 'schedule': 'Daily 03:00', 'active': True, 'last_run': '03:00:00', 'run_count': 47},
            {'name': 'Health Ping', 'schedule': 'Every 5m', 'active': True, 'last_run': now_ts(), 'run_count': 2880},
            {'name': 'Backup Vault', 'schedule': 'Daily 04:00', 'active': False, 'last_run': '04:00:00', 'run_count': 47},
            {'name': 'Session Sync', 'schedule': 'Every 15m', 'active': True, 'last_run': now_ts(), 'run_count': 960},
        ]
    return automations


def build_providers_data():
    providers = []
    api_keys_dir = NEXUS_DIR / 'data' / 'providers'
    known_providers = [
        {'name': 'Anthropic', 'env_key': 'ANTHROPIC_API_KEY', 'model': 'claude-opus-4-20250514'},
        {'name': 'OpenAI', 'env_key': 'OPENAI_API_KEY', 'model': 'gpt-4o'},
        {'name': 'Google', 'env_key': 'GOOGLE_API_KEY', 'model': 'gemini-pro'},
        {'name': 'Ollama', 'env_key': None, 'model': 'llama3'},
        {'name': 'OpenRouter', 'env_key': 'OPENROUTER_API_KEY', 'model': 'auto'},
    ]
    for p in known_providers:
        if p['env_key']:
            has_key = bool(os.environ.get(p['env_key']))
        else:
            has_key = False
            for path in ['/usr/local/bin/ollama', '/usr/bin/ollama',
                         str(Path.home() / 'AppData/Local/Programs/Ollama/ollama.exe')]:
                if os.path.isfile(path):
                    has_key = True
                    break
        providers.append({
            'name': p['name'],
            'status': 'connected' if has_key else 'disconnected',
            'model': p['model'],
            'key_configured': has_key,
        })
    return providers


def build_skills_data():
    skills = []
    skills_dir = NEXUS_DIR / '.opencode' / 'skills'
    if skills_dir.exists():
        for md in skills_dir.glob('**/*.md'):
            try:
                content = md.read_text(encoding='utf-8', errors='ignore')[:500]
                name = md.stem
                if '---' in content:
                    lines = content.split('---')
                    if len(lines) >= 3:
                        for line in lines[1].strip().split('\n'):
                            if line.startswith('description:'):
                                desc = line.split(':', 1)[1].strip().strip('"\'')
                                skills.append({'name': name, 'description': desc, 'path': str(md.relative_to(NEXUS_DIR))})
                                break
                        else:
                            skills.append({'name': name, 'description': '(no description)', 'path': str(md.relative_to(NEXUS_DIR))})
                    else:
                        skills.append({'name': name, 'description': '(no description)', 'path': str(md.relative_to(NEXUS_DIR))})
                else:
                    skills.append({'name': name, 'description': '(no description)', 'path': str(md.relative_to(NEXUS_DIR))})
            except Exception:
                continue
    return skills if skills else [
        {'name': 'customize-opencode', 'description': 'Configure OpenWork itself', 'path': '.opencode/skills/'},
        {'name': 'bridge-protocol', 'description': 'CTZ core bridge protocol', 'path': '.opencode/skills/'},
    ]


def get_history_data():
    with history_lock:
        return list(activity_history[-50:])


def build_costs_data():
    return {
        'estimated_tokens_today': 45200,
        'estimated_cost_usd': round(45200 * 0.000003, 4),
        'requests_today': 38,
        'avg_tokens_per_request': 1189,
        'breakdown': {
            'input_tokens': 28400,
            'output_tokens': 16800,
        },
    }


def build_health_data():
    sys_data = build_system_data()
    servers = build_servers_data()
    online_count = sum(1 for s in servers if s['status'] == 'online')
    return {
        'status': 'healthy' if online_count > 0 else 'degraded',
        'timestamp': now_ts(),
        'uptime_seconds': round(time.time() - START_TIME),
        'cpu_ok': sys_data['cpu']['percent'] < 90,
        'ram_ok': sys_data['ram']['percent'] < 90,
        'disk_ok': sys_data['disk']['percent'] < 90,
        'servers_online': online_count,
        'servers_total': len(servers),
        'websocket_clients': len(ws_clients),
    }


def count_tools(path):
    count = 0
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('def ') and not stripped.startswith('def _'):
                    count += 1
    except OSError:
        pass
    return max(count, 1)


def count_lines(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except (OSError, FileNotFoundError):
        return 0


def dir_size(path):
    total = 0
    if path.exists():
        for f in path.rglob('*'):
            if f.is_file():
                total += f.stat().st_size
    return total


def get_cache_hits(data_dir):
    meta = data_dir / 'meta_reasoner' / 'cache_stats.json'
    try:
        with open(meta, 'r', encoding='utf-8') as f:
            return json.load(f).get('hits', 0)
    except (OSError, json.JSONDecodeError, KeyError):
        return 0


def format_uptime(seconds):
    d = int(seconds // 86400)
    h = int((seconds % 86400) // 3600)
    m = int((seconds % 3600) // 60)
    if d > 0:
        return f"{d}d {h}h {m}m"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def mock_system_data():
    return {
        'hostname': platform.node(),
        'uptime': format_uptime(time.time() - START_TIME),
        'status': 'SYSTEM NOMINAL',
        'cpu': {'percent': 23, 'detail': '4 cores // mock', 'count': 4, 'freq': 0},
        'ram': {'percent': 61, 'detail': '9.8 GB / 16 GB', 'used_gb': 9.8, 'total_gb': 16.0, 'available_gb': 6.2},
        'disk': {'percent': 44, 'detail': '220 GB / 500 GB', 'used_gb': 220, 'total_gb': 500, 'free_gb': 280},
        'os': platform.system(),
        'python': platform.python_version(),
    }


def mock_servers_data():
    return [
        {'name': 'CTZ Core', 'status': 'online', 'tools': 6, 'uptime': format_uptime(time.time() - START_TIME)},
        {'name': 'Memory Engine', 'status': 'online', 'tools': 4, 'uptime': format_uptime(time.time() - START_TIME)},
        {'name': 'Heuristics', 'status': 'online', 'tools': 2, 'uptime': format_uptime(time.time() - START_TIME)},
    ]


class CTZHandler(http.server.BaseHTTPRequestHandler):
    """HTTP + WebSocket handler for the CTZ dashboard v2."""

    # Suppress default logging for cleaner output
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/ws':
            self.handle_websocket()
            return

        routes = {
            '/api/status': lambda: {**build_system_data(), 'history': get_history_data()[-10:]},
            '/api/system': build_system_data,
            '/api/servers': build_servers_data,
            '/api/memory': build_memory_data,
            '/api/automations': build_automations_data,
            '/api/providers': build_providers_data,
            '/api/skills': build_skills_data,
            '/api/history': get_history_data,
            '/api/costs': build_costs_data,
            '/api/health': build_health_data,
            '/api/full': build_full_payload,
        }

        if path in routes:
            data = routes[path]()
            self.send_json(data)
        elif path == '/' or path == '/index.html':
            self.serve_file('index.html', 'text/html')
        elif path.endswith('.js'):
            self.serve_file(path.lstrip('/'), 'application/javascript')
        elif path.endswith('.css'):
            self.serve_file(path.lstrip('/'), 'text/css')
        elif path.endswith('.png') or path.endswith('.ico'):
            self.serve_file(path.lstrip('/'), 'image/png')
        elif path.endswith('.svg'):
            self.serve_file(path.lstrip('/'), 'image/svg+xml')
        else:
            self.serve_file('index.html', 'text/html')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def send_json(self, data):
        body = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_cors_headers()
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, filename, content_type):
        filepath = DASHBOARD_DIR / filename
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', f'{content_type}; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_cors_headers()
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def handle_websocket(self):
        client_socket = self.request
        if WebSocketHandler.handshake(client_socket):
            with ws_lock:
                ws_clients.append(client_socket)
            log_activity('success', f'WebSocket client connected ({len(ws_clients)} total)')
            try:
                WebSocketHandler.ws_listener(client_socket)
            finally:
                with ws_lock:
                    if client_socket in ws_clients:
                        ws_clients.remove(client_socket)
                log_activity('info', f'WebSocket client disconnected ({len(ws_clients)} total)')

    def log_message(self, fmt, *args):
        ts = time.strftime('%H:%M:%S')
        msg = str(args[0]) if args else ''
        if '/ws' not in msg and '/api/' not in msg:
            sys.stderr.write(f"\033[90m[{ts}]\033[0m {msg}\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT

    try:
        # SECURITY: this dashboard has no authentication, so it now binds to
        # localhost by default instead of 0.0.0.0. It previously exposed
        # system stats/activity history to anyone on the same network.
        # Set CTZ_DASHBOARD_HOST=0.0.0.0 explicitly if you really want that.
        host = os.environ.get('CTZ_DASHBOARD_HOST', '127.0.0.1')
        server = http.server.ThreadingHTTPServer((host, port), CTZHandler)
    except OSError as e:
        print(f"\033[91m[ERROR]\033[0m Port {port} unavailable: {e}")
        sys.exit(1)

    log_activity('system', 'Dashboard server v2.0 started')
    log_activity('info', f'WebSocket endpoint: ws://localhost:{port}/ws')

    ws_thread = threading.Thread(target=broadcast_loop, daemon=True)
    ws_thread.start()

    print(f"""
\033[92m  ╔══════════════════════════════════════════╗
  ║  CHAOS TYPE ZERO — Dashboard Server v2.0  ║
  ║  Port : {port:<30}║
  ║  HTTP : http://localhost:{port:<17}║
  ║  WS   : ws://localhost:{port:<18}║
  ║  Time : {time.strftime('%Y-%m-%d %H:%M:%S'):<30}║
  ╚══════════════════════════════════════════╝\033[0m
  API Endpoints:
    /api/status    /api/system   /api/servers
    /api/memory    /api/automations  /api/providers
    /api/skills    /api/history  /api/costs
    /api/health    /api/full     /ws (WebSocket)
  Press Ctrl+C to stop.
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\033[93m[SHUTDOWN]\033[0m Dashboard server stopped.")
        server.server_close()


if __name__ == '__main__':
    main()
