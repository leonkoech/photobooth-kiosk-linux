#!/usr/bin/env bash
# Rebuilds photobooth-kiosk-front and copies its static export into
# frontend_dist/ here, which app.py serves directly.
#
# The Nano doesn't have Node.js installed and this repo intentionally
# doesn't require it -- frontend_dist/ is committed as a build artifact so
# `git pull` alone is enough to deploy a frontend change. Run this script
# (on a dev machine with Node) after making UI changes in
# photobooth-kiosk-front, then commit + push the resulting frontend_dist/
# diff here.
#
#   FRONT_DIR=../photobooth-kiosk-front ./scripts/sync-frontend.sh

set -euo pipefail

FRONT_DIR="${FRONT_DIR:-../photobooth-kiosk-front}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[[ -d "$FRONT_DIR" ]] || { echo "ERROR: FRONT_DIR '$FRONT_DIR' not found -- clone photobooth-kiosk-front next to this repo, or set FRONT_DIR=..."; exit 1; }

echo "==> building $FRONT_DIR"
(cd "$FRONT_DIR" && npm install && npm run build)

echo "==> syncing $FRONT_DIR/out -> $HERE/frontend_dist"
rm -rf "$HERE/frontend_dist"
mkdir -p "$HERE/frontend_dist"
cp -r "$FRONT_DIR/out/." "$HERE/frontend_dist/"

echo "==> done -- review with 'git status', then commit + push frontend_dist/"
