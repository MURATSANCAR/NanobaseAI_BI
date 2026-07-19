#!/usr/bin/env python3
"""Re-run failed chat cases + qg_and_case after QG TokenError fix."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Load helpers from e2e validator
_e2e = Path(__file__).resolve().parent / "erp-complex-e2e-validate.py"
ns: dict = {"__name__": "erp_complex_e2e_validate", "__file__": str(_e2e)}
exec(_e2e.read_text(encoding="utf-8"), ns)
run_chat = ns["run_chat"]
qg_execute = ns["qg_execute"]
qg_rows = ns["qg_rows"]
CHAT_PROMPTS = {p["id"]: p for p in ns["CHAT_PROMPTS"]}

FAILED = ["C01", "C04", "C05"]
out = {"chat": [], "qg_and_case": None}


def main() -> int:
    for cid in FAILED:
        print(f"## rerun {cid}")
        out["chat"].append(run_chat(CHAT_PROMPTS[cid]))
        time.sleep(2)

    sql = (
        "SELECT bp.butce_kodu, CASE WHEN bp.planlanan_tutar=0 THEN NULL "
        "ELSE ROUND(100.0*COALESCE(SUM(af.genel_toplam),0)/bp.planlanan_tutar,2) END AS pct "
        "FROM butce_planlari bp LEFT JOIN alis_faturalari af "
        "ON bp.butce_kodu=af.butce_kodu AND EXTRACT(YEAR FROM af.fatura_tarihi)=bp.mali_yil "
        "WHERE bp.mali_yil=2026 AND upper(bp.tur)='OPEX' "
        "GROUP BY bp.butce_kodu, bp.planlanan_tutar ORDER BY pct DESC NULLS LAST LIMIT 5"
    )
    data = qg_execute(sql)
    rows = qg_rows(data)
    ok = len(rows) >= 1
    out["qg_and_case"] = {"ok": ok, "row_count": len(rows), "sample": rows[0] if rows else None}
    print(f"  QG_AND_CASE {'PASS' if ok else 'FAIL'} rows={len(rows)}")

    chat_ok = sum(1 for r in out["chat"] if r.get("ok"))
    summary = {
        "chat_pass": f"{chat_ok}/{len(out['chat'])}",
        "hard_fail": sum(1 for r in out["chat"] if r.get("hard_fail")),
        "qg_and_case": ok,
        "gate_pass": chat_ok == len(out["chat"]) and ok and all(not r.get("hard_fail") for r in out["chat"]),
    }
    Path("/tmp/erp-complex-rerun-report.json").write_text(
        json.dumps({"summary": summary, **out}, ensure_ascii=False, indent=2)
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
