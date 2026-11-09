#!/usr/bin/env bash
# Build the one-file installer: install.sh with the files it puts on the server (deploy/) inside it, so that
#   curl -fsSL https://github.com/pendarsolutions/FinOps/releases/latest/download/install.sh | sudo bash
# needs nothing else. Every release attaches it, and the offline bundle carries it.
#
#   scripts/make-installer.sh [OUT]        default OUT: dist/install.sh
#
# FINOPS_VERSION and FINOPS_IMAGE_PREFIX override the version and image prefix written into finops-agent.
# The embedded files stay readable: each is a quoted heredoc, so nothing in them is expanded.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/dist/install.sh}"
END="__FINOPS_FILE_END__"
MARK="# @embedded-files"
die() { echo "make-installer: $*" >&2; exit 1; }

grep -q "^$MARK" "$ROOT/install.sh" || die "install.sh has no '$MARK' line"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
sed -e "${FINOPS_VERSION:+s|^VERSION=\"[^\"]*\"|VERSION=\"$FINOPS_VERSION\"|}" \
    -e "${FINOPS_IMAGE_PREFIX:+s|^IMAGE_PREFIX=\"[^\"]*\"|IMAGE_PREFIX=\"$FINOPS_IMAGE_PREFIX\"|}" \
    "$ROOT/deploy/finops-agent" > "$WORK/finops-agent"

embed() {  # embed NAME FILE
  ! grep -qx "$END" "$2" || die "$2 contains the line $END"
  printf '    %s)\n      cat <<'"'"'%s'"'"'\n' "$1" "$END"
  cat "$2"
  [ -z "$(tail -c1 "$2")" ] || echo
  printf '%s\n      ;;\n' "$END"
}

mkdir -p "$(dirname "$OUT")"
{
  sed -n "1,/^$MARK/p" "$ROOT/install.sh"
  echo "EMBEDDED=1"
  echo "embedded_file() {"
  echo '  case "$1" in'
  embed compose.install.yml "$ROOT/deploy/compose.install.yml"
  embed backup.sh "$ROOT/deploy/backup.sh"
  embed finops-agent "$WORK/finops-agent"
  echo '    *) return 1 ;;'
  echo '  esac'
  echo '}'
  sed -n "/^$MARK/,\$p" "$ROOT/install.sh" | tail -n +2
} > "$OUT.tmp"
bash -n "$OUT.tmp" || die "the result doesn't parse"
chmod 755 "$OUT.tmp"
mv -f "$OUT.tmp" "$OUT"
echo "Created $OUT (version $(sed -n 's/^VERSION="\([^"]*\)".*/\1/p' "$WORK/finops-agent"))"
