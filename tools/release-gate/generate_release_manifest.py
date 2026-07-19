#!/usr/bin/env python3
"""Generate immutable Release Candidate manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (
    ARTIFACTS,
    REPO_ROOT,
    ensure_artifacts,
    git_commit,
    set_gate_status,
    sha256_tree,
    utc_now,
    write_json,
)


def _policy_versions() -> dict[str, str]:
    policies = REPO_ROOT / "backend" / "query_gateway" / "config" / "policies"
    mapping = {
        "postgres": ("postgres-statements.yaml", "postgres-functions.yaml"),
        "oracle": ("oracle-statements.yaml", "oracle-functions.yaml"),
        "hana": ("hana-statements.yaml", "hana-functions.yaml"),
        "odata": ("odata-policy.yaml",),
    }
    out: dict[str, str] = {}
    for name, files in mapping.items():
        h = sha256_tree(policies, files) if policies.exists() else "missing"
        out[name] = f"2026.07.1+{h[:12]}"
    return out


def _read_digest_file() -> dict[str, str]:
    path = ARTIFACTS / "image-digests.txt"
    digests: dict[str, str] = {}
    if not path.exists():
        return digests
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            digests[k.strip()] = v.strip()
    return digests


def build_manifest(release: str, claimed_connectors: list[str]) -> dict:
    digests = _read_digest_file()
    prompts = REPO_ROOT / "backend" / "nanobase_awel" / "prompts"
    semantic = REPO_ROOT / "configs" / "semantic"
    awel_hash = sha256_tree(prompts) if prompts.exists() else "missing"
    semantic_hash = sha256_tree(semantic, ("*.json",)) if semantic.exists() else "missing"

    # Collect prompt file hashes
    prompt_hashes: dict[str, str] = {}
    if prompts.exists():
        for p in sorted(prompts.rglob("*.jinja2")):
            rel = str(p.relative_to(prompts)).replace("\\", "/")
            from common import sha256_file

            prompt_hashes[rel] = sha256_file(p)

    return {
        "release": release,
        "gitCommit": git_commit(),
        "createdAt": utc_now(),
        "claimedConnectors": claimed_connectors,
        "components": {
            "frontend": {
                "image": "registry/nanobase/frontend",
                "digest": digests.get("frontend", "pending-build"),
            },
            "backend": {
                "image": "registry/nanobase/backend",
                "digest": digests.get("backend", "pending-build"),
            },
            "queryGateway": {
                "image": "registry/nanobase/query-gateway",
                "digest": digests.get("queryGateway", digests.get("query_gateway", "pending-build")),
            },
            "dbgpt": {
                "version": "0.8.1",
                "imageDigest": digests.get("dbgpt", "pending-build"),
            },
            "awel": {
                "workflowVersion": "1.0.0",
                "promptTreeHash": awel_hash,
                "promptHashes": prompt_hashes,
            },
            "model": {
                "modelId": "nanobase-qwen36-35b-a3b-mtp",
                "modelHash": digests.get("modelHash", "pin-before-freeze"),
                "llamaCppBuild": digests.get("llamaCppBuild", "pin-before-freeze"),
            },
            "embedding": {
                "modelId": "BAAI/bge-m3",
                "modelHash": digests.get("embeddingHash", "pin-before-freeze"),
            },
            "semanticCatalog": {
                "version": "9.0.0",
                "manifestHash": semantic_hash,
            },
            "queryPolicies": _policy_versions(),
        },
        "freezeRules": {
            "noFeatureAdds": True,
            "noPromptChanges": True,
            "noModelProfileChanges": True,
            "noSemanticMetricChanges": True,
            "noPolicyChanges": True,
            "noConnectorChanges": True,
            "noDependencyUpdates": True,
            "noTestDatasetChanges": True,
            "fixesRequireNewRc": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="1.0.0-rc.1")
    parser.add_argument(
        "--claimed-connectors",
        default="postgres",
        help="Comma-separated connectors claimed for this RC (postgres,oracle,hana,odata)",
    )
    parser.add_argument("--freeze", action="store_true", help="Advance gate to RELEASE_CANDIDATE_FROZEN")
    args = parser.parse_args(argv)

    ensure_artifacts()
    claimed = [c.strip() for c in args.claimed_connectors.split(",") if c.strip()]
    manifest = build_manifest(args.release, claimed)
    out = ARTIFACTS / "release-manifest.json"
    write_json(out, manifest)
    print(f"Wrote {out}")
    print(json.dumps({"release": args.release, "gitCommit": manifest["gitCommit"]}, indent=2))

    set_gate_status("PREPARING", release=args.release, note="manifest generated")
    if args.freeze:
        set_gate_status(
            "RELEASE_CANDIDATE_FROZEN",
            release=args.release,
            note="RC freeze after manifest",
        )
    return 0


if __name__ == "__main__":
    # Allow running as script from tools/release-gate
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
