"""Arşiv P100 hata sınıfları (2026-09-21), iş kararı: tamamlanmış satış faturadır (kayıt sistemi Logo, fatura).

1) Faturalı satır kuralı — satış adedi/tutarı/net ciro (satır) faturası olmayan irsaliye satırlarını da sayıyordu.
   Ölçüm: Ocak 2026 satılan adet 1.034.224 = faturalı 943.754 + faturasız 90.470 (fark birebir faturasız satırlar);
   2026 satır net ciro 839,59 Mn → faturalı 837,90 Mn (faturasız satış 13,6 Mn, faturasız iade 11,9 Mn).
   Koşul: STLINE.INVOICEREF NOT IN (0). (kâr/maliyet ölçüleri bu turda değişmedi — ayrı karar.)
2) Net satış — "net satış tutarı" net ciroya bağlanmıyor, "satış tutarı"na (iade düşülmemiş) gidiyordu.
   "perakende" tek kelimelik eş anlamlısı 'perakende payı' ölçüsündeydi (tek kelime kuralı): kanal filtresi yerine
   oran ölçüsü seçiliyordu. Kanal değerleri iadesiyle birlikte: perakende = TRCODE 7 satış + 2 iade, toptan = 8 + 3
   (Logo fiş türleri); satış ölçüleri kendi TRCODE koşuluyla kesiştiği için satış sorularında sonuç değişmez.
3) Satış satırı sayısı — katalogda yoktu; COUNT(STLINE.LOGICALREF), satış malzeme satırı, faturalı.
Kuru koşu varsayılan; --apply ile yazar."""
import os, sys, dataclasses
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping, SemanticType, ConceptStatus, Evidence, EvidenceType
from semantic_layer.evidence.engine import EvidenceEngine
WHO = "operator:claude (arşiv P100, 2026-09-21)"
SALES_METRICS = ["sem_0777c0af5563", "sem_c7c4b595ee6a", "sem_b62a0c853395", "sem_8542c8254c47"]
CHANNEL = {"sem_7d7582bb6525": ["2", "7"], "sem_862a69064242": ["2", "7"],      # perakende (STLINE, INVOICE)
           "sem_73c2b14a9720": ["3", "8"], "sem_7fdbfd1bd0e8": ["3", "8"]}      # toptan (STLINE, INVOICE)
NET_SYNONYMS = ["net satış tutarı", "net satış"]
st = open_store(os.environ["SEMANTIC_STORE_DSN"])

plan = []
for cid in SALES_METRICS:
    new = []
    for m in st.list_mappings(cid):
        conds = list((m.extra or {}).get("conditions") or [])
        cond = f"{m.entity}.INVOICEREF NOT IN (0)"
        if cond not in conds:
            ex = dict(m.extra or {}); ex["conditions"] = conds + [cond]
            m = dataclasses.replace(m, extra=ex)
        new.append(m)
    plan.append(("koşul", cid, new))
    print(f"koşul  {cid} '{st.get_concept(cid).term}': {[(x.extra or {}).get('conditions') for x in new]}")
for cid, vals in CHANNEL.items():
    ms = st.list_mappings(cid)
    new = [dataclasses.replace(m, values=vals) if m.column and m.column.upper() == "TRCODE" else m for m in ms]
    plan.append(("kanal", cid, new))
    print(f"kanal  {cid} '{st.get_concept(cid).term}' {ms[0].entity}: {[m.values for m in ms]} → {[m.values for m in new]}")
payi = "sem_ee0c320bdea5"
print(f"eş-sil {payi} '{st.get_concept(payi).term}': {st.get_concept(payi).synonyms} → 'perakende' (tek kelime) çıkar")
base = st.list_mappings("sem_0777c0af5563")[0]
e = base.entity
count_map = Mapping(concept_id="", entity=e, table_pattern=base.table_pattern, formula=f"COUNT({e}.LOGICALREF)",
                    extra={"func": "COUNT", "conditions": [f"{e}.LINETYPE IN (0)", f"{e}.CANCELLED IN (0)",
                                                           f"{e}.TRCODE IN (7,8)", f"{e}.INVOICEREF NOT IN (0)"]})
print(f"yeni   'satış satırı sayısı': {count_map.formula} | {count_map.extra['conditions']}")
if "--apply" not in sys.argv:
    raise SystemExit("KURU KOŞU")

eng = EvidenceEngine(st)
def note(cid, text):
    st.add_evidence(Evidence(cid, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:faturali-satis", support_count=1, weight=1.0,
                             payload={"snippet": text, "by": WHO}))
for kind, cid, new in plan:
    st.replace_mappings(cid, new)
    note(cid, "satış faturalı satırdır (INVOICEREF ≠ 0)" if kind == "koşul" else "kanal = satış + aynı kanalın iadesi (TRCODE 7/2, 8/3)")
for s in NET_SYNONYMS:
    st.add_synonym("sem_8542c8254c47", s)
note("sem_8542c8254c47", "net satış tutarı = net ciro (satış − iade)")
c = st.get_concept(payi)
st.update_concept(payi, synonyms=[s for s in c.synonyms if s.strip() != "perakende"])
note(payi, "tek kelimelik 'perakende' eş anlamlısı kanal filtresini yutuyordu")
c, created = st.upsert_concept("default", "logo", "satış satırı sayısı", SemanticType.METRIC, mapping=count_map, status=ConceptStatus.CANDIDATE)
for s in ["satış satırı", "satış kalemi sayısı", "fatura satırı sayısı"]:
    st.add_synonym(c.id, s)
note(c.id, "satış satırı sayısı = faturalı satış malzeme satırı adedi (arşiv P100 tanımı)")
eng.human_certify(c.id, WHO, reason="arşiv P100 satır sayısı tanımı, bağımsız referansla ölçülecek")
print("YAZILDI; yeni kavram", c.id, st.get_concept(c.id).status, "| payı eş:", st.get_concept(payi).synonyms)

# Not (aynı gün, ikinci geçiş): 'satış satırı sayısı' kavramı (sem_c5f321293a34) önceden vardı; upsert_concept var olan
# eşlemeyi korudu, yukarıdaki koşullar yazılmadı. Eşleme ayrıca replace_mappings ile değiştirildi: LINETYPE = (0),
# CANCELLED = (0), TRCODE IN (7,8), INVOICEREF NOT IN (0); definition_source korundu.
# Üçüncü geçiş: 'satış tutarı' (sem_b62a0c853395) koşulu TRCODE IN (2,3,7,8,9) → (7,8,9). Formül iadeyi zaten 0 sayıyor;
# iade satırları yalnız sıfır tutarlı gruplar üretiyordu (arşiv P100'de toplam doğru, grup sayısı fazla).
# Üçüncü geçiş GERİ ALINDI: daraltma set100 Q19'u ("iade hariç ... ciro", beklenen netleştirme) retle bozdu; koşul
# yeniden TRCODE IN (2,3,7,8,9). Sıfır tutarlı iade grupları görünüm sorunu olarak açık kaldı.
