#!/usr/bin/env bash
# Build an offline bundle: every image plus the installer, for a server with no registry access.
#   scripts/make-bundle.sh [version]   ->  finops-agent-<version>.tar.gz
# On the server:  tar xzf finops-agent-*.tar.gz && cd finops-agent-* && sudo ./install.sh --bundle images.tar.gz
set -euo pipefail

VERSION="${1:-0.1.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="ghcr.io/theparsakhezli"
APP="$PREFIX/finops-agent-app:$VERSION"
WEB="$PREFIX/finops-agent-web:$VERSION"
NAME="finops-agent-$VERSION"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

docker build -t "$APP" "$ROOT"
docker build -t "$WEB" "$ROOT/apps/web"
for image in postgres:16-alpine redis:7-alpine caddy:2-alpine; do docker pull -q "$image"; done

mkdir -p "$WORK/$NAME/deploy"
cp "$ROOT/install.sh" "$WORK/$NAME/"
cp "$ROOT/deploy/compose.install.yml" "$WORK/$NAME/deploy/"
docker save "$APP" "$WEB" postgres:16-alpine redis:7-alpine caddy:2-alpine | gzip > "$WORK/$NAME/images.tar.gz"
tar -C "$WORK" -czf "$ROOT/$NAME.tar.gz" "$NAME"
echo "Created $ROOT/$NAME.tar.gz"
