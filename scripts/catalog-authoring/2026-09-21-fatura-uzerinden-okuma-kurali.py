"""Arşiv P100: satır (STLINE) ölçüsü teslimat/temsilci/ödeme planına göre kırılınca derleyici yolu seçemiyordu —
STLINE'dan LG_SHIPINFO'ya fatura (INVOICE) ve irsaliye (STFICHE) üzerinden iki eşit yol var; derleyici bu
durumda bilerek reddeder ("rakip yollar anlamsal seçim ister"). 2026-09-09 son kullanıcı kaydı seçimi yazmıştı
(definition_source: "invoice customer / invoice salesperson for invoice-based sales reporting", "line-specific
plan when nonzero, otherwise invoice plan") ama yalnız 'teslimat şehri' ve 'fatura ödeme planı' kavramlarında;
çözücü aynı kolonun eş kavramını ('gönderim şehri', 'satış temsilcisi', 'ödeme planı') seçince kural kayboluyordu.
Aynı kural aynı kolonun bütün eşlemelerine yazılır. Kuru koşu varsayılan; --apply."""
import os, sys, dataclasses
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Evidence, EvidenceType
import sqlalchemy as sa
WHO = "operator:claude (arşiv P100, 2026-09-21)"
VIA = {"via": "INVOICE", "via_key": "LOGICALREF", "via_column": "INVOICEREF", "target_column": "LOGICALREF"}
RULES = {  # hedef varlık → STLINE için okuma kuralı
    "LG_SHIPINFO": {**VIA, "fallback_column": "SHIPINFOREF"},
    "LG_SLSMAN": {**VIA, "fallback_column": "SALESMANREF"},
    "PAYPLANS": {**VIA, "fallback_column": "PAYDEFREF", "primary_column": "PAYDEFREF"},
}
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
with st.engine.connect() as c:
    rows = c.execute(sa.text("""select distinct m.concept_id from sl_mapping m join sl_concept c on c.id = m.concept_id
        where m.entity in ('LG_SHIPINFO','LG_SLSMAN','PAYPLANS') and m.column_name in ('CITY','TOWN','COUNTRY','DEFINITION_')
          and c.status = 'CERTIFIED'""")).fetchall()
plan = []
for (cid,) in rows:
    con, ms = st.get_concept(cid), st.list_mappings(cid)
    new = []
    for m in ms:
        rule = RULES.get(m.entity)
        have = ((m.extra or {}).get("reference_resolution") or {}).get("STLINE")
        if rule and have != rule:
            ex = dict(m.extra or {}); ex["join_kind"] = "LEFT"; ex["reference_resolution"] = {**(ex.get("reference_resolution") or {}), "STLINE": rule}
            new.append(dataclasses.replace(m, extra=ex))
        else:
            new.append(m)
    if new != ms:
        plan.append((con, new))
        print(f"{cid} '{con.term}': {[f'{m.entity}.{m.column}' for m in ms]} ← STLINE fatura üzerinden")
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
for con, new in plan:
    st.replace_mappings(con.id, new)
    st.add_evidence(Evidence(con.id, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:fatura-uzerinden", support_count=1, weight=1.0,
        payload={"snippet": "satır ölçüsünde bu bilgi faturadan okunur (fatura bazlı satış raporlaması, 09-09 son kullanıcı tanımı)", "by": WHO}))
    print("YAZILDI:", con.id, con.term, st.get_concept(con.id).status)
