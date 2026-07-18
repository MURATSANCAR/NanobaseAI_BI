#!/usr/bin/env bash
# Create venv and install DB-GPT backend deps (Python 3.10+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    ver="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    major="${ver%%.*}"
    minor="${ver#*.}"
    if [[ "$major" -gt 3 ]] || { [[ "$major" -eq 3 ]] && [[ "$minor" -ge 10 ]]; }; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "error: Python 3.10+ required (tried python3.12/3.11/3.10/3)." >&2
  echo "Install with: brew install python@3.12" >&2
  exit 1
fi

echo "Using $PYTHON ($("$PYTHON" --version))"

if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "OK — DB-GPT CLI: $(dbgpt --version 2>/dev/null || echo 'installed')"
echo "Next: cp .env.example .env  # then edit paths/keys"
echo "Start: ./scripts/start.sh"
