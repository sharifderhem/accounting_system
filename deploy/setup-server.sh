#!/usr/bin/env bash
# One-time server setup for دفتر مصنع جوان (Ubuntu 22.04/24.04 or Debian 12). Run as root:
#
#   curl -fsSL https://raw.githubusercontent.com/sharifderhem/accounting_system/main/deploy/setup-server.sh -o setup.sh
#   bash setup.sh
#
# Optional: DOMAIN=ledger.example.com bash setup.sh   (HTTPS certificate is then obtained automatically)
#
# Layout it creates:
#   /opt/joan-ledger/app        code (git checkout, replaced on every deploy)
#   /opt/joan-ledger/venv       Python packages
#   /var/lib/joan-ledger/       THE DATABASE (ledger.db) and pre-deploy snapshots. Deploys never touch it.
#   /etc/joan-ledger.env        settings (owner login, database path)
# Services: joan-ledger (the app), joan-ledger-update.timer (checks GitHub every minute and deploys), caddy (web).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/sharifderhem/accounting_system.git}"
BRANCH="${BRANCH:-main}"
DOMAIN="${DOMAIN:-}"
APP_USER=joan
BASE=/opt/joan-ledger
DATA=/var/lib/joan-ledger
ENV_FILE=/etc/joan-ledger.env

[ "$(id -u)" -eq 0 ] || { echo "Run as root."; exit 1; }
. /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo "This script supports Ubuntu or Debian only (found $ID)."; exit 1 ;; esac

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git python3 python3-venv python3-pip sqlite3 curl ufw debian-keyring debian-archive-keyring apt-transport-https gnupg
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy
fi

echo "==> App user and folders"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$BASE" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$BASE" "$DATA/snapshots"
chown -R "$APP_USER:$APP_USER" "$BASE" "$DATA"
chmod 750 "$DATA"

echo "==> Code and Python packages"
if [ ! -d "$BASE/app/.git" ]; then
  runuser -u "$APP_USER" -- git clone --branch "$BRANCH" "$REPO_URL" "$BASE/app"
fi
[ -d "$BASE/venv" ] || runuser -u "$APP_USER" -- python3 -m venv "$BASE/venv"
runuser -u "$APP_USER" -- "$BASE/venv/bin/pip" install -q --upgrade pip
runuser -u "$APP_USER" -- "$BASE/venv/bin/pip" install -q -r "$BASE/app/backend/requirements.txt"

echo "==> Running the tests once"
( cd "$BASE/app/backend/tests" && runuser -u "$APP_USER" -- env DATABASE_PATH=/tmp/joan-test.db "$BASE/venv/bin/python" -m unittest discover -q -p "test_*.py" )

if [ ! -f "$ENV_FILE" ]; then
  echo "==> Owner account (the only login that exists at first; it creates all others)"
  read -r -p "Owner username: " OWNER_USERNAME </dev/tty
  while :; do
    read -r -s -p "Owner password (8+ characters): " OWNER_PASSWORD </dev/tty; echo
    [ "${#OWNER_PASSWORD}" -ge 8 ] && break
    echo "Too short."
  done
  SECURE=0; [ -n "$DOMAIN" ] && SECURE=1
  # systemd reads this file: quote the password and escape backslashes and double quotes.
  PW_ESC=${OWNER_PASSWORD//\\/\\\\}; PW_ESC=${PW_ESC//\"/\\\"}
  umask 077
  cat > "$ENV_FILE" <<EOF
DATABASE_PATH=$DATA/ledger.db
SECURE_COOKIES=$SECURE
APP_TIMEZONE=Asia/Aden
OWNER_NAME=طه عادل
OWNER_USERNAME=$OWNER_USERNAME
OWNER_PASSWORD="$PW_ESC"
EOF
  chown root:"$APP_USER" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
fi

echo "==> Services"
install -m 755 "$BASE/app/deploy/update.sh" /usr/local/bin/joan-ledger-update

cat > /etc/systemd/system/joan-ledger.service <<EOF
[Unit]
Description=Joan factory ledger
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
EnvironmentFile=$ENV_FILE
WorkingDirectory=$BASE/app/backend
ExecStart=$BASE/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DATA
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/joan-ledger-update.service <<EOF
[Unit]
Description=Deploy the latest commit of the Joan ledger from GitHub
After=network-online.target

[Service]
Type=oneshot
Environment=REPO_BRANCH=$BRANCH
ExecStart=/usr/local/bin/joan-ledger-update
EOF

cat > /etc/systemd/system/joan-ledger-update.timer <<EOF
[Unit]
Description=Check GitHub for a new Joan ledger commit every minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
Unit=joan-ledger-update.service

[Install]
WantedBy=timers.target
EOF

SITE="${DOMAIN:-:80}"
cat > /etc/caddy/Caddyfile <<EOF
$SITE {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
EOF

systemctl daemon-reload
systemctl enable --now joan-ledger
systemctl enable --now joan-ledger-update.timer
systemctl reload caddy || systemctl restart caddy

echo "==> Waiting for the app"
for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:8000/api/health >/dev/null && break
  sleep 1
done
curl -fs http://127.0.0.1:8000/api/health >/dev/null || { echo "App did not start. See: journalctl -u joan-ledger -n 50"; exit 1; }

# The owner account now exists in the database; the password is no longer needed in the file.
sed -i '/^OWNER_PASSWORD=/d' "$ENV_FILE"

echo "==> Firewall (SSH, HTTP, HTTPS)"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

IP=$(curl -fs4 https://ifconfig.me || hostname -I | awk '{print $1}')
echo
echo "Done. Open: ${DOMAIN:+https://$DOMAIN}${DOMAIN:-http://$IP}"
echo "Database:   $DATA/ledger.db  (never touched by deploys; snapshots in $DATA/snapshots)"
echo "Deploy log: journalctl -u joan-ledger-update -f"
