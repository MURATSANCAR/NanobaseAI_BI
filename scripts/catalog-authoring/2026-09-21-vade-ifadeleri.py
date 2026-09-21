"""Muhasebe testi M015/M027: 'vadesi geçmiş müşteri alacakları', 'vadesi gelmiş satıcı borçları' — 'vade tarihi'
(PAYTRANS.DATE_) kavramı var ama bu söylenişler yok; çözücü veriden TG_RAPOR.VADESI / AA_CAR_EKSTRE rapor tablolarını
buluyordu. İki kelimelik öbekler eklenir (tek kelime yok). Kuru koşu varsayılan; --apply yazar."""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
WHO = "operator:claude (muhasebe testi, 2026-09-21)"
ADD = {
    "sem_20a502bb7f6a": ["vadesi geçmiş", "vadesi geçen", "vadesi gelmiş", "vadesi gelen", "vadesi gelmemiş"],
}
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
for cid, terms in ADD.items():
    print("ÖNCE :", cid, st.get_concept(cid).term, list(st.get_concept(cid).synonyms))
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
for cid, terms in ADD.items():
    for t in terms: st.add_synonym(cid, t)
    st.add_evidence(Evidence(cid, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:vade-ifadeleri", support_count=1,
        weight=1.0, payload={"snippet": "vade tarihinin doğal söylenişleri (FIFO yaşlandırma PAYTRANS.DATE_ üzerinden): " + ", ".join(terms), "by": WHO}))
    print("SONRA:", cid, st.get_concept(cid).synonyms)
