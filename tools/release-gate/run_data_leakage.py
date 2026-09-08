#!/usr/bin/env python3
"""Data leakage / masking gate (§21)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import ARTIFACTS, REPO_ROOT, ensure_artifacts, utc_now, write_json


def _mask_email(v: str) -> str:
    return re.sub(r"(^.).*(@.*$)", r"\1***\2", v)


def _mask_iban(v: str) -> str:
    return v[:4] + "*" * max(0, len(v) - 8) + v[-4:] if len(v) >= 8 else "***"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="1.0.0-rc.1")
    args = parser.parse_args(argv)
    ensure_artifacts()

    samples = {
        "email": "user@example.com",
        "phone": "+905551112233",
        "iban": "TR330006100519786457841326",
        "national_id": "12345678901",
    }
    masked = {
        "email": _mask_email(samples["email"]),
        "phone": samples["phone"][:4] + "****" + samples["phone"][-2:],
        "iban": _mask_iban(samples["iban"]),
        "national_id": "***",
    }
    unmasked_restricted = 0
    for k, raw in samples.items():
        if masked[k] == raw and k != "phone":
            # phone partial mask ok
            unmasked_restricted += 1
        if k == "iban" and samples["iban"] in masked["iban"]:
            unmasked_restricted += 1

    # The masker this deployment actually uses, exercised on canary values. Importing it and never
    # calling it measured nothing: the gate scored its own local examples, so a production masker that
    # was broken or missing still produced a pass as long as no artifact happened to contain a match.
    gateway_masker = False
    gateway_unmasked = 0
    gateway_checks: list[dict[str, object]] = []
    canaries = [
        ("email", "EMAIL", "ayse.yilmaz@example.com"),
        ("phone", "PHONE", "05321234567"),
        ("iban", "IBAN", "TR330006100519786457841326"),
        ("national_id", "IDENTITY_NUMBER", "12345678901"),
        ("card", "LAST_FOUR", "4111111111111111"),
        ("secret", "FULL", "super-secret-value"),
        ("dropped", "NULLIFY", "anything"),
    ]
    try:
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        from query_gateway.infrastructure.result.masking import mask_value  # type: ignore

        gateway_masker = True
        for label, kind, raw in canaries:
            out = mask_value(raw, kind)
            leaked = out is not None and str(raw) in str(out)
            # A mask that returns the value unchanged is not a mask, whatever its name says.
            if leaked or (kind != "NULLIFY" and str(out) == str(raw)):
                gateway_unmasked += 1
            gateway_checks.append({"field": label, "kind": kind, "leaked": bool(leaked)})
    except Exception as e:  # noqa: BLE001
        # An unimportable masker is a failure, not an absence: the check it was supposed to perform
        # did not happen, and a gate that passes when it did not run is worse than no gate.
        gateway_unmasked += 1
        gateway_checks.append({"field": "import", "kind": "-", "error": str(e)[:200]})

    # Log DLP scan on artifacts (no secrets expected)
    secret_hits = 0
    patterns = [
        re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
        re.compile(r"(?i)password\s*=\s*[^*\s]{8,}"),
        re.compile(r"(?i)authorization:\s*bearer\s+[a-z0-9\-._~+/]+=*", re.I),
    ]
    for p in (REPO_ROOT / "artifacts").rglob("*.json"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in patterns:
            if pat.search(text):
                secret_hits += 1

    pass_ = unmasked_restricted == 0 and secret_hits == 0 and gateway_masker and gateway_unmasked == 0
    doc = {
        "release": args.release,
        "generatedAt": utc_now(),
        "classes": ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PII", "FINANCIAL", "SECRET"],
        "tests": ["email", "phone", "iban", "national_id", "log_dlp"],
        "unmaskedRestricted": unmasked_restricted,
        # Not measured here, and said so rather than reported as a passing zero.
        "llmForbiddenRaw": None,
        "llmForbiddenRawMeasured": False,
        "logForbiddenRaw": secret_hits,
        "gatewayMaskerImportable": gateway_masker,
        "gatewayMaskerUnmasked": gateway_unmasked,
        "gatewayMaskerChecks": gateway_checks,
        "pass": pass_,
    }
    write_json(ARTIFACTS / "data-leakage-results.json", doc)
    print(doc)
    return 0 if pass_ else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
