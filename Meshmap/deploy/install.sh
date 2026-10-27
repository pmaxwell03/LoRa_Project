#!/usr/bin/env bash
# One-time setup on a Raspberry Pi (Raspberry Pi OS). Run from the meshmap folder:
#   bash deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"; USER_NAME="$(whoami)"
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
sudo usermod -aG dialout "$USER_NAME"          # permission to open the USB radio
for svc in meshmap-gateway meshmap-web; do
  sed -e "s#/home/pi/meshmap#$DIR#g" -e "s#^User=pi#User=$USER_NAME#" "deploy/$svc.service" \
    | sudo tee "/etc/systemd/system/$svc.service" > /dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now meshmap-gateway meshmap-web
echo "Done. Map: http://$(hostname -I | awk '{print $1}'):8000"
