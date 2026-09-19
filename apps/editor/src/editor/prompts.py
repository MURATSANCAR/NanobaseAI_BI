"""Versioned prompts (src/editor/prompts/*.md) registered in ed.prompt.

A prompt file starts with `<!-- name: x version: n -->`. Changing the body
without bumping the version is refused, so a ledger row always points at the
exact text that produced it.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

from . import db
from .llm import PromptRef

DIR = Path(__file__).resolve().parent / "prompts"
HEAD = re.compile(r"<!--\s*name:\s*(\S+)\s+version:\s*(\S+)\s*-->\s*\n")


@lru_cache(maxsize=None)
def load(name: str) -> tuple[PromptRef, str]:
    text = (DIR / f"{name}.md").read_text()
    m = HEAD.match(text)
    if not m or m.group(1) != name:
        raise ValueError(f"prompt {name}: bad header")
    return PromptRef(name, m.group(2)), text[m.end():].strip()


def register_all() -> dict[str, dict]:
    """Insert every prompt; returns the manifest stored on the generation."""
    manifest = {}
    for f in sorted(DIR.glob("*.md")):
        ref, body = load(f.stem)
        sha = hashlib.sha256(body.encode()).hexdigest()
        row = db.one("SELECT sha256 FROM prompt WHERE name=%s AND version=%s", ref.name, ref.version)
        if row is None:
            db.one("INSERT INTO prompt(name, version, sha256, body) VALUES (%s,%s,%s,%s) "
                   "ON CONFLICT DO NOTHING RETURNING name", ref.name, ref.version, sha, body)
        elif row["sha256"] != sha:
            raise RuntimeError(f"prompt {ref.name} v{ref.version} changed without a version bump")
        manifest[ref.name] = {"version": ref.version, "sha256": sha}
    return manifest


SHARED = ("modality_rules",)      # one definition, included wherever {{name}} appears


def render(name: str, **kw: str) -> tuple[PromptRef, str]:
    ref, body = load(name)
    for shared in SHARED:
        if "{{" + shared + "}}" in body:
            body = body.replace("{{" + shared + "}}", load(shared)[1])
    for k, v in kw.items():
        body = body.replace("{{" + k + "}}", v)
    return ref, body
