"""Q29: «bekleyen sipariş tutarı» ölçüsü katalogda sertifikalı, ama soru "bekleyen TOPLAM tutar"
dediğinde kelimeler bitişik olmadığı için yerleşmiyor; "bekleyen" modele kalıyor ve iş kuralı
metni modeli adede çekiyor (85.688 adet, oysa tutar 18.062.204,75).

Kuru koşu varsayılan; --apply ile yazar. Store API + human_certify (gece motoru geri almasın).
"""
import datetime, os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
from semantic_layer.normalize import normalize_term

CID = "sem_6c91092af708"
WHO = "operator:claude (iş kararı 2026-09-21)"
TERMS = ["bekleyen toplam tutar", "bekleyen sipariş toplamı"]

st = open_store(os.environ["SEMANTIC_STORE_DSN"])
c = st.get_concept(CID)
if c is None:
    raise SystemExit(f"kavram yok: {CID}")
print("ÖNCE :", c.term, c.status, "synonyms=", list(c.synonyms))
print("EKLENECEK:", TERMS)
if "--apply" not in sys.argv:
    raise SystemExit("KURU KOŞU — yazılmadı. Uygulamak için: --apply")

for t in TERMS:
    st.add_synonym(CID, t)
c = st.get_concept(CID)
ex = dict(c.explain or {})
src = dict(ex.get("synonym_sources") or {})
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
for t in TERMS:
    src[normalize_term(t)] = {"by": WHO, "source": "answer-gate Q29: ölçü yerleşmeyince adet dönüyordu", "at": now}
st.update_concept(CID, explain={
    "synonym_sources": src,
    "declared_synonyms": sorted(set(ex.get("declared_synonyms") or []) | {normalize_term(t) for t in TERMS})})
st.add_evidence(Evidence(CID, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:bekleyen-toplam",
                         support_count=1, weight=1.0,
                         payload={"snippet": "eş anlamlı: bekleyen toplam tutar → bekleyen sipariş tutarı", "by": WHO}))
c = st.get_concept(CID)
print("SONRA:", c.term, c.status, "synonyms=", list(c.synonyms))
