#!/usr/bin/env bash
# Set the application version everywhere it appears.
#   scripts/bump-version.sh 0.3.0
# Then add a CHANGELOG section and docs/releases/v0.3.0.md, commit, and push the tag (see docs/releasing.md).
set -euo pipefail

NEW="${1:?usage: scripts/bump-version.sh X.Y.Z}"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not a version: $NEW" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

sed -i -E "s/^VERSION=\"[^\"]*\"/VERSION=\"$NEW\"/" install.sh
sed -i -E "0,/^version = \"[^\"]*\"/s//version = \"$NEW\"/" pyproject.toml
sed -i -E "s/(FastAPI\(title=\"FinOps agent API\", version=)\"[^\"]*\"/\1\"$NEW\"/" apps/api/finops_api/main.py
# package.json and the first two "version" entries of the lock file (the root package)
sed -i -E "0,/\"version\": \"[^\"]*\"/s//\"version\": \"$NEW\"/" apps/web/package.json
sed -i -E "1,12s/\"version\": \"[^\"]*\"/\"version\": \"$NEW\"/" apps/web/package-lock.json

grep -n "$NEW" install.sh pyproject.toml apps/api/finops_api/main.py apps/web/package.json
head -12 apps/web/package-lock.json | grep -n "$NEW"
