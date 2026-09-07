#!/usr/bin/env bash
# Create venv and install the backend deps.
# Target: Python 3.11 (see .python-version). dbgpt 0.8.1 pins aiohttp==3.8.4 —
# that wheel/build often fails on 3.12+ macOS.
#
#   ./scripts/setup.sh                  DB-GPT + the semantic layer
#   ./scripts/setup.sh --semantic-only  the semantic layer alone — profiling, the pipeline, the tests
#
# The semantic layer imports none of DB-GPT. Anyone working on the catalog wants the second form: it
# installs seven packages in seconds instead of building aiohttp.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SEMANTIC_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --semantic-only) SEMANTIC_ONLY=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

REQS=(requirements.txt requirements-semantic.txt)
if [[ $SEMANTIC_ONLY -eq 1 ]]; then
  REQS=(requirements-semantic.txt)
fi

# Prefer uv if available (faster, better conflict resolution)
if command -v uv >/dev/null 2>&1; then
  UV=(uv)
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV=("${HOME}/.local/bin/uv")
else
  UV=()
fi

PYTHON=""
for candidate in python3.11 python3.10; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "error: Python 3.11 required (3.10 acceptable)." >&2
  echo "Install with: brew install python@3.11" >&2
  echo "Then: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "Using $PYTHON ($("$PYTHON" --version))"

if [[ ${#UV[@]} -gt 0 ]]; then
  echo "Installing with uv (reads .python-version → 3.11)..."
  # Omit --python so uv honors backend/.python-version
  "${UV[@]}" venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  for req in "${REQS[@]}"; do "${UV[@]}" pip install -r "$req"; done
else
  echo "warn: uv not found — falling back to pip (install uv for reliability)" >&2
  if [[ ! -d .venv ]]; then
    "$PYTHON" -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip setuptools wheel
  for req in "${REQS[@]}"; do python -m pip install -r "$req"; done
fi

echo
if [[ $SEMANTIC_ONLY -eq 1 ]]; then
  echo "OK — semantic layer only."
  echo "Test:  python -m pytest semantic_layer/tests/ -q"
  echo "Build: python -m semantic_layer.cli pipeline   # see README, 'Semantic catalog'"
else
  echo "OK — DB-GPT CLI: $(dbgpt --version 2>/dev/null || echo 'installed')"
  echo "Next: cp .env.example .env  # then edit paths/keys"
  echo "Start: ./scripts/start.sh"
fi
