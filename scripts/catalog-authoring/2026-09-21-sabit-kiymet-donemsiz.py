"""Muhasebe testi M090/M091/M094: sabit kıymet ölçülerine varsayılan yıl basılıyordu.

Parti 1'in FAREGIST ölçüleri (giriş maliyeti = INVALUE, amortisman = ACCUMDEPR) olay ölçüsü gibi
işaretliydi. FAREGIST'te alım tarihi (DATEIN) olduğu için çözücü 'dönem söylenmedi → bu yıl' uyguladı:
  M091 birikmiş amortisman 340.063 (doğru 30,3 Mn) · sabit kıymet maliyeti 2,7 Mn (doğru 94,2 Mn) ·
  M094 'amortismanı bitmiş kıymetler' → yalnız 2026'da alınanlar (tanım gereği ~hiç).
Sabit kıymet sicili ANLIK bir listedir; maliyet ve birikmiş amortisman bir karttaki değerdir, dönem
içinde gerçekleşen olay değil. Çözücüde bunun için hazır işaret var: extra.undated ("a cost on a card,
not an event"). Açık dönem ('bu yıl alınan …') yine uygulanır; yalnız VARSAYILAN yıl kalkar.
Kuru koşu varsayılan; --apply ile yazar."""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping, Evidence, EvidenceType
WHO = "operator:claude (muhasebe testi, 2026-09-21)"
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
hedef = []
for c in st.find_concepts("default", "logo", limit=100000):
    if str(getattr(c.status, "value", c.status)) != "CERTIFIED": continue
    if str(getattr(c.semantic_type, "value", c.semantic_type)) != "METRIC": continue
    ms = st.list_mappings(c.id)
    if any((m.entity or "").upper().endswith("FAREGIST") for m in ms):
        hedef.append((c, ms))
for c, ms in hedef:
    print("ÖLÇÜ:", c.id, c.term, "|", [(m.formula, (m.extra or {}).get("undated")) for m in ms])
if "--apply" not in sys.argv: raise SystemExit("KURU KOŞU")
for c, ms in hedef:
    yeni = []
    for m in ms:
        ex = dict(m.extra or {}); ex["undated"] = True
        yeni.append(Mapping(concept_id=c.id, entity=m.entity, table_pattern=m.table_pattern, column=m.column,
                            operator=m.operator, values=list(m.values or []), formula=m.formula,
                            time_primitive=m.time_primitive, extra=ex))
    st.replace_mappings(c.id, yeni)
    st.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:sabit-kiymet-donemsiz", support_count=1, weight=1.0,
        payload={"snippet": "sabit kıymet sicili anlık listedir; maliyet/amortisman kart değeridir, olay değil → varsayılan yıl uygulanmaz (extra.undated)", "by": WHO}))
    print("YAZILDI:", c.term, [(m.extra or {}).get("undated") for m in st.list_mappings(c.id)])
