"""M031 (ikinci kusur): 'alış faturalarımızın toplam tutarı' katalogdaki 'fatura toplam' metriğine hiç
gitmiyordu (kavram kimliği boş); çözücü, açıklamasında 'toplam tutar' geçen BRÜT kolonu (GROSSTOTAL)
kendisi seçiyordu. 'fatura toplam' NET (NETTOTAL) olarak düzeltilmişti ama devreye girmiyordu.
İş dilindeki karşılıklar metriğe eş anlamlı olarak eklenir. Kuru koşu varsayılan; --apply ile yazar."""
import datetime, os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
from semantic_layer.normalize import normalize_term
CID, WHO = "sem_7d3196fdb5ee", "operator:claude (muhasebe testi, 2026-09-21)"
TERMS = ["fatura tutarı", "toplam fatura tutarı", "fatura toplam tutarı", "toplam tutar"]
st = open_store(os.environ["SEMANTIC_STORE_DSN"]); c = st.get_concept(CID)
print("ÖNCE :", c.term, list(c.synonyms), [m.formula for m in st.list_mappings(CID)])
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
for t in TERMS: st.add_synonym(CID, t)
c = st.get_concept(CID); ex = dict(c.explain or {}); src = dict(ex.get("synonym_sources") or {})
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
for t in TERMS: src[normalize_term(t)] = {"by": WHO, "source": "muhasebe100 M031: toplam tutar brüt kolona gidiyordu", "at": now}
st.update_concept(CID, explain={"synonym_sources": src, "declared_synonyms": sorted(set(ex.get("declared_synonyms") or []) | {normalize_term(t) for t in TERMS})})
st.add_evidence(Evidence(CID, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:fatura-toplam-tutari", support_count=1, weight=1.0,
    payload={"snippet": "fatura toplam tutarı NET tutardır (NETTOTAL)", "by": WHO}))
print("SONRA:", st.get_concept(CID).synonyms)
