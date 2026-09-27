"""K4 (müşteri VM'i, 2026-09-25): "2026 ağustos toplam kdvli satış tutarı" dört kez soruldu, üç ayrı cevap aldı
(161,4 Mn, 87,9 Mn, 171,1 Mn). Katalogda KDV'li satış ölçüsü yoktu; "kdvli" çözülmeyince soru modele gitti ve
model her seferinde başka formül yazdı (TOTAL+VATAMNT iskonto öncesi brüttür).

Ölçüm (.155, Ağustos 2026, TRCODE 7-8-9):
  fatura NETTOTAL                       87.893.832,55
  satır VATMATRAH + VATAMNT (tüm satır) 87.893.832,61   ← aynı tutar: NETTOTAL KDV dahil net fatura tutarıdır
  satır LINENET (satış tutarı)          87.674.133,53   ← KDV hariç, iskonto sonrası
  fatura TOTALVAT                          140.016,76   (kitap satışının büyük kısmı %0 KDV)

İş kararı (kararlar Claude'a bırakıldı, veriyle): KDV'li satış tutarı = faturanın NETTOTAL'i, fatura bazlı "satış
tutarı" (sem_67d025bf42fb) ile aynı kapsam ve koşul. KDV hariç / KDV'siz satış tutarı = satır bazlı satış tutarı
(sem_b62a0c853395, LINENET). Kuru koşu varsayılan; --apply ile yazar."""
import datetime, os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping, SemanticType, ConceptStatus, Evidence, EvidenceType
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.normalize import normalize_term

WHO = "operator:claude (K4 müşteri sohbeti, 2026-09-27)"
INVOICE_SALES, LINE_SALES = "sem_67d025bf42fb", "sem_b62a0c853395"
TERM = "kdvli satış tutarı"
SYNONYMS = ["kdv dahil satış tutarı", "kdvli satış", "kdv dahil satış", "kdvli ciro", "kdv dahil ciro",
            "vergiler dahil satış tutarı"]
EXCLUSIVE = ["kdvsiz satış tutarı", "kdv hariç satış tutarı", "kdvsiz ciro", "kdv hariç ciro"]

st = open_store(os.environ["SEMANTIC_STORE_DSN"])
base = st.list_mappings(INVOICE_SALES)[0]
extra = dict(base.extra or {})
extra["aliases"] = ["kdvli_satis_tutari"]
mapping = Mapping(concept_id="", entity=base.entity, table_pattern=base.table_pattern, formula=base.formula, extra=extra)
print("YENİ  :", TERM, "|", mapping.entity, mapping.formula, mapping.extra)
print("  eş  :", SYNONYMS)
print("EKLE  :", st.get_concept(LINE_SALES).term, st.list_mappings(LINE_SALES)[0].formula, "←", EXCLUSIVE)
if "--apply" not in sys.argv:
    raise SystemExit("KURU KOŞU — yazılmadı. Uygulamak için: --apply")

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
eng = EvidenceEngine(st)


def note(cid: str, text: str) -> None:
    st.add_evidence(Evidence(cid, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-27:kdvli-satis", support_count=1,
                             weight=1.0, payload={"snippet": text, "by": WHO}))


def synonyms(cid: str, terms: list[str], why: str) -> None:
    for t in terms:
        st.add_synonym(cid, t)
    c = st.get_concept(cid)
    ex = dict(c.explain or {})
    src = dict(ex.get("synonym_sources") or {})
    for t in terms:
        src[normalize_term(t)] = {"by": WHO, "source": why, "at": now}
    st.update_concept(cid, explain={"synonym_sources": src,
                                    "declared_synonyms": sorted(set(ex.get("declared_synonyms") or []) | {normalize_term(t) for t in terms})})


c, created = st.upsert_concept("default", "logo", TERM, SemanticType.METRIC, mapping=mapping, status=ConceptStatus.CANDIDATE)
if not created:
    st.replace_mappings(c.id, [mapping])
synonyms(c.id, SYNONYMS, "K4: kdvli satış tutarı modele gidiyor, üç ayrı cevap")
note(c.id, "KDV dahil satış tutarı = fatura NETTOTAL (7-8-9); Ağustos 2026 87.893.832,55 = satır VATMATRAH+VATAMNT")
eng.human_certify(c.id, WHO, reason="K4: KDV'li satış ölçüsü, .155 üzerinde iki bağımsız yoldan aynı tutar")
synonyms(LINE_SALES, EXCLUSIVE, "K4: KDV hariç satış tutarı satır LINENET'tir")
note(LINE_SALES, "KDV hariç satış tutarı = satır LINENET (iskonto sonrası, KDV hariç)")
print("YAZILDI:", c.id, st.get_concept(c.id).status, st.get_concept(c.id).synonyms, "|", st.get_concept(LINE_SALES).synonyms)
