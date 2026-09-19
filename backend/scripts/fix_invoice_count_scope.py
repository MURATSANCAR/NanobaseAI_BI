"""«fatura sayısı» satış faturalarını saysın, alış faturalarını değil.

Kavram tek bir tedarikçi sorgusundan çıkarılmıştı ("mal alım TRCODE 1 ve alınan hizmet TRCODE 4
faturalarında … fatura sayısı"); o sorgunun filtresi genel ölçüye yapıştı ve 2026-09-08'de onaylandı.
Sonuç: "müşteri bazında net ciro ve fatura sayısı" müşteri satırında alış faturası sayıyordu.

Doğru kapsam net ciroyla aynıdır: satış (7, 8, 9) ve satış iadesi (2, 3). Kokpitteki "Fatura 73.660"
KPI'sı tam olarak bu kümedir (2026: 49.548 + 21.009 + 107 + 643 + 2.353).

Varsayılan kuru koşudur: ne değişeceğini yazar. `--apply` ile yazar ve insan onayıyla sertifikalar
(gece işi insan kararını geri almaz).

  PYTHONPATH=backend python backend/scripts/fix_invoice_count_scope.py [--apply]
"""

from __future__ import annotations

import argparse
import dataclasses
import json

from semantic_layer.config import SemanticSettings
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.store.catalog_store import open_store

CONCEPT_ID = "sem_442e64e4a773"
WRONG = "INVOICE.TRCODE IN (1,4)"
RIGHT = "INVOICE.TRCODE IN (2,3,7,8,9)"
REASON = ("fatura sayısı satış + satış iadesi faturalarını sayar (net ciro kapsamı, kokpit KPI 73.660); "
          "TRCODE 1/4 bir tedarikçi sorgusundan yanlışlıkla geçmişti")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    c = store.get_concept(CONCEPT_ID)
    if c is None:
        print(json.dumps({"error": "kavram yok", "id": CONCEPT_ID}))
        return 1
    maps = store.list_mappings(c.id)
    new_maps = []
    changed = False
    for m in maps:
        extra = dict(m.extra or {})
        conds = [str(x) for x in extra.get("conditions") or []]
        norm = [x.replace(" ", "") for x in conds]
        if WRONG.replace(" ", "") in norm:
            extra["conditions"] = [RIGHT if x.replace(" ", "") == WRONG.replace(" ", "") else x for x in conds]
            changed = True
        new_maps.append(dataclasses.replace(m, extra=extra))
    print(json.dumps({
        "concept": {"id": c.id, "term": c.term, "status": str(c.status), "explain": c.explain},
        "before": [{"entity": m.entity, "formula": m.formula, "conditions": (m.extra or {}).get("conditions")} for m in maps],
        "after": [{"entity": m.entity, "formula": m.formula, "conditions": (m.extra or {}).get("conditions")} for m in new_maps],
        "changed": changed, "apply": args.apply,
    }, ensure_ascii=False, indent=2, default=str))
    if not changed:
        print("Değişecek bir şey yok (koşul zaten düzeltilmiş olabilir).")
        return 0
    if args.apply:
        store.replace_mappings(c.id, new_maps)
        EvidenceEngine(store).human_certify(c.id, "claude-excel-taslak", REASON)
        print("Yazıldı ve insan onayıyla sertifikalandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
