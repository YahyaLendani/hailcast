#!/usr/bin/env bash
# One-time setup on a fresh Oracle Cloud Ubuntu VM (run as the ubuntu user):
#   bash setup.sh
# Installs Docker, opens ports 80 and 443 in the VM's own firewall, clones the repo and writes
# deploy/oracle/.env with generated passwords. MTA_API_KEY is left for you to fill in.
set -euo pipefail

REPO=https://github.com/YahyaLendani/hailcast.git
DIR="$HOME/hailcast"

# Leave a running server alone: stop if something already serves the web ports Caddy needs.
busy=$(sudo ss -tlnH '( sport = :80 or sport = :443 )' || true)
if [ -n "$busy" ]; then
  echo "Ports 80/443 are already in use; not changing anything:"; echo "$busy"; exit 1
fi

sudo apt-get update -y
# Keep an existing Docker install (docker-ce from Docker's repo conflicts with Ubuntu's docker.io).
if ! command -v docker >/dev/null; then
  sudo apt-get install -y docker.io docker-compose-v2
elif ! docker compose version >/dev/null 2>&1; then
  echo "Docker is installed but without the compose plugin; install docker-compose-plugin, then rerun."; exit 1
fi
sudo apt-get install -y git iptables-persistent
sudo usermod -aG docker "$USER"

# Oracle's Ubuntu images reject everything but SSH in iptables, on top of the cloud security list.
# Insert the web ports just before that catch-all REJECT rule (its position varies by image).
for port in 80 443; do
  sudo iptables -D INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null || true
  pos=$(sudo iptables -L INPUT -n --line-numbers | awk '$2 == "REJECT" { print $1; exit }')
  sudo iptables -I INPUT "${pos:-1}" -p tcp --dport "$port" -m state --state NEW -j ACCEPT
done
sudo netfilter-persistent save

[ -d "$DIR" ] || git clone "$REPO" "$DIR"

ENV="$DIR/deploy/oracle/.env"
if [ ! -f "$ENV" ]; then
  ip=$(curl -fsS https://api.ipify.org)
  umask 077
  cat > "$ENV" <<EOF
# Secrets for docker compose. Never commit this file.
SITE_ADDRESS=${ip//./-}.sslip.io
POSTGRES_PASSWORD=$(openssl rand -hex 24)
API_KEY=$(openssl rand -hex 24)
MTA_API_KEY=
EOF
fi

echo
echo "Next: put your MTA Bus Time key after MTA_API_KEY= in $ENV, then run:"
echo "  newgrp docker"
echo "  cd $DIR/deploy/oracle && docker compose up -d --build"
