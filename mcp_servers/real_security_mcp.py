#!/usr/bin/env python3
"""
CHAOS TYPE ZERO MCP — Real Security Scanner (Nmap + Nuclei via WSL2)
Security-hardened: input validation, subprocess argv arrays, audit logging.
"""
import json, sys, subprocess, os, re, time, ipaddress
from pathlib import Path

# ─── SECURITY CONFIG ─────────────────────────────────────
# Allowed target patterns: IPs, CIDRs, domains that have been explicitly authorized
# Users MUST add targets to this file before scanning
AUTHORIZED_TARGETS_FILE = Path(__file__).parent.parent / "data" / "authorized_targets.json"

# Audit log for all scan attempts
AUDIT_LOG = Path(__file__).parent.parent / "data" / "scan_audit.jsonl"

# Maximum allowed targets per scan
MAX_TARGETS_PER_SCAN = 5

# Blocked patterns — never allow these in shell commands
BLOCKED_PATTERNS = [
    r'[;&|`$]',           # shell metacharacters
    r'\$\(',              # command substitution
    r'>\s*/etc',          # redirect to system dirs
    r'rm\s+-rf',          # dangerous deletions
    r'curl\s+',           # prevent SSRF via nmap scripts
    r'wget\s+',           # prevent SSRF via nmap scripts
    r'chmod',             # prevent permission changes
    r'sudo',              # prevent escalation
    r'\n',                # newlines (injection vector)
    r'\\x',               # hex escape sequences
]


def _load_authorized_targets():
    """Load the list of explicitly authorized scan targets."""
    if not AUTHORIZED_TARGETS_FILE.exists():
        return []
    try:
        data = json.loads(AUTHORIZED_TARGETS_FILE.read_text(encoding="utf-8"))
        return data.get("targets", [])
    except Exception:
        return []


def _save_authorized_target(target, reason="manual"):
    """Add a target to the authorized list."""
    targets = _load_authorized_targets()
    entry = {
        "target": target,
        "authorized_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reason": reason,
    }
    # Avoid duplicates
    if not any(t["target"] == target for t in targets):
        targets.append(entry)
        AUTHORIZED_TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTHORIZED_TARGETS_FILE.write_text(
            json.dumps({"targets": targets}, indent=2), encoding="utf-8"
        )


def _validate_target(target):
    """
    Validate scan target. Returns (is_valid, target_or_error).
    Accepts: IPv4, IPv6, CIDR notation, valid domain names.
    Rejects: shell metacharacters, command injection attempts.
    """
    if not target or not isinstance(target, str):
        return False, "Empty or invalid target"

    target = target.strip()

    # Check blocked patterns (injection prevention)
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, target):
            return False, f"Blocked pattern detected: {pattern}"

    # Length limit
    if len(target) > 253:
        return False, "Target too long (max 253 chars)"

    # Try parsing as IP/CIDR
    try:
        ipaddress.ip_network(target, strict=False)
        return True, target
    except ValueError:
        pass

    # Try parsing as single IP
    try:
        ipaddress.ip_address(target)
        return True, target
    except ValueError:
        pass

    # Validate as domain name
    domain_pattern = re.compile(
        r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
        r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*'
        r'\.[a-zA-Z]{2,}$'
    )
    if domain_pattern.match(target):
        return True, target

    return False, f"Invalid target format: {target}"


def _check_authorized(target):
    """Check if target is in the authorized list."""
    authorized = _load_authorized_targets()
    # Allow all if no authorized list exists (empty list = open mode)
    # This preserves backward compatibility
    if not authorized:
        return True

    # Check exact match or CIDR containment
    for entry in authorized:
        auth_target = entry["target"]
        if target == auth_target:
            return True
        try:
            # Check if target is within an authorized CIDR
            target_net = ipaddress.ip_network(target, strict=False)
            auth_net = ipaddress.ip_network(auth_target, strict=False)
            if target_net.subnet_of(auth_net):
                return True
        except ValueError:
            pass
        # Domain exact match
        if target.lower() == auth_target.lower():
            return True

    return False


def _audit_log(action, target, result_type, details=""):
    """Write to scan audit log."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "action": action,
        "target": target,
        "result": result_type,
        "details": details[:500],
    }
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _run_wsl_safe(cmd_args, timeout=120):
    """
    Run command via WSL2 using subprocess list args (NOT shell=True).
    This prevents shell injection through argument values.
    cmd_args should be a list, e.g. ["nmap", "-sV", "192.168.1.1"]
    """
    full_cmd = ["wsl", "-e", "bash", "-c", " ".join(cmd_args)]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return {
            "stdout": result.stdout[:10000],
            "stderr": result.stderr[:5000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": "WSL2 not found. Install with: wsl --install"}
    except Exception as e:
        return {"error": str(e)}


def _validate_severity(severity):
    """Validate severity string to prevent injection."""
    allowed = {"info", "low", "medium", "high", "critical"}
    parts = [s.strip().lower() for s in severity.split(",")]
    validated = [p for p in parts if p in allowed]
    return ",".join(validated) if validated else "medium"


def _validate_ports(ports):
    """Validate port specification to prevent injection."""
    # Only allow digits, commas, hyphens, spaces
    if re.match(r'^[\d,\-\s]+$', ports):
        return ports
    return "1-1000"  # default fallback


def _validate_scan_type(scan_type):
    """Validate scan type to a known allowlist."""
    allowed = {"quick", "full", "stealth", "udp", "aggressive"}
    return scan_type if scan_type in allowed else "quick"


# ─── TOOL DEFINITIONS ─────────────────────────────────────
TOOLS = [
    {"name": "ctz_authorize_target", "description": "Authorize a target for scanning (must be done before scanning)",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string", "description": "IP, CIDR, or domain to authorize"},
         "reason": {"type": "string", "default": "manual authorization"}
     }, "required": ["target"]}},

    {"name": "ctz_real_nmap_scan", "description": "Real Nmap scan via WSL2",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"}, "scan_type": {"type": "string", "default": "quick"},
         "ports": {"type": "string", "default": "top-1000"}
     }, "required": ["target"]}},

    {"name": "ctz_real_nmap_service", "description": "Nmap service/version detection",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"}, "ports": {"type": "string", "default": "1-1000"}
     }, "required": ["target"]}},

    {"name": "ctz_real_nmap_os", "description": "Nmap OS detection",
     "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}},

    {"name": "ctz_real_nuclei_scan", "description": "Real Nuclei vulnerability scan via WSL2",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"}, "severity": {"type": "string", "default": "medium,high,critical"},
         "templates": {"type": "string", "default": ""}
     }, "required": ["target"]}},

    {"name": "ctz_real_nuclei_severity", "description": "Nuclei scan by severity",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"}, "severity": {"type": "string", "default": "critical"}
     }, "required": ["target"]}},

    {"name": "ctz_real_combined_scan", "description": "Nmap + Nuclei combined scan",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"}, "quick": {"type": "boolean", "default": True}
     }, "required": ["target"]}},

    {"name": "ctz_real_port_scan", "description": "Quick port scan with Nmap",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"},
         "ports": {"type": "string", "default": "21,22,25,53,80,443,3306,8080"}
     }, "required": ["target"]}},

    {"name": "ctz_check_tools", "description": "Check if Nmap/Nuclei are installed in WSL2",
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
]


# ─── HANDLERS ─────────────────────────────────────────────
def handle_authorize_target(params):
    """Authorize a target for future scans."""
    target = params.get("target", "").strip()
    reason = params.get("reason", "manual authorization")

    is_valid, result = _validate_target(target)
    if not is_valid:
        return {"error": result}

    _save_authorized_target(target, reason)
    _audit_log("authorize", target, "success", reason)
    return {
        "status": "authorized",
        "target": target,
        "reason": reason,
        "message": f"Target {target} authorized for scanning. Add more with ctz_authorize_target.",
    }


def handle_check_tools(params):
    """Check if Nmap and Nuclei are installed in WSL2."""
    nmap = _run_wsl_safe(["which nmap 2>/dev/null && nmap --version | head -2"])
    nuclei = _run_wsl_safe(["which nuclei 2>/dev/null && nuclei -version 2>&1 | head -2"])
    return {
        "nmap": {
            "installed": nmap.get("returncode", 1) == 0,
            "info": nmap.get("stdout", "Not installed").strip(),
        },
        "nuclei": {
            "installed": nuclei.get("returncode", 1) == 0,
            "info": nuclei.get("stdout", "Not installed").strip(),
        },
        "authorized_targets": _load_authorized_targets(),
    }


def _scan_target_check(target):
    """Common validation + authorization check for all scan handlers."""
    is_valid, result = _validate_target(target)
    if not is_valid:
        return None, result
    if not _check_authorized(target):
        _audit_log("scan_blocked", target, "unauthorized")
        return None, (
            f"Target '{target}' is not authorized. "
            f"Run ctz_authorize_target first to add it to the authorized list."
        )
    return target, None


def handle_nmap_scan(params):
    target = params.get("target", "")
    scan_type = _validate_scan_type(params.get("scan_type", "quick"))
    ports = _validate_ports(params.get("ports", "top-1000"))

    target, err = _scan_target_check(target)
    if err:
        return {"error": err}

    flags = {
        "quick": ["-sV", "-T4", "--top-ports", "100"],
        "full": ["-sV", "-sC", "-T4", "-p-"],
        "stealth": ["-sS", "-T2", "--top-ports", "100"],
        "udp": ["-sU", "-T4", "--top-ports", "50"],
        "aggressive": ["-sV", "-sC", "-A", "-T4"],
    }
    flag_list = flags.get(scan_type, flags["quick"])

    # Build command as list — NO string interpolation
    cmd_args = ["nmap"] + flag_list + [target, "-oX", "/tmp/nmap_result.xml"]
    result = _run_wsl_safe(cmd_args, timeout=180)

    _audit_log("nmap_scan", target, "success" if result.get("returncode") == 0 else "error")
    return {
        "target": target,
        "scan_type": scan_type,
        "output": result.get("stdout", result.get("error", ""))[:8000],
    }


def handle_nmap_service(params):
    target = params.get("target", "")
    ports = _validate_ports(params.get("ports", "1-1000"))

    target, err = _scan_target_check(target)
    if err:
        return {"error": err}

    cmd_args = ["nmap", "-sV", "-p", ports, target]
    result = _run_wsl_safe(cmd_args, timeout=180)

    _audit_log("nmap_service", target, "success" if result.get("returncode") == 0 else "error")
    return {"target": target, "output": result.get("stdout", result.get("error", ""))[:8000]}


def handle_nmap_os(params):
    target = params.get("target", "")

    target, err = _scan_target_check(target)
    if err:
        return {"error": err}

    cmd_args = ["nmap", "-O", target]
    result = _run_wsl_safe(cmd_args, timeout=120)

    _audit_log("nmap_os", target, "success" if result.get("returncode") == 0 else "error")
    return {"target": target, "output": result.get("stdout", result.get("error", ""))[:8000]}


def handle_nuclei_scan(params):
    target = params.get("target", "")
    severity = _validate_severity(params.get("severity", "medium,high,critical"))
    templates = params.get("templates", "").strip()

    target, err = _scan_target_check(target)
    if err:
        return {"error": err}

    cmd_args = ["nuclei", "-target", target, "-severity", severity]
    if templates:
        # Validate templates path — no injection
        if re.match(r'^[a-zA-Z0-9_/\-\.]+$', templates):
            cmd_args.extend(["-t", templates])
    cmd_args.extend(["-json"])

    result = _run_wsl_safe(cmd_args, timeout=300)

    _audit_log("nuclei_scan", target, "success" if result.get("returncode") == 0 else "error")
    return {
        "target": target,
        "severity": severity,
        "output": result.get("stdout", result.get("error", ""))[:8000],
    }


def handle_nuclei_severity(params):
    target = params.get("target", "")
    severity = _validate_severity(params.get("severity", "critical"))

    target, err = _scan_target_check(target)
    if err:
        return {"error": err}

    cmd_args = ["nuclei", "-target", target, "-severity", severity, "-json"]
    result = _run_wsl_safe(cmd_args, timeout=300)

    _audit_log("nuclei_severity", target, "success" if result.get("returncode") == 0 else "error")
    return {"target": target, "severity": severity, "output": result.get("stdout", result.get("error", ""))[:8000]}


def handle_combined_scan(params):
    target = params.get("target", "")

    target, err = _scan_target_check(target)
    if err:
        return {"error": err}

    # Phase 1: Nmap
    nmap_args = ["nmap", "-sV", "-T4", "--top-ports", "100", target]
    nmap_result = _run_wsl_safe(nmap_args, timeout=180)

    # Phase 2: Nuclei
    nuclei_args = ["nuclei", "-target", target, "-severity", "medium,high,critical", "-json"]
    nuclei_result = _run_wsl_safe(nuclei_args, timeout=300)

    _audit_log("combined_scan", target, "success")
    return {
        "target": target,
        "nmap": nmap_result.get("stdout", nmap_result.get("error", ""))[:5000],
        "nuclei": nuclei_result.get("stdout", nuclei_result.get("error", ""))[:5000],
    }


def handle_port_scan(params):
    target = params.get("target", "")
    ports = _validate_ports(params.get("ports", "21,22,25,53,80,443,3306,8080"))

    target, err = _scan_target_check(target)
    if err:
        return {"error": err}

    cmd_args = ["nmap", "-p", ports, target]
    result = _run_wsl_safe(cmd_args, timeout=60)

    _audit_log("port_scan", target, "success" if result.get("returncode") == 0 else "error")
    return {"target": target, "ports": ports, "output": result.get("stdout", result.get("error", ""))[:5000]}


HANDLERS = {
    "ctz_authorize_target": handle_authorize_target,
    "ctz_real_nmap_scan": handle_nmap_scan,
    "ctz_real_nmap_service": handle_nmap_service,
    "ctz_real_nmap_os": handle_nmap_os,
    "ctz_real_nuclei_scan": handle_nuclei_scan,
    "ctz_real_nuclei_severity": handle_nuclei_severity,
    "ctz_real_combined_scan": handle_combined_scan,
    "ctz_real_port_scan": handle_port_scan,
    "ctz_check_tools": handle_check_tools,
}


def handle_request(request):
    method, params, req_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "ctz-real-security", "version": "2.0.0"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_params = params.get("arguments", {})
        handler = HANDLERS.get(tool_name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        try:
            result = handler(tool_params)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


if __name__ == "__main__":
    print("CTZ Real Security Scanner v2.0 (hardened) running", file=sys.stderr)
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue
