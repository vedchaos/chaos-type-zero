#!/usr/bin/env python3
"""
============================================================
 CHAOS TYPE ZERO — AWS Deploy Script
============================================================
 One-click deploy CTZ to AWS EC2 (Free Tier)
 
 Prerequisites:
   1. AWS account with free tier
   2. AWS CLI installed + configured
   3. Terraform installed
 
 Usage:
   python deploy.py          # Deploy CTZ
   python deploy.py destroy  # Destroy everything
   python deploy.py status   # Show current status
============================================================
"""

import subprocess
import sys
import os
import json
import time
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
TERRAFORM_DIR = Path(__file__).parent
PROJECT_ROOT = TERRAFORM_DIR.parent

COLORS = {
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "cyan": "\033[96m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

def print_banner():
    print(f"""{COLORS['cyan']}
╔══════════════════════════════════════════════════════════╗
║          CHAOS TYPE ZERO — AWS DEPLOYER                ║
║                    v3.3 Production                      ║
╚══════════════════════════════════════════════════════════╝
{COLORS['reset']}""")

def log(msg, color="green"):
    print(f"  {COLORS[color]}✓{COLORS['reset']} {msg}")

def warn(msg):
    print(f"  {COLORS['yellow']}⚠{COLORS['reset']} {msg}")

def error(msg):
    print(f"  {COLORS['red']}✗{COLORS['reset']} {msg}")

def run(cmd, cwd=None, check=True):
    """Run a shell command and return output."""
    print(f"  {COLORS['cyan']}$ {cmd}{COLORS['reset']}")
    result = subprocess.run(
        cmd, shell=True, cwd=cwd or TERRAFORM_DIR,
        capture_output=True, text=True
    )
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n")[:5]:
            print(f"    {line}")
        if len(result.stdout.strip().split("\n")) > 5:
            print(f"    ... ({len(result.stdout.strip().split(chr(10)))} lines total)")
    if check and result.returncode != 0:
        error(f"Command failed: {cmd}")
        if result.stderr:
            print(f"    {result.stderr.strip()}")
        sys.exit(1)
    return result

def check_prerequisites():
    """Check all required tools are installed."""
    print(f"\n{COLORS['bold']}Step 1: Checking prerequisites...{COLORS['reset']}\n")
    
    tools = {
        "python3": "Python 3",
        "aws": "AWS CLI",
        "terraform": "Terraform",
    }
    
    all_ok = True
    for cmd, name in tools.items():
        result = subprocess.run(
            f"{cmd} --version" if cmd != "terraform" else f"{cmd} version",
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            log(f"{name}: {version}")
        else:
            error(f"{name} NOT FOUND")
            all_ok = False
    
    # Check AWS credentials
    result = subprocess.run(
        "aws sts get-caller-identity",
        shell=True, capture_output=True, text=True
    )
    if result.returncode == 0:
        identity = json.loads(result.stdout)
        log(f"AWS Account: {identity.get('Account', 'unknown')}")
        log(f"AWS User: {identity.get('Arn', 'unknown').split('/')[-1]}")
    else:
        error("AWS credentials not configured!")
        warn("Run: aws configure")
        all_ok = False
    
    if not all_ok:
        print(f"\n{COLORS['red']}Missing prerequisites! Install them first:{COLORS['reset']}")
        print("  AWS CLI:    https://aws.amazon.com/cli/")
        print("  Terraform:  https://www.terraform.io/downloads")
        sys.exit(1)
    
    print()

def deploy():
    """Deploy CTZ to AWS."""
    print(f"{COLORS['bold']}Step 2: Initializing Terraform...{COLORS['reset']}\n")
    run("terraform init", cwd=TERRAFORM_DIR)
    
    print(f"\n{COLORS['bold']}Step 3: Planning deployment...{COLORS['reset']}\n")
    run("terraform plan -out=tfplan", cwd=TERRAFORM_DIR)
    
    print(f"\n{COLORS['bold']}Step 4: Applying deployment...{COLORS['reset']}\n")
    run("terraform apply tfplan", cwd=TERRAFORM_DIR)
    
    print(f"\n{COLORS['bold']}Step 5: Getting outputs...{COLORS['reset']}\n")
    result = run("terraform output -json", cwd=TERRAFORM_DIR)
    
    outputs = json.loads(result.stdout)
    
    # Display results
    print(f"""{COLORS['green']}
╔══════════════════════════════════════════════════════════╗
║              DEPLOYMENT COMPLETE!                       ║
╚══════════════════════════════════════════════════════════╝
{COLORS['reset']}""")
    
    server_ip = outputs.get("instance_public_ip", {}).get("value", "unknown")
    
    print(f"""  {COLORS['bold']}Your CTZ Server is LIVE!{COLORS['reset']}
  
  {COLORS['green']}FastAPI Server:{COLORS['reset']}  http://{server_ip}:9000
  {COLORS['green']}Swagger Docs:{COLORS['reset']}    http://{server_ip}:9000/docs
  {COLORS['green']}Dashboard:{COLORS['reset']}         http://{server_ip}:8080
  {COLORS['green']}Mobile API:{COLORS['reset']}        http://{server_ip}:8081
  
  {COLORS['cyan']}SSH Command:{COLORS['reset']}
    ssh -i terraform/ctz-key.pem ubuntu@{server_ip}
  
  {COLORS['yellow']}Note: Server takes 2-3 minutes to fully start after launch.
  Check: journalctl -u ctz-server -f (via SSH){COLORS['reset']}
""")
    
    # Save connection info
    conn_file = PROJECT_ROOT / "AWS_CONNECTION.md"
    conn_file.write_text(f"""# CTZ AWS Connection Info

## Server Details
- **Public IP**: {server_ip}
- **SSH Key**: `terraform/ctz-key.pem`
- **Region**: us-east-1

## Endpoints
| Service | URL |
|---------|-----|
| FastAPI Server | http://{server_ip}:9000 |
| Swagger Docs | http://{server_ip}:9000/docs |
| Dashboard | http://{server_ip}:8080 |
| Mobile API | http://{server_ip}:8081 |

## SSH
```bash
ssh -i terraform/ctz-key.pem ubuntu@{server_ip}
```

## Service Management
```bash
# Check status
sudo systemctl status ctz-server
sudo systemctl status ctz-dashboard
sudo systemctl status ctz-mobile-api

# Restart
sudo systemctl restart ctz-server

# Logs
journalctl -u ctz-server -f
journalctl -u ctz-dashboard -f
```

## Costs (Free Tier)
- EC2 t3.micro: 750 hrs/month FREE for 12 months
- EBS gp3 30GB: FREE for 12 months
- S3 5GB: FREE for 12 months
- **Total: $0/month for 12 months**

Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
""")
    log(f"Connection info saved to AWS_CONNECTION.md")

def destroy():
    """Destroy all AWS resources."""
    print(f"{COLORS['bold']}Destroying all CTZ AWS resources...{COLORS['reset']}\n")
    
    confirm = input(f"  {COLORS['red']}Are you sure? This will delete everything! (yes/no): {COLORS['reset']}")
    if confirm.lower() != "yes":
        warn("Aborted.")
        return
    
    run("terraform destroy -auto-approve", cwd=TERRAFORM_DIR)
    log("All resources destroyed!")

def status():
    """Show current deployment status."""
    print(f"{COLORS['bold']}Current CTZ AWS Status:{COLORS['reset']}\n")
    run("terraform output", cwd=TERRAFORM_DIR)

def main():
    print_banner()
    
    command = sys.argv[1] if len(sys.argv) > 1 else "deploy"
    
    check_prerequisites()
    
    if command == "deploy":
        deploy()
    elif command == "destroy":
        destroy()
    elif command == "status":
        status()
    else:
        print(f"Usage: python deploy.py [deploy|destroy|status]")
        sys.exit(1)

if __name__ == "__main__":
    main()
