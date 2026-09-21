"""Arşiv P100: 'teslimat şehri bazında' kırılımı derlenemiyordu ("group column on SHIPINFO cannot be joined
to STLINE"). Teslimat kavramları VW_{n}_SHIPINFO görünümüne (varlık SHIPINFO) bağlıydı; fatura/satır ilişkisi
ise Logo sözlüğünden gerçek tabloya (varlık LG_SHIPINFO, INVOICE.SHIPINFOREF → LOGICALREF) çözülüyor.
Ölçüm (doğrudan DB, 2026-09-21): VW_411_SHIPINFO 370.467 satır = LG_411_SHIPINFO'nun alt kümesi, CITY birebir;
VW_211_SHIPINFO 0 satır — görünüm üzerinden 2021–25 teslimat şehri hep boş gelir. Bütün SHIPINFO eşlemeleri
aynı kolonla LG_SHIPINFO'ya taşınır; 'teslimat şehri' (DISCOVERED) sertifikalanır. Kuru koşu varsayılan; --apply."""
import os, sys, dataclasses
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
from semantic_layer.evidence.engine import EvidenceEngine
import sqlalchemy as sa
WHO = "operator:claude (arşiv P100, 2026-09-21)"
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
pat = next(p.table_pattern for p in st.list_profiles("logo") if (p.entity or "").upper() == "LG_SHIPINFO")
with st.engine.connect() as c:
    ids = [r[0] for r in c.execute(sa.text("select distinct concept_id from sl_mapping where entity = 'SHIPINFO'"))]
plan = []
for cid in ids:
    con = st.get_concept(cid)
    ms = st.list_mappings(cid)
    new = [dataclasses.replace(m, entity="LG_SHIPINFO", table_pattern=pat,
                               formula=(m.formula or None) and m.formula.replace("SHIPINFO.", "LG_SHIPINFO.")) if m.entity == "SHIPINFO" else m for m in ms]
    plan.append((con, ms, new))
    print(f"{cid} '{con.term}' {con.status}: " + "; ".join(f"{m.entity}.{m.column} → {n.entity}.{n.column}" for m, n in zip(ms, new)))
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
eng = EvidenceEngine(st)
for con, ms, new in plan:
    st.replace_mappings(con.id, new)
    reason = "teslimat bilgisi gerçek tablo LG_SHIPINFO'dan okunur (INVOICE.SHIPINFOREF ilişkisi; VW_211_SHIPINFO boş)"
    st.add_evidence(Evidence(con.id, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:shipinfo", support_count=1, weight=1.0, payload={"snippet": reason, "by": WHO}))
    if con.term == "teslimat şehri" and str(con.status).endswith("DISCOVERED"):
        eng.human_certify(con.id, WHO, reason=reason)
    print("YAZILDI:", con.id, con.term, st.get_concept(con.id).status)
