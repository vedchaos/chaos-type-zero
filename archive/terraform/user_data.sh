#!/bin/bash
# ============================================================
# CHAOS TYPE ZERO — EC2 User Data (Auto-setup on boot)
# ============================================================
# Runs automatically on first boot after instance launch
# Sets up: Python, deps, CTZ repo, FastAPI server, systemd
# ============================================================

set -e

# Redirect all output to log file
exec > >(tee /var/log/ctz-setup.log) 2>&1

echo "============================================"
echo " CHAOS TYPE ZERO — EC2 Auto-Setup"
echo " $(date)"
echo "============================================"

# ============================================================
# 1. SYSTEM UPDATE
# ============================================================
echo "[1/8] Updating system..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# ============================================================
# 2. INSTALL DEPENDENCIES
# ============================================================
echo "[2/8] Installing dependencies..."
apt-get install -y \
  python3 \
  python3-pip \
  python3-venv \
  git \
  curl \
  wget \
  htop \
  nginx \
  ufw \
  unzip

# Ensure python3 points to python3
if ! command -v python3 &> /dev/null; then
  apt-get install -y python3.10
fi

echo "Python version: $(python3 --version)"
echo "Pip version: $(pip3 --version)"

# ============================================================
# 3. CREATE CTZ USER
# ============================================================
echo "[3/8] Creating CTZ user..."
if ! id "ctz" &>/dev/null; then
  useradd -m -s /bin/bash ctz
  usermod -aG sudo ctz
  echo "ctz ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ctz
fi

# ============================================================
# 4. CLONE REPO
# ============================================================
echo "[4/8] Cloning CTZ repo..."
CTZ_HOME="/home/ctz/chaos-type-zero"
if [ ! -d "$CTZ_HOME" ]; then
  sudo -u ctz git clone ${github_repo} $CTZ_HOME
else
  sudo -u ctz -C $CTZ_HOME git pull
fi

# ============================================================
# 5. SETUP PYTHON VENV & INSTALL DEPS
# ============================================================
echo "[5/8] Setting up Python environment..."
cd $CTZ_HOME

# Create venv
sudo -u ctz python3 -m venv venv
sudo -u ctz bash -c "source venv/bin/activate && pip install --upgrade pip"

# Install dependencies
if [ -f requirements.txt ]; then
  sudo -u ctz bash -c "source venv/bin/activate && pip install -r requirements.txt"
fi

# Install FastAPI + uvicorn + extras
sudo -u ctz bash -c "source venv/bin/activate && pip install fastapi uvicorn[standard] python-multipart aiofiles websockets python-jose[cryptography] passlib[bcrypt] httpx"

echo "Dependencies installed!"

# ============================================================
# 6. SETUP SYSTEMD SERVICES
# ============================================================
echo "[6/8] Creating systemd services..."

# FastAPI Production Server (port 9000)
cat > /etc/systemd/system/ctz-server.service << 'EOF'
[Unit]
Description=CTZ FastAPI Production Server
After=network.target

[Service]
Type=simple
User=ctz
Group=ctz
WorkingDirectory=/home/ctz/chaos-type-zero
ExecStart=/home/ctz/chaos-type-zero/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 9000 --workers 2
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=CTZ_ENV=production
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Dashboard (port 8080)
cat > /etc/systemd/system/ctz-dashboard.service << 'EOF'
[Unit]
Description=CTZ Cyberpunk Dashboard
After=network.target

[Service]
Type=simple
User=ctz
Group=ctz
WorkingDirectory=/home/ctz/chaos-type-zero
ExecStart=/home/ctz/chaos-type-zero/venv/bin/python dashboard/server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Mobile API (port 8081)
cat > /etc/systemd/system/ctz-mobile-api.service << 'EOF'
[Unit]
Description=CTZ Mobile API Backend
After=network.target

[Service]
Type=simple
User=ctz
Group=ctz
WorkingDirectory=/home/ctz/chaos-type-zero
ExecStart=/home/ctz/chaos-type-zero/venv/bin/python dashboard/mobile_api.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
systemctl daemon-reload
systemctl enable ctz-server ctz-dashboard ctz-mobile-api
systemctl start ctz-server ctz-dashboard ctz-mobile-api

echo "Services started!"
echo "  ctz-server     → port 9000"
echo "  ctz-dashboard  → port 8080"
echo "  ctz-mobile-api → port 8081"

# ============================================================
# 7. SETUP UFW FIREWALL
# ============================================================
echo "[7/8] Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 9000/tcp  # FastAPI
ufw allow 8080/tcp  # Dashboard
ufw allow 8081/tcp  # Mobile API
ufw allow 3000/tcp  # Slack Bot
ufw allow 3001/tcp  # Grafana
ufw allow 9090/tcp  # Prometheus
ufw --force enable

# ============================================================
# 8. SETUP DATA DISK
# ============================================================
echo "[8/8] Setting up data disk..."
DATA_DISK="/dev/xdvf"  # /dev/xvdf or /dev/nvme1n1 depending on instance

# Check if data disk is attached and unformatted
if [ -b "/dev/xvdf" ]; then
  if ! blkid /dev/xvdf | grep -q "ext4"; then
    mkfs.ext4 /dev/xvdf
  fi
  mkdir -p /mnt/data
  mount /dev/xvdf /mnt/data || true
  echo "/dev/xvdf /mnt/data ext4 defaults,nofail 0 2" >> /etc/fstab
  chown ctz:ctz /mnt/data
elif [ -b "/dev/nvme1n1" ]; then
  if ! blkid /dev/nvme1n1 | grep -q "ext4"; then
    mkfs.ext4 /dev/nvme1n1
  fi
  mkdir -p /mnt/data
  mount /dev/nvme1n1 /mnt/data || true
  echo "/dev/nvme1n1 /mnt/data ext4 defaults,nofail 0 2" >> /etc/fstab
  chown ctz:ctz /mnt/data
fi

# ============================================================
# DONE
# ============================================================
echo ""
echo "============================================"
echo " CHAOS TYPE ZERO — Setup Complete!"
echo "============================================"
echo ""
echo " FastAPI Server:    http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):9000"
echo " Swagger Docs:      http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):9000/docs"
echo " Dashboard:         http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
echo " Mobile API:        http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8081"
echo ""
echo " SSH: ssh -i ctz-key.pem ubuntu@$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
echo ""
echo " Logs:"
echo "   journalctl -u ctz-server -f"
echo "   journalctl -u ctz-dashboard -f"
echo "   journalctl -u ctz-mobile-api -f"
echo "============================================"
