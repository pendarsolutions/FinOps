#!/usr/bin/env bash
# Build an offline bundle: every image plus the installer, for a server with no registry access.
#   scripts/make-bundle.sh [version]   ->  finops-agent-<version>.tar.gz
# On the server:  tar xzf finops-agent-*.tar.gz && cd finops-agent-* && sudo ./install.sh --bundle images.tar.gz
#
# The version and image prefix default to the ones in install.sh. FINOPS_IMAGE_PREFIX overrides the prefix, and
# FINOPS_IMAGE_SOURCE (a repository URL) labels the images so a registry can link them to it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
from_installer() { sed -n "s/^$1=\"\(.*\)\"$/\1/p" "$ROOT/install.sh"; }
VERSION="${1:-$(from_installer VERSION)}"
PREFIX="${FINOPS_IMAGE_PREFIX:-$(from_installer IMAGE_PREFIX)}"
APP="$PREFIX/finops-agent-app:$VERSION"
WEB="$PREFIX/finops-agent-web:$VERSION"
NAME="finops-agent-$VERSION"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

LABELS=()
if [ -n "${FINOPS_IMAGE_SOURCE:-}" ]; then
  LABELS=(--label "org.opencontainers.image.source=$FINOPS_IMAGE_SOURCE" --label "org.opencontainers.image.version=$VERSION")
fi
docker build "${LABELS[@]}" -t "$APP" "$ROOT"
docker build "${LABELS[@]}" -t "$WEB" "$ROOT/apps/web"
for image in postgres:16-alpine redis:7-alpine caddy:2-alpine; do docker pull -q "$image"; done

mkdir -p "$WORK/$NAME/deploy"
# the bundled installer must look for exactly the images packed next to it
sed -e "s|^VERSION=\".*\"|VERSION=\"$VERSION\"|" -e "s|^IMAGE_PREFIX=\".*\"|IMAGE_PREFIX=\"$PREFIX\"|" \
  "$ROOT/install.sh" > "$WORK/$NAME/install.sh"
chmod +x "$WORK/$NAME/install.sh"
cp "$ROOT/deploy/compose.install.yml" "$ROOT/deploy/backup.sh" "$WORK/$NAME/deploy/"
docker save "$APP" "$WEB" postgres:16-alpine redis:7-alpine caddy:2-alpine | gzip > "$WORK/$NAME/images.tar.gz"
# through stdout: on Windows, tar reads a "C:/..." file name as a remote host
(cd "$WORK" && tar -czf - "$NAME") > "$ROOT/$NAME.tar.gz"
echo "Created $ROOT/$NAME.tar.gz"
