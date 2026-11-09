#!/usr/bin/env bash
# Build an offline bundle: every image plus the installer, for a server with no registry access.
#   scripts/make-bundle.sh [version]   ->  finops-agent-<version>.tar.gz
# On the server:  tar xzf finops-agent-*.tar.gz && cd finops-agent-* && sudo ./install.sh --bundle images.tar.gz
# (or, on an installation that has it: sudo finops-agent upgrade --bundle finops-agent-<version>.tar.gz)
#
# The version and image prefix default to the ones in deploy/finops-agent. FINOPS_IMAGE_PREFIX overrides the prefix,
# and FINOPS_IMAGE_SOURCE (a repository URL) labels the images so a registry can link them to it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
from_cli() { sed -n "s/^$1=\"\([^\"]*\)\".*/\1/p" "$ROOT/deploy/finops-agent"; }
VERSION="${1:-$(from_cli VERSION)}"
PREFIX="${FINOPS_IMAGE_PREFIX:-$(from_cli IMAGE_PREFIX)}"
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

mkdir -p "$WORK/$NAME"
# the bundled installer carries its files and looks for exactly the images packed next to it
FINOPS_VERSION="$VERSION" FINOPS_IMAGE_PREFIX="$PREFIX" "$ROOT/scripts/make-installer.sh" "$WORK/$NAME/install.sh"
docker save "$APP" "$WEB" postgres:16-alpine redis:7-alpine caddy:2-alpine | gzip > "$WORK/$NAME/images.tar.gz"
# through stdout: on Windows, tar reads a "C:/..." file name as a remote host
(cd "$WORK" && tar -czf - "$NAME") > "$ROOT/$NAME.tar.gz"
echo "Created $ROOT/$NAME.tar.gz"
