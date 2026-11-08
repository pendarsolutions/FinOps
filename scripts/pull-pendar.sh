#!/usr/bin/env bash
# Download Pendar's design system (version 3, pinned) from Specimen into the web app, then commit the result.
#   SPECIMEN_TOKEN=... scripts/pull-pendar.sh
#
# The read-only key is used only here, on a developer's machine. The built site never calls Specimen.
# Everything this writes is generated: change values in Specimen and run this again instead of editing the files.
#   apps/web/src/pendar/   tokens.css, fonts/, icons.svg, icons.ts, logo.ts
#   apps/web/public/       favicon.ico, favicon.svg, favicon-*.png, apple-touch-icon.png
set -euo pipefail

: "${SPECIMEN_TOKEN:?set SPECIMEN_TOKEN to a read-only Specimen API key}"
VERSION=3
API="https://specimen.ariaashrafi.com/api/v1/brands/pendar"
ESTEDAD_LICENSE="https://raw.githubusercontent.com/aminabedi68/Estedad/master/OFL.txt"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/apps/web/src/pendar"
PUBLIC="$ROOT/apps/web/public"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || { echo "Python 3.9 or later is needed" >&2; exit 1; }

fetch() {
  curl -fsS --retry 3 -H "Authorization: Bearer $SPECIMEN_TOKEN" -o "$2" "$API/$1"
  echo "  $1"
}

echo "Pendar v$VERSION from Specimen:"
fetch "tokens.css?version=$VERSION" "$TMP/tokens.css"
for collection in estedad icons favicons logo symbol motion; do
  fetch "collections/$collection.zip?version=$VERSION" "$TMP/$collection.zip"
done
curl -fsS --retry 3 -o "$TMP/OFL.txt" "$ESTEDAD_LICENSE"
echo "  Estedad license (OFL 1.1)"

mkdir -p "$OUT" "$PUBLIC"
"$PY" "$ROOT/scripts/pendar_assets.py" "$TMP" "$OUT" "$PUBLIC" "$VERSION"
echo "Done. Review the changes and commit them."
