#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/init.py
python3 scripts/preflight.py
# Offline by default: import the release bundle first. No downloads at customer startup.
docker compose up -d --no-build --pull never --wait --wait-timeout 180
python3 scripts/verify.py
