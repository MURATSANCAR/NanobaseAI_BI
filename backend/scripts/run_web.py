#!/usr/bin/env python3
"""Start DB-GPT web after applying the Neon dual-database connector patch."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Import before apply() so the class exists to patch.
import dbgpt_serve.datasource.manages.connector_manager  # noqa: E402, F401
from patch_connector_db_name import apply as apply_connector_patch  # noqa: E402
from patch_stream_generator import apply as apply_stream_patch  # noqa: E402

apply_connector_patch()
apply_stream_patch()

from dbgpt.cli.cli_scripts import main  # noqa: E402

if __name__ == "__main__":
    # Preserve: python run_web.py start web --config ... --yes
    # Drop run_web.py from argv so Click sees `dbgpt`-style args.
    sys.argv = ["dbgpt", *sys.argv[1:]]
    raise SystemExit(main())
