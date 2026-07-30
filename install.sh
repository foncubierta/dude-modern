#!/usr/bin/env bash
# Dude Modern — LXC installer
# Run inside a Debian 12 / Ubuntu 22.04 LXC (privileged)
# Usage: bash install.sh
set -euo pipefail

GN='\033[0;32m'; YW='\033[0;33m'; RD='\033[0;31m'; CL='\033[0m'
msg()  { echo -e "${GN}▶ $*${CL}"; }
warn() { echo -e "${YW}⚠ $*${CL}"; }
err()  { echo -e "${RD}✗ $*${CL}"; exit 1; }

REPO="https://github.com/foncubierta/dude-modern.git"
INSTALL_DIR="/opt/dude-modern"
DATA_DIR="/opt/dude-modern/data"
SERVICE="dude-modern"
PORT=8099

[[ $EUID -ne 0 ]] && err "Run as root"

# ── System packages ────────────────────────────────────────────────────────────
msg "Updating package lists..."
apt-get update -qq

msg "Installing system packages..."
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    nmap iproute2 iputils-ping \
    nginx git curl ca-certificates

# ── Node.js 20 LTS ────────────────────────────────────────────────────────────
msg "Installing Node.js 20..."
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1
    apt-get install -y -qq nodejs
fi
node --version

# ── Clone repo ────────────────────────────────────────────────────────────────
msg "Cloning repository..."
if [[ -d "$INSTALL_DIR" ]]; then
    warn "$INSTALL_DIR already exists — pulling latest changes"
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO" "$INSTALL_DIR"
fi

mkdir -p "$DATA_DIR"

# ── Python venv ───────────────────────────────────────────────────────────────
msg "Installing Python dependencies..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q

# ── Frontend build ────────────────────────────────────────────────────────────
msg "Building frontend..."
cd "$INSTALL_DIR/frontend"
npm install --silent
npm run build
cd /

# ── systemd service ───────────────────────────────────────────────────────────
msg "Creating systemd service..."
cat > /etc/systemd/system/${SERVICE}.service << EOF
[Unit]
Description=Dude Modern Network Dashboard
After=network.target

[Service]
User=root
WorkingDirectory=${INSTALL_DIR}/backend
ExecStart=${INSTALL_DIR}/venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=5
Environment=DATABASE_URL=sqlite:///${DATA_DIR}/dude.db

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

# ── nginx ─────────────────────────────────────────────────────────────────────
msg "Configuring nginx..."
rm -f /etc/nginx/sites-enabled/default
cat > /etc/nginx/sites-available/dude-modern << EOF
server {
    listen 80;
    server_name _;

    root ${INSTALL_DIR}/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 300s;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/dude-modern /etc/nginx/sites-enabled/
nginx -t
systemctl enable nginx
systemctl restart nginx

# ── Done ──────────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"
echo -e "${GN}  Dude Modern installed successfully!${CL}"
echo -e "${GN}  Open: ${YW}http://${IP}${GN}  (or your domain/IP)${CL}"
echo -e "${GN}  Logs: ${YW}journalctl -u dude-modern -f${CL}"
echo -e "${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"
