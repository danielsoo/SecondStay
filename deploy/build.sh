#!/bin/sh
# Assemble the Fly.io build context outside the repo and deploy it.
# Usage: sh deploy/build.sh [context-dir]   (needs `fly auth login` first)
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
kit=${COSTAR_KIT_DIR:-$repo/../costar-hackathon-kit}
out=${1:-${TMPDIR:-/tmp}/secondstay-deploy}

rm -rf "$out"
mkdir -p "$out/app/data" "$out/kit/data"
cp "$repo/deploy/Dockerfile" "$repo/deploy/fly.toml" "$out/"
cp -R "$repo/secondstay" "$out/app/"
cp "$repo/assumptions.json" "$repo/la_permit_prices.json" "$repo/pyproject.toml" "$out/app/"
cp -R "$repo/data/raw" "$out/app/data/raw"
cp "$kit/data/apartment-listing.jsonl" "$kit/data/residential-listings.jsonl" "$out/kit/data/"
# Stored AI checks go along (each building opens on its last check); bytecode caches stay local.
find "$out" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$out" -name .DS_Store -delete
du -sh "$out"
[ -n "${SKIP_DEPLOY:-}" ] && exit 0  # assemble only, e.g. for a local `docker build`
cd "$out" && fly deploy --remote-only
