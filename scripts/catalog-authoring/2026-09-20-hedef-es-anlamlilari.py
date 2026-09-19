import sys, os, datetime
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
from semantic_layer.normalize import normalize_term
CID, WHO = "sem_8424f510c61f", "operator:claude (iş teyidi bekliyor)"
TERMS = ["hedef", "satış hedefi", "toplam hedef"]
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
c = st.get_concept(CID)
print("ÖNCE :", c.term, c.status, "synonyms=", list(c.synonyms))
if "--apply" in sys.argv:
    for t in TERMS:
        st.add_synonym(CID, t)
    c = st.get_concept(CID)
    ex = dict(c.explain or {})
    src = dict(ex.get("synonym_sources") or {})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for t in TERMS:
        src[normalize_term(t)] = {"by": WHO, "source": "answer-gate Q65/Q69: 'hedefi olan' kolona bağlanamıyordu", "at": now}
    st.update_concept(CID, explain={"synonym_sources": src,
                                    "declared_synonyms": sorted(set(ex.get("declared_synonyms") or []) | {normalize_term(t) for t in TERMS})})
    st.add_evidence(Evidence(CID, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-20:hedef", support_count=1, weight=1.0,
                             payload={"snippet": "eş anlamlı: hedef / satış hedefi / toplam hedef → NEW_TOPLAMHEDEF", "by": WHO}))
    c = st.get_concept(CID)
    print("SONRA:", c.term, c.status, "synonyms=", list(c.synonyms))
