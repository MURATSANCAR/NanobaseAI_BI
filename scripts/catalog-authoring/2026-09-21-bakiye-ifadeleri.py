"""Muhasebe testi M003/M004 ailesi: bakiye soruları ölçüye bağlanmıyordu.
'102 Bankalar hesabının bugünkü bakiyesi' — 'bugünkü' öbeği böldüğü için 'bank baki' anahtarı tutmuyor,
'bankalar hesabı' tek başına hiçbir ölçüde yok. 'Müşterilerin borç bakiyesi' — 120 ölçüsünde 'müşteri'
ile başlayan öbek yok. Çok kelimeli öbekler eklenir (tek kelime yok). Kuru koşu varsayılan; --apply yazar."""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
WHO = "operator:claude (muhasebe testi, 2026-09-21)"
ADD = {
    "sem_7f3e9ed8eb79": ["bankalar hesabı", "banka hesabı", "bankalar hesabı bakiyesi"],
    "sem_a42781dc25eb": ["müşteri bakiyesi", "müşteri borç bakiyesi", "müşterilerin borç bakiyesi",
                         "alıcılar borç bakiyesi"],
    "sem_c77b2fdb93c1": ["satıcılar alacak bakiyesi", "tedarikçi bakiyesi", "tedarikçi borç bakiyesi"],
    "sem_cc9f112ce3bd": ["vergi ve fonlar", "ödenecek vergi ve fonlar"],
}
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
for cid, terms in ADD.items():
    print("ÖNCE :", cid, st.get_concept(cid).term, list(st.get_concept(cid).synonyms))
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
for cid, terms in ADD.items():
    for t in terms: st.add_synonym(cid, t)
    st.add_evidence(Evidence(cid, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:bakiye-ifadeleri", support_count=1,
        weight=1.0, payload={"snippet": "bakiye sorusunun doğal söylenişleri: " + ", ".join(terms), "by": WHO}))
    print("SONRA:", cid, st.get_concept(cid).synonyms)
