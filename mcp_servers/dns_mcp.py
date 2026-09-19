#!/usr/bin/env python3
"""
CHAOS TYPE ZERO - DNS Recon MCP Tool
A-record / DNS resolution via Python socket (no external deps).
Usage: from mcp_servers.dns_mcp import dns_lookup; dns_lookup("google.com")
"""

import socket


def dns_lookup(domain: str = "google.com") -> dict:
    """Resolve A records for the given domain."""
    domain = (domain or "google.com").strip().lower()
    if not domain.startswith(("http://", "https://")):
        domain = domain
    else:
        domain = domain.split("//", 1)[1].split("/", 1)[0]

    try:
        infos = socket.getaddrinfo(domain, None, socket.AF_INET)
        ips = sorted({info[4][0] for info in infos})
        lines = [f"Domain: {domain}", f"A Records ({len(ips)}):"]
        for ip in ips:
            lines.append(f"  - {ip}")
        return {"domain": domain, "ips": ips, "stdout": "\n".join(lines)}
    except socket.gaierror as e:
        return {
            "domain": domain,
            "ips": [],
            "stdout": f"DNS resolution failed for '{domain}': {e}",
            "error": str(e),
        }


if __name__ == "__main__":
    import sys

    dom = sys.argv[1] if len(sys.argv) > 1 else "google.com"
    print(dns_lookup(dom)["stdout"])