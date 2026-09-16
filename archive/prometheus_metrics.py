#!/usr/bin/env python3
"""
CHAOS TYPE ZERO — Prometheus Metrics Server
Exposes /metrics endpoint for Prometheus scraping
"""

import time
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

# ============================================================
# METRICS STORAGE
# ============================================================
class MetricsCollector:
    """Collects and stores CTZ metrics"""

    def __init__(self):
        self.start_time = time.time()
        self.counters = {
            "ctz_requests_total": 0,
            "ctz_mcp_calls_total": 0,
            "ctz_mcp_errors_total": 0,
            "ctz_tasks_completed_total": 0,
            "ctz_tasks_failed_total": 0,
            "ctz_memory_hits_total": 0,
            "ctz_memory_misses_total": 0,
            "ctz_security_scans_total": 0,
            "ctz_llm_calls_total": 0,
            "ctz_llm_tokens_total": 0,
        }
        self.gauges = {
            "ctz_cpu_percent": 0.0,
            "ctz_memory_percent": 0.0,
            "ctz_memory_used_bytes": 0,
            "ctz_memory_total_bytes": 0,
            "ctz_disk_used_bytes": 0,
            "ctz_disk_total_bytes": 0,
            "ctz_uptime_seconds": 0,
            "ctz_mcp_servers_active": 0,
            "ctz_agents_active": 0,
        }
        self.histograms = {
            "ctz_request_duration_seconds": [],
            "ctz_mcp_call_duration_seconds": [],
            "ctz_llm_response_time_seconds": [],
        }
        self.lock = threading.Lock()
        self._start_collector()

    def _start_collector(self):
        """Start background metric collection"""
        def collect():
            while True:
                self._collect_system_metrics()
                time.sleep(5)
        t = threading.Thread(target=collect, daemon=True)
        t.start()

    def _collect_system_metrics(self):
        """Collect system metrics"""
        with self.lock:
            if HAS_PSUTIL and psutil is not None:
                try:
                    self.gauges["ctz_cpu_percent"] = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory()
                    self.gauges["ctz_memory_percent"] = mem.percent
                    self.gauges["ctz_memory_used_bytes"] = mem.used
                    self.gauges["ctz_memory_total_bytes"] = mem.total
                    disk = psutil.disk_usage("/")
                    self.gauges["ctz_disk_used_bytes"] = disk.used
                    self.gauges["ctz_disk_total_bytes"] = disk.total
                except Exception:
                    pass
            self.gauges["ctz_uptime_seconds"] = time.time() - self.start_time

    def inc_counter(self, name, value=1):
        """Increment a counter"""
        with self.lock:
            if name in self.counters:
                self.counters[name] += value

    def set_gauge(self, name, value):
        """Set a gauge value"""
        with self.lock:
            self.gauges[name] = value

    def observe_histogram(self, name, value):
        """Record a histogram observation"""
        with self.lock:
            if name in self.histograms:
                self.histograms[name].append(value)
                # Keep only last 1000 observations
                if len(self.histograms[name]) > 1000:
                    self.histograms[name] = self.histograms[name][-1000:]

    def get_metrics(self):
        """Get all metrics in Prometheus format"""
        lines = []

        # Counters
        for name, value in self.counters.items():
            lines.append(f"# HELP {name} CTZ counter metric")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")

        # Gauges
        for name, value in self.gauges.items():
            lines.append(f"# HELP {name} CTZ gauge metric")
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {value}")

        # Histograms
        for name, values in self.histograms.items():
            if values:
                lines.append(f"# HELP {name} CTZ histogram metric")
                lines.append(f"# TYPE {name} histogram")

                # Calculate buckets
                sorted_vals = sorted(values)
                buckets = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
                cumulative = 0
                for bucket in buckets:
                    count = sum(1 for v in sorted_vals if v <= bucket)
                    cumulative += count
                    lines.append(f'{name}_bucket{{le="{bucket}"}} {cumulative}')
                lines.append(f'{name}_bucket{{le="+Inf"}} {len(values)}')
                lines.append(f'{name}_sum {sum(values):.6f}')
                lines.append(f'{name}_count {len(values)}')

        return "\n".join(lines)


# ============================================================
# GLOBAL METRICS
# ============================================================
metrics = MetricsCollector()


# ============================================================
# HTTP HANDLER
# ============================================================
class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for /metrics endpoint"""

    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(metrics.get_metrics().encode())

        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            health = {
                "status": "healthy",
                "version": "3.2",
                "uptime": time.time() - metrics.start_time,
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(health).encode())

        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """
            <html>
            <head><title>CTZ Prometheus Metrics</title></head>
            <body>
                <h1>CHAOS TYPE ZERO — Prometheus Metrics</h1>
                <p><a href="/metrics">Metrics Endpoint</a></p>
                <p><a href="/health">Health Check</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


# ============================================================
# PUBLIC API
# ============================================================
def inc_counter(name, value=1):
    """Public API to increment counters"""
    metrics.inc_counter(name, value)

def set_gauge(name, value):
    """Public API to set gauges"""
    metrics.set_gauge(name, value)

def observe_histogram(name, value):
    """Public API to observe histograms"""
    metrics.observe_histogram(name, value)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    PORT = int(os.environ.get("PROMETHEUS_PORT", 9090))
    print(f"📊 CTZ Prometheus Metrics running on port {PORT}")
    print(f"📡 Metrics endpoint: http://localhost:{PORT}/metrics")
    print(f"❤️  Health endpoint: http://localhost:{PORT}/health")

    server = HTTPServer(("0.0.0.0", PORT), MetricsHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down metrics server...")
        server.shutdown()
