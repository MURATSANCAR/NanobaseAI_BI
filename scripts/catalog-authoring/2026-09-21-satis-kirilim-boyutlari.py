"""Arşiv P100 (müşteri/ürün/ödeme planı/satış temsilcisi/teslimat şehri/birim bazında satış): 100 sorunun hepsi
model yoluna düşüyor, model 'ödeme planı'nı TSOFT_KAMPANYA'ya, 'satış temsilcisi'ni ESP_KULLANICIGRUP'a bağlıyordu.
Üç kırılım kavramı katalogda vardı ama sertifikasızdı (DISCOVERED/CANDIDATE) ve eşlemeleri eksikti:
  ödeme planı      → PAYPLANS.DEFINITION_   (INVOICE/STLINE.PAYDEFREF → PAYPLANS, şemada ilişki var)
  satış temsilcisi → LG_SLSMAN.DEFINITION_  (INVOICE/STLINE.SALESMANREF → LG_SLSMAN; eski eşleme 'SLSMAN' profilsiz)
  birim            → UNITSETL.NAME          (STLINE.UOMREF → UNITSETL; arşivdeki SQL NAME okuyor, eski eşleme CODE)
Kuru koşu varsayılan; --apply ile yazar."""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping, Evidence, EvidenceType
from semantic_layer.evidence.engine import EvidenceEngine
WHO = "operator:claude (arşiv P100, 2026-09-21)"
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
profs = st.list_profiles("logo")
def pat(entity): return next(p.table_pattern for p in profs if (p.entity or "").upper() == entity)
D = [("sem_67c4c7d15941", "PAYPLANS", "DEFINITION_", ["ödeme planı adı"]),
     ("sem_c519db21f6e5", "LG_SLSMAN", "DEFINITION_", ["satış temsilcisi adı", "satış temsilcileri"]),
     ("sem_b68a6f9b4071", "UNITSETL", "NAME", ["birim adı", "ölçü birimi"])]
for cid, ent, col, syn in D:
    c = st.get_concept(cid)
    print(f"{cid} '{c.term}' {c.status} → {ent}.{col} ({pat(ent)}) eş: {syn}")
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
eng = EvidenceEngine(st)
for cid, ent, col, syn in D:
    st.replace_mappings(cid, [Mapping(concept_id=cid, entity=ent, table_pattern=pat(ent), column=col)])
    for s in syn: st.add_synonym(cid, s)
    reason = f"satış kırılım boyutu {ent}.{col}; arşiv P100 SQL'leriyle aynı kolon, şemada ilişki mevcut"
    st.add_evidence(Evidence(cid, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:satis-kirilim", support_count=1, weight=1.0, payload={"snippet": reason, "by": WHO}))
    eng.human_certify(cid, WHO, reason=reason)
    c = st.get_concept(cid); print("YAZILDI:", cid, c.term, c.status, c.synonyms)
