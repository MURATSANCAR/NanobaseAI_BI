#!/usr/bin/env python3
"""Check every downloaded model file against Hugging Face (size + LFS sha256)
at the revision pinned in /data/editor/models/MANIFEST.json.

  python3 verify_models.py [Qwen3-VL-8B-Instruct ...]   # default: all in the manifest
"""

import hashlib
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.environ.get("EDITOR_ROOT", "/data/editor") + "/models"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(repo: str, rev: str) -> list[str]:
    name = repo.split("/")[1]
    info = json.load(urllib.request.urlopen(
        f"https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true"))
    problems, jobs = [], []
    for s in info["siblings"]:
        p = os.path.join(ROOT, name, s["rfilename"])
        if not os.path.exists(p):
            problems.append(f"missing {p}")
            continue
        if os.path.exists(p + ".aria2"):
            problems.append(f"incomplete {p}")
            continue
        if s.get("size") is not None and os.path.getsize(p) != s["size"]:
            problems.append(f"size {p}: {os.path.getsize(p)} != {s['size']}")
            continue
        if s.get("lfs"):
            jobs.append((p, s["lfs"]["sha256"]))
    with ThreadPoolExecutor(8) as ex:
        for (p, want), got in zip(jobs, ex.map(lambda j: sha256(j[0]), jobs)):
            if got != want:
                problems.append(f"sha256 {p}")
    return problems


def main() -> int:
    manifest = json.load(open(os.path.join(ROOT, "MANIFEST.json")))
    only = set(sys.argv[1:])
    bad = 0
    for repo, m in manifest.items():
        if only and repo.split("/")[1] not in only:
            continue
        problems = check(repo, m["revision"])
        print(f"{'OK ' if not problems else 'BAD'} {repo}@{m['revision'][:10]}", *problems, sep="\n  ")
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
