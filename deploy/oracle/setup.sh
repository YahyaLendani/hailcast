#!/usr/bin/env bash
# One-time setup on a fresh Oracle Cloud Ubuntu VM (run as the ubuntu user):
#   bash setup.sh
# Installs Docker, opens ports 80 and 443 in the VM's own firewall, clones the repo and writes
# deploy/oracle/.env with generated passwords. MTA_API_KEY is left for you to fill in.
set -euo pipefail

REPO=https://github.com/YahyaLendani/hailcast.git
DIR="$HOME/hailcast"

sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose-v2 git iptables-persistent
sudo usermod -aG docker "$USER"

# Oracle's Ubuntu images reject everything but SSH in iptables, on top of the cloud security list.
for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 6 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
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
