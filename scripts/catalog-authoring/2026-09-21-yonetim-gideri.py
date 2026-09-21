"""Muhasebe testi M081: 'Genel yönetim giderlerimiz' → 7'li hesap toplamı (65,3 Mn), doğrusu 770 (54,1 Mn).
Kök neden: 'genel' durak kelime listesinde ('genel olarak'); çözücü sorudan atıyor, geriye kalan
'yönetim gideri' katalogdaki 'genel yönetim gideri' anahtarıyla eşleşmiyor. İki kelimelik öbek
eş anlamlısı eklenir. Kuru koşu varsayılan; --apply ile yazar."""
import datetime, os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
from semantic_layer.normalize import normalize_term
CID, WHO = "sem_3d2495e274f8", "operator:claude (muhasebe testi, 2026-09-21)"
TERMS = ["yönetim gideri", "yönetim giderleri"]
st = open_store(os.environ["SEMANTIC_STORE_DSN"]); c = st.get_concept(CID)
print("ÖNCE :", c.term, list(c.synonyms))
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
for t in TERMS: st.add_synonym(CID, t)
st.add_evidence(Evidence(CID, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:yonetim-gideri", support_count=1, weight=1.0,
    payload={"snippet": "'genel' durak kelimesi sorudan düşünce kalan 'yönetim gideri' öbeği", "by": WHO}))
print("SONRA:", st.get_concept(CID).synonyms)
