#!/usr/bin/env bash
# Rebuild the console and sync it into the Hugging Face Space (deploy/huggingface).
# The Space serves a prebuilt copy of frontend/ from webapp/spa; without this
# step it keeps shipping an old bundle that lacks newer pages.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPA="$ROOT/deploy/huggingface/webapp/spa"

cd "$ROOT/frontend"
[ -d node_modules ] || npm ci
rm -rf dist
npm run build

rm -rf "$SPA/assets"
mkdir -p "$SPA"
cp -r dist/assets "$SPA/assets"
cp dist/index.html "$SPA/index.html"
[ -f dist/favicon.svg ] && cp dist/favicon.svg "$SPA/favicon.svg"
rm -rf dist

# Every shipped bundle must be the one index.html loads.
for f in "$SPA"/assets/*.js "$SPA"/assets/*.css; do
  name="$(basename "$f")"
  grep -q "/assets/$name" "$SPA/index.html" || { echo "stale asset: $name" >&2; exit 1; }
done
echo "Space console synced: $(grep -o 'assets/index-[^"]*\.js' "$SPA/index.html")"
