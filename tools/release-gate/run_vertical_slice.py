#!/usr/bin/env python3
"""§51 Final Gate vertical slice orchestrator."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import ARTIFACTS, REPO_ROOT, ensure_artifacts, set_gate_status, utc_now, write_json

RG = Path(__file__).resolve().parent
SCRIPTS = REPO_ROOT / "scripts" / "server" / "release-gate"


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(cwd or REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="1.0.0-rc.1")
    parser.add_argument("--claimed-connectors", default="postgres")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--run-sql-pytest", action="store_true")
    args = parser.parse_args(argv)

    ensure_artifacts()
    set_gate_status("PREPARING", release=args.release, note="vertical slice start")
    steps: list[dict] = []

    def step(name: str, code: int) -> None:
        steps.append({"name": name, "exitCode": code, "ok": code == 0})
        print(f"==> {name}: {'OK' if code == 0 else 'FAIL'} ({code})")

    step("expand_quality_corpora", _run([sys.executable, str(RG / "expand_quality_corpora.py")]))
    step("record_image_digests", _run(["bash", str(SCRIPTS / "record_image_digests.sh")]))
    step(
        "generate_release_manifest",
        _run(
            [
                sys.executable,
                str(RG / "generate_release_manifest.py"),
                "--release",
                args.release,
                "--claimed-connectors",
                args.claimed_connectors,
            ]
            + (["--freeze"] if args.freeze else [])
        ),
    )
    step("verify_release_manifest", _run([sys.executable, str(RG / "verify_release_manifest.py")]))
    step(
        "verify_phase_evidence",
        _run([sys.executable, str(RG / "verify_phase_evidence.py"), "--release", args.release]),
    )
    step("verify_sbom", _run([sys.executable, str(RG / "verify_sbom.py")]))
    step("verify_image_signatures", _run([sys.executable, str(RG / "verify_image_signatures.py")]))
    step("verify_provenance", _run([sys.executable, str(RG / "verify_provenance.py")]))

    if not args.skip_pytest:
        step(
            "tenant_isolation",
            _run([sys.executable, str(RG / "run_tenant_isolation.py"), "--release", args.release]),
        )
        step(
            "bypass_suite",
            _run([sys.executable, str(RG / "run_bypass_suite.py"), "--release", args.release]),
        )

    sql_cmd = [sys.executable, str(RG / "run_sql_security_corpus.py"), "--release", args.release]
    if args.run_sql_pytest:
        sql_cmd.append("--run-pytest")
    step("sql_security_unified", _run(sql_cmd))
    step("ai_adversarial", _run([sys.executable, str(RG / "run_ai_adversarial.py"), "--release", args.release]))
    step(
        "quality_benchmark",
        _run(
            [
                sys.executable,
                str(RG / "run_quality_benchmark.py"),
                "--release",
                args.release,
                "--require-full",
            ]
        ),
    )
    step("backup", _run(["bash", str(SCRIPTS / "backup-metadata.sh")]))
    step("restore", _run(["bash", str(SCRIPTS / "restore-metadata.sh")]))
    step("rollback", _run(["bash", str(SCRIPTS / "rollback-plan-only.sh"), "drill"]))
    step("data_leakage", _run([sys.executable, str(RG / "run_data_leakage.py"), "--release", args.release]))
    step("e2e_suite", _run([sys.executable, str(RG / "run_e2e_suite.py"), "--release", args.release]))
    step("chaos", _run([sys.executable, str(RG / "run_chaos_suite.py"), "--release", args.release]))
    step(
        "performance",
        _run(
            [
                sys.executable,
                str(RG / "run_performance_suite.py"),
                "--release",
                args.release,
                "--profile",
                "smoke",
            ]
        ),
    )
    step("determinism", _run([sys.executable, str(RG / "run_determinism.py"), "--release", args.release]))
    step(
        "secret_rotation",
        _run([sys.executable, str(RG / "run_secret_rotation_drill.py"), "--release", args.release]),
    )
    step("dr_verification", _run([sys.executable, str(RG / "run_dr_verification.py"), "--release", args.release]))
    step("customer_uat_template", _run([sys.executable, str(RG / "run_customer_uat.py"), "--release", args.release]))
    step(
        "generate_final_acceptance",
        _run([sys.executable, str(RG / "generate_final_acceptance.py"), "--release", args.release]),
    )

    # Acceptance may return 1 for NO_GO while still producing artifacts — treat as soft for slice report
    hard = [s for s in steps if s["name"] != "generate_final_acceptance"]
    ok = all(s["ok"] for s in hard)
    report = {
        "generatedAt": utc_now(),
        "release": args.release,
        "steps": steps,
        "pass": ok,
    }
    write_json(ARTIFACTS / "vertical-slice-results.json", report)
    set_gate_status(
        "VERIFYING" if ok else "BLOCKED",
        release=args.release,
        note="vertical slice complete",
    )
    print(f"Vertical slice pass={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
