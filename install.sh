#!/usr/bin/env bash
# FinOps agent installer. Run on one server; the others are added from the dashboard.
#
#   sudo ./install.sh                         use this server's IP address (browser shows a certificate warning)
#   sudo ./install.sh --domain finops.ir      use a domain with an automatic certificate
#   sudo ./install.sh --bundle images.tar.gz  offline: no container registry needed
#
# Safe on a server that already runs other things: if ports 80 and 443 are taken, it picks a free port and
# changes nothing else. Running it again upgrades and keeps your settings, secrets and data.
set -euo pipefail

VERSION="0.2.0"
INSTALL_DIR="/opt/finops-agent"
IMAGE_PREFIX="ghcr.io/pendarsolutions"
DOMAIN=""
IP=""
HTTPS_PORT=""
HTTP_BIND=""
BUNDLE=""
MIRROR=""
FORCE_BUILD=0
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: sudo ./install.sh [options]

  --domain NAME           Domain pointing at this server (automatic certificate)
  --ip ADDRESS            IP address to serve on (default: detected)
  --port PORT             HTTPS port (default: 443, or a free port if 443 is taken)
  --bundle FILE           Load images from an offline bundle (see scripts/make-bundle.sh)
  --registry-mirror URL   Docker registry mirror, for when Docker Hub isn't reachable
  --build                 Build the application images here from source
  --dir PATH              Install directory (default: $INSTALL_DIR)
  --version VERSION       Application image version (default: $VERSION)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="${2:?--domain needs a value}"; shift 2 ;;
    --ip) IP="${2:?--ip needs a value}"; shift 2 ;;
    --port) HTTPS_PORT="${2:?--port needs a value}"; shift 2 ;;
    --bundle) BUNDLE="${2:?--bundle needs a file}"; shift 2 ;;
    --registry-mirror) MIRROR="${2:?--registry-mirror needs a URL}"; shift 2 ;;
    --build) FORCE_BUILD=1; shift ;;
    --dir) INSTALL_DIR="${2:?--dir needs a path}"; shift 2 ;;
    --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done

[ "$(id -u)" = 0 ] || die "run this as root (sudo ./install.sh)"
[ -z "$BUNDLE" ] || [ -f "$BUNDLE" ] || die "bundle not found: $BUNDLE"
[ -f "$SOURCE_DIR/deploy/compose.install.yml" ] || die "run this from the project folder or an extracted bundle"
if [[ -n "$DOMAIN" && ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then die "invalid domain: $DOMAIN"; fi
if [[ -n "$IP" && ! "$IP" =~ ^[0-9A-Fa-f:.]+$ ]]; then die "invalid IP address: $IP"; fi
if [[ -n "$HTTPS_PORT" && ! "$HTTPS_PORT" =~ ^[0-9]+$ ]]; then die "invalid port: $HTTPS_PORT"; fi

mem_kb="$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || echo 0)"
[ "$mem_kb" -ge 1500000 ] || warn "less than 1.5 GB of memory; the app may run slowly"

install_docker() {
  command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && return 0
  say "Installing Docker"
  if command -v apt-get >/dev/null 2>&1; then
    # the distribution's own packages first: Iranian mirrors usually carry them when docker.com isn't reachable
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq || warn "apt-get update failed"
    apt-get install -y -qq docker.io docker-compose-v2 >/dev/null 2>&1 ||
      apt-get install -y -qq docker.io docker-compose-plugin >/dev/null 2>&1 || true
  fi
  if ! { command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; }; then
    command -v curl >/dev/null 2>&1 || die "install Docker with Compose, then run this again"
    curl -fsSL https://get.docker.com | sh || die "couldn't install Docker. Install it by hand, then run this again"
  fi
  systemctl enable --now docker >/dev/null 2>&1 || true
}

configure_mirror() {
  [ -n "$MIRROR" ] || return 0
  if [ -s /etc/docker/daemon.json ]; then
    warn "/etc/docker/daemon.json already exists, so it wasn't changed. Add \"registry-mirrors\": [\"$MIRROR\"] to it yourself."
    return 0
  fi
  mkdir -p /etc/docker
  printf '{"registry-mirrors": ["%s"]}\n' "$MIRROR" > /etc/docker/daemon.json
  systemctl restart docker >/dev/null 2>&1 || warn "restart Docker to use the mirror"
}

secret() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
fernet_key() { head -c 32 /dev/urandom | base64 | tr '+/' '-_'; }

port_in_use() { ss -ltnH "sport = :$1" 2>/dev/null | grep -q .; }

env_value() { [ -f "$INSTALL_DIR/.env" ] && sed -n "s/^$1=//p" "$INSTALL_DIR/.env" | head -1 || true; }

# An upgrade keeps its ports, which are in use by this app. Otherwise take 80/443 only if nothing else has them.
choose_ports() {
  local saved p
  saved="$(env_value FINOPS_HTTPS_PORT)"
  HTTP_BIND="$(env_value FINOPS_HTTP_BIND)"
  if [ -n "$HTTPS_PORT" ]; then
    if [ "$HTTPS_PORT" != "$saved" ] && port_in_use "$HTTPS_PORT"; then die "port $HTTPS_PORT is already in use"; fi
  elif [ -n "$saved" ]; then
    HTTPS_PORT="$saved"
  elif ! port_in_use 443; then
    HTTPS_PORT=443
  else
    for p in 8443 9443 10443 18443 28443; do
      if ! port_in_use "$p"; then HTTPS_PORT="$p"; break; fi
    done
    [ -n "$HTTPS_PORT" ] || die "no free HTTPS port found; choose one with --port"
    say "Port 443 is in use, so this will use port $HTTPS_PORT and leave the existing service alone"
  fi
  if [ -z "$HTTP_BIND" ]; then
    # port 80 only redirects to HTTPS, so without it the app still works
    if [ "$HTTPS_PORT" = 443 ] && ! port_in_use 80; then HTTP_BIND=80; else HTTP_BIND="127.0.0.1:18080"; fi
  fi
}

url() {
  if [ "$HTTPS_PORT" = 443 ]; then echo "https://$1"; else echo "https://$1:$HTTPS_PORT"; fi
}

site_address() {
  if [ -n "$DOMAIN" ]; then echo "$DOMAIN"; return; fi
  if [ -z "$IP" ]; then IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; fi
  [ -n "$IP" ] || die "couldn't detect this server's IP address; use --ip or --domain"
  echo "$IP"
}

write_env() {
  local site="$1" env_file="$INSTALL_DIR/.env"
  if [ -f "$env_file" ]; then
    say "Keeping the existing settings in $env_file"
    sed -i "s|^FINOPS_APP_IMAGE=.*|FINOPS_APP_IMAGE=$APP_IMAGE|; s|^FINOPS_WEB_IMAGE=.*|FINOPS_WEB_IMAGE=$WEB_IMAGE|" "$env_file"
    sed -i "/^FINOPS_HTTPS_PORT=/d; /^FINOPS_HTTP_BIND=/d" "$env_file"
    printf 'FINOPS_HTTPS_PORT=%s\nFINOPS_HTTP_BIND=%s\n' "$HTTPS_PORT" "$HTTP_BIND" >> "$env_file"
    return
  fi
  ( umask 077
    cat > "$env_file" <<EOF
FINOPS_APP_IMAGE=$APP_IMAGE
FINOPS_WEB_IMAGE=$WEB_IMAGE
POSTGRES_PASSWORD=$(secret)
FINOPS_JWT_SECRET=$(secret)
FINOPS_CREDENTIALS_KEY=$(fernet_key)
FINOPS_CORS_ORIGINS=["$(url "$site")"]
FINOPS_AI_PROVIDER=offline
FINOPS_HTTPS_PORT=$HTTPS_PORT
FINOPS_HTTP_BIND=$HTTP_BIND
EOF
  )
}

write_caddyfile() {
  local site="$1"
  {
    if [ -n "$DOMAIN" ] && [ "$HTTPS_PORT" = 443 ]; then
      echo "$site {"
    else
      # browsers send no hostname when connecting to an IP address, so Caddy must be told which certificate to use.
      # a public certificate needs port 443, so any other port uses Caddy's own.
      printf '{\n  default_sni %s\n}\nhttps://%s:%s {\n  tls internal\n' "$site" "$site" "$HTTPS_PORT"
    fi
    cat <<'EOF'
  encode gzip
  handle /catalog/* {
    uri strip_prefix /catalog
    root * /srv/catalog
    file_server
  }
  handle {
    reverse_proxy web:80
  }
}
EOF
  } > "$INSTALL_DIR/Caddyfile"
}

prepare_images() {
  if [ -n "$BUNDLE" ]; then
    say "Loading images from $BUNDLE"
    gunzip -c "$BUNDLE" | docker load >/dev/null
    return
  fi
  if [ "$FORCE_BUILD" = 0 ] && docker pull -q "$APP_IMAGE" >/dev/null 2>&1 && docker pull -q "$WEB_IMAGE" >/dev/null 2>&1; then
    return
  fi
  if [ ! -f "$SOURCE_DIR/Dockerfile" ]; then
    die "couldn't download the application images. Use --bundle, or --registry-mirror for a mirror that has them."
  fi
  say "Building the application images (this takes a few minutes)"
  docker build -q -t "$APP_IMAGE" "$SOURCE_DIR" >/dev/null
  docker build -q -t "$WEB_IMAGE" "$SOURCE_DIR/apps/web" >/dev/null
}

wait_healthy() {
  say "Starting (the first start takes a minute or two)"
  for _ in $(seq 1 60); do
    if [ "$(docker inspect -f '{{.State.Health.Status}}' finops-agent-api-1 2>/dev/null)" = healthy ]; then return 0; fi
    sleep 5
  done
  docker compose logs --tail 30 api >&2 || true
  die "the app didn't become healthy. Logs are above; see them again with: cd $INSTALL_DIR && docker compose logs"
}

install_docker
configure_mirror

APP_IMAGE="$IMAGE_PREFIX/finops-agent-app:$VERSION"
WEB_IMAGE="$IMAGE_PREFIX/finops-agent-web:$VERSION"
mkdir -p "$INSTALL_DIR"
choose_ports
SITE="$(site_address)"
cp "$SOURCE_DIR/deploy/compose.install.yml" "$INSTALL_DIR/compose.yml"
write_env "$SITE"
write_caddyfile "$SITE"
prepare_images

cd "$INSTALL_DIR"
if ! docker compose up -d --pull missing --quiet-pull; then
  die "couldn't start. If Docker Hub isn't reachable, use --registry-mirror or --bundle."
fi
wait_healthy
# compose doesn't notice a changed Caddyfile, so an upgrade would keep serving the old one
docker compose restart caddy >/dev/null 2>&1 || warn "couldn't restart Caddy; run: cd $INSTALL_DIR && docker compose restart caddy"

cat <<EOF

FinOps agent is running.

  Open:       $(url "$SITE")
  Next:       create the first account there. Sign-up closes after it.
  Add servers from the Servers page.

  Settings:   $INSTALL_DIR/.env  (back this up: it holds the keys that decrypt your data)
  Logs:       cd $INSTALL_DIR && docker compose logs
  Upgrade:    run this installer again
EOF
if [ -z "$DOMAIN" ] || [ "$HTTPS_PORT" != 443 ]; then
  echo
  echo "Your browser will warn about the certificate. Use --domain with port 443 free to avoid that."
fi
if [ "$HTTPS_PORT" != 443 ]; then
  echo "If this server has a firewall, open port $HTTPS_PORT."
fi
