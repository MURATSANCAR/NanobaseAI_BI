"""K11 — iş kararı 2026-09-20: «sevk ettiğimiz adede göre iade oranı» müşteri bazında ADET üzerinden okunur.

Katalogda gereken TEK değişiklik bir ilişki beyanıdır (soruya özel kavram/SQL yok):
  «müşteri» (CLCARD.DEFINITION_) eşlemesinin STLINE için ilişki kuralı bugün yalnız faturadan okur
  (STLINE.INVOICEREF → INVOICE.CLIENTREF → CLCARD). Faturası henüz kesilmemiş irsaliye satırında
  INVOICEREF = 0 olduğu için bu yol satırı DÜŞÜRÜR: 2026'da sevk adedinin 469.093 / 8.084.299'u (%5,8), iade
  adedinin 116.226 / 740.413'ü (%15,7) müşteri kırılımından kayboluyor; kırılım toplamı, kırılımsız toplamı tutmuyor.
  Kurala `own_column: CLIENTREF` eklenir: ara kayıt (fatura) varsa ondan, yoksa satırın kendi cari referansından
  okunur → CLCARD.LOGICALREF = COALESCE(INVOICE.CLIENTREF, STLINE.CLIENTREF), fatura LEFT JOIN.
  Canlı ölçüm (LG_411_01, 2026, 883.454 satır): faturası olan satırlarda INVOICE.CLIENTREF ≠ STLINE.CLIENTREF = 0 satır.
  Kod tarafı: patch.diff (reference_contracts.own_predicate / via_is_optional, derleyici, kapı). Kod kurulmadan bu
  anahtar zararsızdır (eski kod `own_column`'u okumaz).

Kipler:  (varsayılan) KURU KOŞU — ne yazacağını basar, yazmaz.   --apply — yazar (idempotent).
Sunucuda, köprünün ortamıyla, dosya kopyalamadan:
  sudo systemd-run --pipe --wait --collect --quiet -p User=administrator \
     -p EnvironmentFile=/etc/nanobase/semantic-bridge.env -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \
     /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < apply.py
Yazdıktan sonra: köprüyü yenile → resolver-gate.py (beklenen: okuma değişmez; bu anahtar yalnız derlemeyi etkiler)
→ answer-gate.py --only Q11,Q16,Q68.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import sys

sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")

WHO = "operator:claude (iş kararı 2026-09-20)"
SRC = "operator:2026-09-20:k11-musteri-kendi-referansi"
TERM, FACT, OWN = "müşteri", "STLINE", "CLIENTREF"
REASON = ("K11: müşteri kırılımı, faturası olmayan irsaliye satırını düşürmemeli — ilişki faturadan, fatura yoksa satırın "
          "kendi CLIENTREF'inden okunur (canlıda iki yol 883.454 satırda birebir aynı cariyi veriyor).")


def main() -> int:
    from semantic_layer.config import SemanticSettings
    from semantic_layer.evidence.engine import EvidenceEngine
    from semantic_layer.models import Evidence, EvidenceType, SemanticType
    from semantic_layer.normalize import normalize_term
    from semantic_layer.store.catalog_store import open_store

    write = "--apply" in sys.argv
    s = SemanticSettings.from_env()
    store = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False)
    found = [c for c in store.find_concepts(s.tenant_id, s.datasource_id, semantic_type=SemanticType.COLUMN, limit=10000)
             if c.normalized_term == normalize_term(TERM)]
    todo = []
    for c in found:
        maps = store.list_mappings(c.id)
        for m in maps:
            rule = ((m.extra or {}).get("reference_resolution") or {}).get(FACT)
            if not rule or rule.get("primary_column") or rule.get("fallback_column") != OWN:
                continue
            todo.append((c, maps, m, rule))
    if len(todo) != 1:
        print(json.dumps({"sonuç": "DURDU", "neden": f"'{TERM}' için {FACT} ilişki kuralı taşıyan tek eşleme bekleniyordu, bulunan: {len(todo)}"}, ensure_ascii=False))
        return 1
    c, maps, m, rule = todo[0]
    # The fact must really carry that reference: a declared relationship STLINE.CLIENTREF → this mapping's entity.
    from semantic_layer.catalog import one_entity_per_pattern
    profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id), store.concept_entities(s.tenant_id, s.datasource_id))
    fact_prof = next((p for p in profiles if p.entity == FACT), None)
    declared = [r for r in (getattr(fact_prof, "relationships", None) or [])
                if str(r.get("column") or "").upper() == OWN and str(r.get("ref_entity") or "").upper() == m.entity.upper()]
    report = {"kavram": c.term, "id": c.id, "durum": c.status, "eşleme": f"{m.entity}.{m.column}", "kural_önce": rule,
              "olgu_profili": getattr(fact_prof, "entity", None), "olgunun_kendi_referansı_profilde": bool(declared),
              "insan_sertifikalı": bool((c.explain or {}).get("human_certified_by"))}
    if not declared:
        report.update(sonuç="DURDU", neden=f"{FACT}.{OWN} → {m.entity} ilişkisi profilde beyanlı değil; derleyici bu kuralı kullanamaz")
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 1
    if rule.get("own_column") == OWN:
        report.update(sonuç="DEĞİŞİKLİK YOK", neden="own_column zaten yazılı")
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    after = copy.deepcopy(rule)
    after["own_column"] = OWN
    report["kural_sonra"] = after
    report["etki"] = ("derleme: STLINE LEFT JOIN INVOICE; CLCARD.LOGICALREF = COALESCE(INVOICE.CLIENTREF, STLINE.CLIENTREF). "
                      "Bellekte ölçüm (set100, 100 soru): deterministik SQL'i değişen sorular Q11 ve Q16; Q16 sonucu birebir aynı (2 satır, 0,9139/0,8643).")
    if not write:
        report["sonuç"] = "KURU KOŞU — yazılmadı (--apply ile yazar)"
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    for x in maps:
        if x is m:
            x.extra = copy.deepcopy(x.extra or {})
            x.extra["reference_resolution"][FACT] = after
    store.replace_mappings(c.id, maps)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    ex = dict(store.get_concept(c.id).explain or {})
    notes = list(ex.get("operator_notes") or [])
    notes.append({"by": WHO, "at": now, "source": SRC, "change": f"reference_resolution.{FACT}.own_column = {OWN}"})
    store.update_concept(c.id, explain={"operator_notes": notes})
    store.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, SRC, support_count=1, weight=1.0,
                                payload={"snippet": REASON, "by": WHO}))
    fresh = store.get_concept(c.id)
    if fresh.status != "CERTIFIED" or not (fresh.explain or {}).get("human_certified_by"):
        EvidenceEngine(store).human_certify(c.id, WHO, reason=REASON)
    report["sonuç"] = "YAZILDI"
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
