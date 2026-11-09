#!/usr/bin/env bash
# FinOps agent installer. Run it on one server; the others are added from the dashboard.
#
#   curl -fsSL https://github.com/pendarsolutions/FinOps/releases/latest/download/install.sh | sudo bash
#   curl -fsSL .../install.sh | sudo bash -s -- --domain finops.example.ir --yes
#   sudo ./install.sh [options]                  from a clone, or from an extracted offline bundle
#
# It installs Docker if it's missing, puts the app in /opt/finops-agent and the `finops-agent` command in
# /usr/local/bin, then runs `finops-agent setup`: in a terminal that asks a few questions, and with options it asks
# nothing. Running it again upgrades and keeps your settings, secrets and data. All options: --help.
#
# The released install.sh is this file with deploy/ inside it (scripts/make-installer.sh), so it needs nothing else.
# Everything runs from main() at the very end, so a download cut short runs nothing.
set -euo pipefail

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33mWarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# Where the files come from when this runs from a clone or a bundle (empty when it came through a pipe).
SOURCE_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; fi

EMBEDDED=0
# @embedded-files: scripts/make-installer.sh puts deploy/ here for the one-file installer

# deploy_file NAME: one of the files this installs, from inside this installer or from deploy/ next to it
deploy_file() {
  if [ "$EMBEDDED" = 1 ]; then embedded_file "$1"; return; fi
  [ -n "$SOURCE_DIR" ] && [ -f "$SOURCE_DIR/deploy/$1" ] ||
    die "deploy/$1 not found. Run this from the project folder or an extracted bundle, or use the released install.sh"
  cat "$SOURCE_DIR/deploy/$1"
}

usage() {
  cat <<'EOF'
Usage: curl -fsSL .../install.sh | sudo bash -s -- [options]
       sudo ./install.sh [options]

Installer options
  --dir PATH              Install directory (default: /opt/finops-agent)
  --registry-mirror URL   Docker registry mirror, for when Docker Hub or ghcr.io isn't reachable

EOF
  # then everything `finops-agent setup` takes
  deploy_file finops-agent | bash -s -- setup --help | sed 1,2d
}

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
  local mirror="$1" conf="${FINOPS_DOCKER_DAEMON_JSON:-/etc/docker/daemon.json}"
  [ -n "$mirror" ] || return 0
  if [ -s "$conf" ]; then
    warn "$conf already exists, so it wasn't changed. Add \"registry-mirrors\": [\"$mirror\"] to it yourself."
    return 0
  fi
  mkdir -p "$(dirname "$conf")"
  printf '{"registry-mirrors": ["%s"]}\n' "$mirror" > "$conf"
  systemctl restart docker >/dev/null 2>&1 || warn "restart Docker to use the mirror"
}

# Writes a file through a new name, so a script that is running (finops-agent upgrading itself) isn't overwritten.
put() {
  local name="$1" dest="$2" mode="$3" tmp
  tmp="$(mktemp "$dest.XXXXXX")"
  deploy_file "$name" > "$tmp"
  chmod "$mode" "$tmp"
  mv -f "$tmp" "$dest"
}

main() {
  local dir=/opt/finops-agent bin_dir="${FINOPS_BIN_DIR:-/usr/local/bin}" mirror="" args=() source=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir) dir="${2:?--dir needs a path}"; shift 2 ;;
      --registry-mirror) mirror="${2:?--registry-mirror needs a URL}"; shift 2 ;;
      -h | --help) usage; exit 0 ;;
      *) args+=("$1"); shift ;;
    esac
  done
  [ "$(id -u)" = 0 ] || die "run this as root: curl -fsSL .../install.sh | sudo bash, or sudo ./install.sh"
  # from a clone, setup can build the images itself if no registry has them
  if [ -n "$SOURCE_DIR" ] && [ -f "$SOURCE_DIR/Dockerfile" ]; then source=(--source "$SOURCE_DIR"); fi

  install_docker
  configure_mirror "$mirror"
  say "Putting FinOps agent in $dir"
  mkdir -p "$dir" "$bin_dir"
  put compose.install.yml "$dir/compose.yml" 644
  put backup.sh "$dir/backup.sh" 700
  put finops-agent "$dir/finops-agent" 755
  ln -sfn "$dir/finops-agent" "$bin_dir/finops-agent"

  # setup asks its questions on the terminal; when this script came through a pipe, stdin is that pipe
  if [ -t 0 ]; then
    FINOPS_DIR="$dir" exec "$dir/finops-agent" setup ${source[@]+"${source[@]}"} ${args[@]+"${args[@]}"}
  fi
  FINOPS_DIR="$dir" exec "$dir/finops-agent" setup ${source[@]+"${source[@]}"} ${args[@]+"${args[@]}"} </dev/null
}

main "$@"
