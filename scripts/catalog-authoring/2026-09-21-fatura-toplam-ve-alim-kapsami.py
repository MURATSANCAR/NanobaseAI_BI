"""Muhasebe testi M031: 'alış faturalarımızın toplam tutarı' 579,8 Mn döndü, doğrusu 492,4 Mn.
İki kusur, ikisi de veride kanıtlı (LG_411_01_INVOICE, 2026, iptal hariç):

1) 'fatura toplam' metriği BRÜT topluyordu: SUM(INVOICE.GROSSTOTAL) (iskonto öncesi). Kokpit ve
   bağımsız referans NET kullanır (NETTOTAL — tahsil/ödenecek tutar). Bu yalnız alışı değil bütün
   fatura toplamı sorularını etkiliyordu.
2) 'alım faturası' ALIŞ GRUBUNA bağlıydı (GRPCODE=1) — grup alış iadesini de içerir:
     GRPCODE=1 → TRCODE 1 (alış, 195,2 Mn) + 4 (alınan hizmet, 297,2 Mn) + 6 (ALIŞ İADESİ, 20,4 Mn net)
   'Alış faturası' iadeyi içermez: TRCODE IN (1,4) → net 492.447.013,72 (referansla birebir).
   Simetri: 'fatura' ve 'satış faturası' da TRCODE'a bağlı.

Kuru koşu varsayılan; --apply ile yazar. Eşleme değişikliği replace_mappings ile (kanıt eklenir).
"""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping, Evidence, EvidenceType

WHO = "operator:claude (muhasebe testi, 2026-09-21)"
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
TOPLAM, ALIM = "sem_7d3196fdb5ee", "sem_f8b96c63eba4"

for cid in (TOPLAM, ALIM):
    c = st.get_concept(cid); ms = st.list_mappings(cid)
    print("ÖNCE :", c.term, "|", [(m.entity, m.column, m.values, m.formula) for m in ms])
print("SONRA: fatura toplam → SUM(INVOICE.NETTOTAL)")
print("SONRA: alım faturası → INVOICE.TRCODE IN (1,4)")
if "--apply" not in sys.argv:
    raise SystemExit("KURU KOŞU — yazılmadı. Uygulamak için: --apply")

old = st.list_mappings(TOPLAM)[0]
st.replace_mappings(TOPLAM, [Mapping(concept_id=TOPLAM, entity=old.entity, table_pattern=old.table_pattern,
                                     formula="SUM(INVOICE.NETTOTAL)", extra=dict(old.extra or {}))])
st.add_evidence(Evidence(TOPLAM, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:fatura-toplam-net", support_count=1, weight=1.0,
    payload={"snippet": "fatura toplamı NET tutardır (NETTOTAL); GROSSTOTAL iskonto öncesi brüttür. Kokpit ve referans NETTOTAL.", "by": WHO}))

old = st.list_mappings(ALIM)[0]
st.replace_mappings(ALIM, [Mapping(concept_id=ALIM, entity=old.entity, table_pattern=old.table_pattern,
                                   column="TRCODE", operator="IN", values=["1", "4"], extra=dict(old.extra or {}))])
st.add_evidence(Evidence(ALIM, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:alim-faturasi-trcode", support_count=1, weight=1.0,
    payload={"snippet": "alış faturası = TRCODE 1 (alış) + 4 (alınan hizmet); GRPCODE=1 alış iadesini (TRCODE 6) de içeriyordu.", "by": WHO}))

for cid in (TOPLAM, ALIM):
    c = st.get_concept(cid); ms = st.list_mappings(cid)
    print("YAZILDI:", c.term, c.status, "|", [(m.entity, m.column, m.values, m.formula) for m in ms])
