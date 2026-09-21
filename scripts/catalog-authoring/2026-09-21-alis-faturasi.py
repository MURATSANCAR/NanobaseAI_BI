"""Muhasebe testi C kategorisi (0/10): alış faturası soruları 'kayıt yok' dönüyordu.

Kök neden: çıplak 'fatura' kavramı (sem_8a9a41ed5881) satış kapsamına bağlı — TRCODE IN (2,3,7,8,9).
Bu doğru bir varsayılan ('kaç fatura kestik' = satış, 73.660). Ama katalogda 'alım faturası' var,
'alış faturası' YOK; 'alış' ile 'alım' sözlüksel eşleşmiyor. Soru 'alış faturası' deyince öbek
bulunamıyor, içindeki 'fatura' tek başına satış kapsamını getiriyor; model alış için TRCODE IN (1,4)
yazıyor ve SQL 'TRCODE IN (2,3,7,8,9) AND TRCODE IN (1,4)' olup her zaman boş dönüyor.

Düzeltme: 'alım faturası' (GRPCODE=1, alış grubu) kavramına iş dilindeki karşılıkları eş anlamlı
olarak eklenir. İki kelimelik öbek tek kelimelik 'fatura'yı tüketir, satış kapsamı devreye girmez.
Kuru koşu varsayılan; --apply ile yazar.
"""
import datetime, os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
from semantic_layer.normalize import normalize_term

CID = "sem_f8b96c63eba4"   # 'alım faturası' → INVOICE.GRPCODE IN (1)
WHO = "operator:claude (muhasebe testi, 2026-09-21)"
TERMS = ["alış faturası", "satınalma faturası", "satın alma faturası", "tedarikçi faturası", "gelen fatura"]

st = open_store(os.environ["SEMANTIC_STORE_DSN"])
c = st.get_concept(CID)
print("ÖNCE :", c.term, c.status, "synonyms=", list(c.synonyms))
print("EKLENECEK:", TERMS, "→ normalize:", [normalize_term(t) for t in TERMS])
if "--apply" not in sys.argv:
    raise SystemExit("KURU KOŞU — yazılmadı. Uygulamak için: --apply")
for t in TERMS:
    st.add_synonym(CID, t)
c = st.get_concept(CID); ex = dict(c.explain or {})
src = dict(ex.get("synonym_sources") or {}); now = datetime.datetime.now(datetime.timezone.utc).isoformat()
for t in TERMS:
    src[normalize_term(t)] = {"by": WHO, "source": "muhasebe100 C kategorisi: alış soruları satış kapsamına düşüyordu", "at": now}
st.update_concept(CID, explain={"synonym_sources": src,
    "declared_synonyms": sorted(set(ex.get("declared_synonyms") or []) | {normalize_term(t) for t in TERMS})})
st.add_evidence(Evidence(CID, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:alis-faturasi", support_count=1, weight=1.0,
    payload={"snippet": "eş anlamlı: alış/satınalma/tedarikçi faturası → alım faturası (GRPCODE=1)", "by": WHO}))
c = st.get_concept(CID)
print("SONRA:", c.term, c.status, "synonyms=", list(c.synonyms))
