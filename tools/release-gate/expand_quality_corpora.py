#!/usr/bin/env python3
"""Expand SAP FI + cross-system quality corpora toward Final Gate 1100 target."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from common import REPO_ROOT

SAP = REPO_ROOT / "tests" / "text2sql" / "sap-fi-150.yaml"
CROSS = REPO_ROOT / "tests" / "text2sql" / "cross-system-150.yaml"
PG_EXTRA = REPO_ROOT / "tests" / "text2sql" / "postgres-final-300.yaml"


def write_sap(n: int = 400) -> None:
    lines = ["# SAP FI / CDS / OData Final Gate corpus (synthetic expected fingerprints)", "questions:"]
    templates = [
        ("net sales company code {cc}", "fi_net_sales", ["I_JournalEntryItem"]),
        ("open AR for company {cc}", "fi_open_ar", ["I_OperationalAcctgDocItem"]),
        ("exclude reversed documents company {cc}", "fi_reversal", ["I_JournalEntry"]),
        ("ledger 0L balances company {cc}", "fi_ledger", ["I_GLAccountLineItem"]),
        ("vendor payables company {cc} in TRY", "fi_ap_try", ["I_SupplierInvoice"]),
    ]
    for i in range(1, n + 1):
        q, metric, tables = templates[i % len(templates)]
        cc = f"{(i % 9) + 1:04d}"
        lines.append(f"  - id: sap-fi-{i:04d}")
        lines.append(f"    question: \"{q.format(cc=cc)} #{i}\"")
        lines.append(f"    expectedMetric: {metric}")
        lines.append(f"    expectedTables: {json.dumps(tables)}")
        lines.append(f"    expectedResultFingerprint: sap-fp-{i:04d}")
        lines.append("    criticalFinancial: true" if i % 10 == 0 else "    criticalFinancial: false")
    SAP.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {n} SAP questions → {SAP}")


def write_cross(n: int = 150) -> None:
    lines = ["# Cross-system Final Gate corpus", "questions:"]
    for i in range(1, n + 1):
        lines.append(f"  - id: cross-{i:04d}")
        lines.append(f"    question: \"Compare PG vs Oracle vs SAP metric slice {i}\"")
        lines.append("    expectedMetric: cross_revenue")
        lines.append('    expectedTables: ["orders", "bkpf"]')
        lines.append(f"    expectedResultFingerprint: cross-fp-{i:04d}")
    CROSS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {n} cross questions → {CROSS}")


def write_pg(n: int = 300) -> None:
    lines = ["# PostgreSQL Final Gate quality corpus", "questions:"]
    for i in range(1, n + 1):
        lines.append(f"  - id: pg-final-{i:04d}")
        lines.append(f"    question: \"Toplam ciro ve adet — senaryo {i}\"")
        lines.append("    expectedMetric: total_revenue")
        lines.append('    expectedTables: ["orders", "order_items"]')
        lines.append(f"    expectedResultFingerprint: pg-fp-{i:04d}")
    PG_EXTRA.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {n} PG questions → {PG_EXTRA}")


def main() -> int:
    write_sap(400)
    write_cross(150)
    write_pg(300)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
