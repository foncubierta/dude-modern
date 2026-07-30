#!/usr/bin/env bash
# Dude Modern — update to latest version
set -euo pipefail

GN='\033[0;32m'; CL='\033[0m'
msg() { echo -e "${GN}▶ $*${CL}"; }

INSTALL_DIR="/opt/dude-modern"

[[ $EUID -ne 0 ]] && echo "Run as root" && exit 1

msg "Pulling latest code..."
git -C "$INSTALL_DIR" pull

msg "Updating Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q

msg "Rebuilding frontend..."
cd "$INSTALL_DIR/frontend"
npm install --silent
npm run build
cd /

msg "Restarting service..."
systemctl restart dude-modern

echo -e "${GN}✓ Updated successfully!${CL}"
journalctl -u dude-modern -n 10 --no-pager
