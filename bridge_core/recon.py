#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Security Module — Recon & Vulnerability Scanning
Authorized security research tools via WSL2 Kali Linux
"""

import json
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CTZ_ROOT = Path(__file__).parent.parent
RESULTS_DIR = CTZ_ROOT / "data" / "scan_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

import shutil

def _detect_scanner_backend():
    """Detect whether to use WSL2 Kali, native binaries, or none."""
    if shutil.which("wsl"):
        return "wsl"
    elif shutil.which("nmap"):
        return "native"
    return "none"


def sanitize_target(target):
    """Validate and sanitize scan target to prevent command injection.
    
    Allowed: domain names, IPs, CIDR ranges, URLs (no shell metacharacters).
    Raises ValueError if target contains dangerous characters.
    """
    if not target or not isinstance(target, str):
        raise ValueError("Target must be a non-empty string")
    
    target = target.strip()
    
    # Block dangerous shell metacharacters
    dangerous = re.compile(r'[;&|`$(){}!\n\r\\\'"<>#~]')
    if dangerous.search(target):
        raise ValueError(f"Target contains forbidden characters: {target}")
    
    # Validate format: domain, IP, CIDR, or URL
    valid_pattern = re.compile(
        r'^(https?://)?'                          # optional http(s)://
        r'[a-zA-Z0-9]'                            # starts with alphanumeric
        r'[a-zA-Z0-9.\-/]*'                       # allowed chars
        r'(:\d+)?$'                               # optional port
    )
    if not valid_pattern.match(target):
        raise ValueError(f"Invalid target format: {target}")
    
    return target


def run_cmd(cmd, timeout=300):
    """Run a command safely using argument lists and detected backend."""
    try:
        backend = _detect_scanner_backend()
        if backend == "wsl":
            full_cmd = ["wsl", "-d", "kali-linux", "--", "bash", "-c", cmd]
        elif backend == "native":
            if sys.platform == "win32":
                full_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd]
            else:
                full_cmd = ["bash", "-c", cmd]
        else:
            return f"[ERROR] Neither WSL2 Kali nor native security tools (nmap) found in PATH. Install WSL2 Kali via setup_kali.sh or install nmap locally."

        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Command timed out after {timeout}s"
    except Exception as e:
        return f"[ERROR] {str(e)}"


def recon_passive(target):
    """Passive recon — no direct contact"""
    target = sanitize_target(target)
    results = {}
    results["whois"] = run_cmd(f"whois {shlex.quote(target)}", timeout=30)
    results["dig"] = run_cmd(f"dig {shlex.quote(target)} ANY +noall +answer", timeout=30)
    results["nslookup"] = run_cmd(f"nslookup {shlex.quote(target)}", timeout=30)
    results["subdomains"] = run_cmd(f"sublist3r -d {shlex.quote(target)} -silent", timeout=120)
    return results


def recon_active(target, scan_type="quick"):
    """Active recon — direct contact with target"""
    target = sanitize_target(target)
    scan_type = sanitize_target(scan_type)  # reuse validator — scan_type should be simple word

    if scan_type == "quick":
        cmd = f"nmap -sV -sC --top-ports 1000 -oG - {shlex.quote(target)}"
    elif scan_type == "full":
        cmd = f"nmap -sV -sC -p- --min-rate 5000 -oG - {shlex.quote(target)}"
    elif scan_type == "stealth":
        cmd = f"nmap -sS -sV --top-ports 1000 -T2 -oG - {shlex.quote(target)}"
    else:
        cmd = f"nmap -sV --top-ports 100 -oG - {shlex.quote(target)}"

    return run_cmd(cmd, timeout=600)


def scan_web(target, port=80):
    """Web vulnerability scanning"""
    target = sanitize_target(target)
    port = int(port)  # ensure port is an integer

    results = {}
    results["nikto"] = run_cmd(f"nikto -h {shlex.quote(target)} -p {port}", timeout=300)
    results["whatweb"] = run_cmd(f"whatweb {shlex.quote(target)}", timeout=120)
    results["gobuster"] = run_cmd(
        f"gobuster dir -u http://{shlex.quote(target)} -w /usr/share/wordlists/dirb/common.txt -t 20 -q",
        timeout=300
    )
    return results


def scan_vulns(target):
    """Vulnerability scanning with nuclei"""
    target = sanitize_target(target)
    output = run_cmd(f"nuclei -u {shlex.quote(target)} -severity critical,high,medium -json", timeout=600)
    findings = []
    for line in output.strip().split("\n"):
        if line.strip():
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return findings


def full_scan(target, authorized=False):
    """Complete scan workflow"""
    target = sanitize_target(target)
    all_results = {}

    # Phase 1: Passive
    all_results["recon_passive"] = recon_passive(target)

    # Phase 2: Active
    all_results["recon_active"] = recon_active(target, "quick")

    # Phase 3: Web (if HTTP detected)
    if "80" in str(all_results["recon_active"]) or "443" in str(all_results["recon_active"]):
        all_results["web"] = scan_web(target)

    # Phase 4: Vuln (if authorized)
    if authorized:
        all_results["vulns"] = scan_vulns(target)

    # Save results — sanitize filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', target)
    result_file = RESULTS_DIR / f"full_{safe_name}_{timestamp}.json"
    result_file.write_text(json.dumps(all_results, indent=2, default=str))

    return {"file": str(result_file), "results": all_results}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python recon.py <target> [--authorized]")
        sys.exit(1)

    target = sys.argv[1]
    authorized = "--authorized" in sys.argv

    result = full_scan(target, authorized)
    print(f"\n[CHAOS TYPE ZERO] Scan complete. Results: {result['file']}")
