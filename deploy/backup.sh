#!/usr/bin/env bash
# Back up FinOps agent, or put a backup back. install.sh copies this to the install directory.
#
#   sudo /opt/finops-agent/backup.sh                    back up now
#   sudo /opt/finops-agent/backup.sh --keep 14          ...and delete all but the newest 14 (the daily job does this)
#   sudo /opt/finops-agent/backup.sh --restore FILE     replace the current data with a backup
#
# A backup is one file, readable only by root, in /var/backups/finops-agent (FINOPS_BACKUP_DIR changes it). It holds
# the database, the uploaded invoices, and the settings file, which has the keys that decrypt the stored SSH keys:
# keep backups as safe as the server itself.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${FINOPS_BACKUP_DIR:-/var/backups/finops-agent}"
KEEP=""
RESTORE=""
YES=0

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: sudo $0 [--keep N] | --restore FILE [--yes]

  (no option)       Back up now, to $DEST
  --keep N          After backing up, keep only the newest N backups
  --restore FILE    Replace the current data with this backup (a backup of the current data is taken first)
  --yes             Don't ask before restoring
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP="${2:?--keep needs a number}"; shift 2 ;;
    --restore) RESTORE="${2:?--restore needs a file}"; shift 2 ;;
    --yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done

[ "$(id -u)" = 0 ] || die "run this as root (sudo $0)"
[[ -z "$KEEP" || "$KEEP" =~ ^[1-9][0-9]*$ ]] || die "--keep needs a whole number of 1 or more"
cd "$DIR"
[ -f compose.yml ] && [ -f .env ] || die "compose.yml and .env must be next to this script, in the install directory"

compose() { docker compose "$@"; }
running() { compose ps --status running --services 2>/dev/null | grep -qx "$1"; }
env_value() { sed -n "s/^$1=//p" "$2" | head -1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Writes one backup file and prints its path. $1 names it: a date, or "before-restore-<date>".
backup() {
  local name="finops-agent-$1.tar.gz" stage="$WORK/backup"
  running postgres || die "the database isn't running; start it with: cd $DIR && docker compose up -d"
  mkdir -p "$stage"
  ( umask 077; mkdir -p "$DEST" )
  chmod 700 "$DEST"
  compose exec -T postgres pg_dump -U finops -d finops --format=custom > "$stage/database.dump"
  compose run --rm --no-deps -T api tar -C /app/var/uploads -cf - . > "$stage/uploads.tar"
  cp .env "$stage/env"
  env_value FINOPS_APP_IMAGE .env > "$stage/app-image"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$stage/created"
  ( umask 077; tar -czf "$DEST/$name" -C "$stage" . )
  rm -rf "$stage"
  echo "$DEST/$name"
}

# The current settings with the backup's, except the ones that belong to this machine rather than to the data:
# image versions, ports, address, and the database password the running database was created with.
MACHINE_KEYS="FINOPS_APP_IMAGE|FINOPS_WEB_IMAGE|FINOPS_ADDRESS|FINOPS_BEHIND_PROXY|FINOPS_HTTPS_PORT|FINOPS_HTTPS_BIND|FINOPS_HTTP_BIND|POSTGRES_PASSWORD|FINOPS_CORS_ORIGINS|FINOPS_PUBLIC_URL|FINOPS_DAILY_BACKUP"
merge_env() {
  grep -vE "^($MACHINE_KEYS)=" "$1" || true
  grep -E "^($MACHINE_KEYS)=" "$2" || true
}

restore() {
  local file="$1" from="$WORK/restore" stamp before
  [ -f "$file" ] || die "backup not found: $file"
  mkdir -p "$from"
  tar -xzf "$file" -C "$from" || die "$file isn't a FinOps agent backup"
  [ -s "$from/database.dump" ] && [ -s "$from/env" ] || die "$file isn't a FinOps agent backup"

  echo "This replaces the current data with the backup from $(cat "$from/created" 2>/dev/null || echo "an unknown date")."
  if [ "$YES" = 0 ]; then
    [ -t 0 ] || die "add --yes to restore without being asked"
    read -r -p "Type yes to continue: " answer
    [ "$answer" = yes ] || die "nothing was changed"
  fi

  stamp="$(date +%Y%m%d-%H%M%S)"
  say "Backing up the current data first"
  # a plain assignment, so a failed backup stops here, before anything is replaced
  before="$(backup "before-restore-$stamp")"
  echo "  $before"

  say "Stopping the app"
  compose stop api worker beat web >/dev/null

  say "Restoring the settings"
  ( umask 077; merge_env "$from/env" .env > .env.restored )
  cp -p .env ".env.before-restore-$stamp"
  mv .env.restored .env

  say "Restoring the database"
  compose exec -T postgres psql -U finops -d postgres -v ON_ERROR_STOP=1 -q \
    -c "DROP DATABASE IF EXISTS finops WITH (FORCE)" -c "CREATE DATABASE finops OWNER finops" >/dev/null
  compose exec -T postgres pg_restore -U finops -d finops --no-owner --exit-on-error < "$from/database.dump"

  say "Restoring the uploaded invoices"
  if [ -s "$from/uploads.tar" ]; then
    compose run --rm --no-deps -T api sh -c 'find /app/var/uploads -mindepth 1 -delete && tar -C /app/var/uploads -xf -' \
      < "$from/uploads.tar"
  fi

  say "Starting the app (it upgrades a backup from an older version by itself)"
  compose up -d >/dev/null
  echo
  echo "Restored. The data from before is in the backup above, and the settings from before in"
  echo "$DIR/.env.before-restore-$stamp."
}

if [ -n "$RESTORE" ]; then
  restore "$RESTORE"
  exit 0
fi

say "Backing up"
path="$(backup "$(date +%Y%m%d-%H%M%S)")"
echo "  $path ($(du -h "$path" | cut -f1))"
if [ -n "$KEEP" ]; then
  # only dated backups rotate; the ones taken before a restore are kept until you delete them
  find "$DEST" -maxdepth 1 -name 'finops-agent-[0-9]*.tar.gz' -printf '%T@ %p\n' | sort -rn | tail -n +"$((KEEP + 1))" |
    cut -d' ' -f2- | while read -r old; do rm -f "$old" && echo "  removed $old"; done
fi
