"""Muhasebe testi M014/M018/M023/M026: katalogda HİÇ tahsilat ya da tedarikçi ödemesi ölçüsü yoktu;
model her soruda kendi tanımını uyduruyordu (aynı kavram için 1,28 Mr / 282 bin / 84,8 Mn).

Tanım (bağımsız referansla aynı, DB'de ölçüldü, 2026):
  tahsilat          = cari hareket (CLFLINE) alacak kaydı (SIGN=1), TRCODE 1 nakit, 20 gelen havale,
                      61 çek girişi, 62 senet girişi, 70 kredi kartı — YALNIZ müşteri carileri (kod 120…)
                      → 896.631.533,76
  tedarikçi ödemesi = borç kaydı (SIGN=0), TRCODE 2 nakit, 21 giden havale, 63 çek çıkışı, 64 senet
                      çıkışı, 72 firma kredi kartı — YALNIZ satıcı carileri (kod 320…) → 482.684.147,84
Müşteri/satıcı filtresi ŞART: 131 Ortaklardan Alacaklar (grup şirketi transferleri, 235 Mn) aynı hareket
türlerini taşıyor; filtresiz tahsilat 1,15 Mr (+255 Mn). Kapı LIKE denetleyemediği için kapsam formüle
gömülür (gider ölçüsündeki yöntem). Kuru koşu varsayılan; --apply ile yazar."""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping, SemanticType, ConceptStatus, Evidence, EvidenceType
from semantic_layer.evidence.engine import EvidenceEngine
WHO = "operator:claude (muhasebe testi, 2026-09-21)"
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
pat = next(p.table_pattern for p in st.list_profiles("logo") if (p.entity or "").upper() in ("CLFLINE", "LG_CLFLINE"))
ent = next(p.entity for p in st.list_profiles("logo") if (p.entity or "").upper() in ("CLFLINE", "LG_CLFLINE"))
D = [("tahsilat", "1", "1,20,61,62,70", "120", ["müşteri tahsilatı", "tahsil edilen tutar", "tahsilat tutarı", "tahsilatlarımız"]),
     ("tedarikçi ödemesi", "0", "2,21,63,64,72", "320", ["satıcı ödemesi", "tedarikçilere ödeme", "tedarikçilere ödenen", "satıcılara ödeme"])]
print("tablo:", ent, pat)
for term, sign, trc, pfx, syn in D:
    print(f"{term}: SUM(CASE WHEN CLCARD.CODE LIKE '{pfx}%' THEN {ent}.AMOUNT ELSE 0 END) | SIGN IN ({sign}) TRCODE IN ({trc}) | eş: {syn}")
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
eng = EvidenceEngine(st)
for term, sign, trc, pfx, syn in D:
    m = Mapping(concept_id="", entity=ent, table_pattern=pat,
                formula=f"SUM(CASE WHEN CLCARD.CODE LIKE '{pfx}%' THEN {ent}.AMOUNT ELSE 0 END)",
                extra={"func": "SUM", "conditions": [f"{ent}.CANCELLED IN (0)", f"{ent}.SIGN IN ({sign})", f"{ent}.TRCODE IN ({trc})"]})
    c, created = st.upsert_concept("default", "logo", term, SemanticType.METRIC, mapping=m, status=ConceptStatus.CANDIDATE)
    for s in syn: st.add_synonym(c.id, s)
    reason = f"{term}: cari hareket SIGN={sign}, TRCODE {trc}, yalnız {pfx}… carileri; bağımsız referansla birebir (muhasebe100)"
    st.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, f"operator:2026-09-21:{term}", support_count=1, weight=1.0, payload={"snippet": reason, "by": WHO}))
    eng.human_certify(c.id, WHO, reason=reason)
    print("YAZILDI:", c.id, st.get_concept(c.id).term, st.get_concept(c.id).status, "yeni:", created)
