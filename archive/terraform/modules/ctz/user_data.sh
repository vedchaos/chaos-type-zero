#!/bin/bash
# ============================================================
# CHAOS TYPE ZERO — EC2 User Data
# ============================================================

set -e

echo "🚀 Setting up CHAOS TYPE ZERO v3.2..."

# Update system
apt-get update -y
apt-get upgrade -y

# Install dependencies
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    unzip \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx \
    prometheus \
    node-exporter

# Install Docker
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Create CTZ directory
mkdir -p /opt/ctz
cd /opt/ctz

# Clone repo
git clone https://github.com/vedchaos/chaos-type-zero.git .

# Setup Python venv
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
pip install playwright discord.py prometheus-client
playwright install chromium

# Setup config
cp config.example.json config.json

# Create systemd service
cat > /etc/systemd/system/ctz.service << 'EOF'
[Unit]
Description=CHAOS TYPE ZERO
After=network.target docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/ctz
ExecStart=/opt/ctz/venv/bin/python dashboard/server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Create API service
cat > /etc/systemd/system/ctz-api.service << 'EOF'
[Unit]
Description=CTZ Mobile API
After=network.target ctz.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/ctz
ExecStart=/opt/ctz/venv/bin/python dashboard/mobile_api.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Create Prometheus service
cat > /etc/systemd/system/ctz-prometheus.service << 'EOF'
[Unit]
Description=CTZ Prometheus Metrics
After=network.target ctz.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/ctz
ExecStart=/opt/ctz/venv/bin/python bridge_core/prometheus_metrics.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Enable services
systemctl daemon-reload
systemctl enable ctz ctz-api ctz-prometheus
systemctl start ctz ctz-api ctz-prometheus

# Mount data volume
mkfs.ext4 /dev/nvme1n1
mkdir -p /data
mount /dev/nvme1n1 /data
echo '/dev/nvme1n1 /data ext4 defaults,nofail 0 2' >> /etc/fstab
ln -sf /data /opt/ctz/data

# Setup Nginx
cat > /etc/nginx/sites-available/ctz << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /api {
        proxy_pass http://localhost:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /metrics {
        proxy_pass http://localhost:9090;
    }
}
EOF

ln -sf /etc/nginx/sites-available/ctz /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

# Setup log rotation
cat > /etc/logrotate.d/ctz << 'EOF'
/opt/ctz/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
EOF

echo "✅ CHAOS TYPE ZERO v3.2 installed!"
echo "🌐 Dashboard: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
echo "📡 API: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8081"
echo "📊 Prometheus: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):9090"
