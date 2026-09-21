"""Q51: "önerilen telif oranı" kavramı YANLIŞ alana bağlı.

Bugün `sem_3f7cd5c208f4` → `NEW_PROJEBASE.new_olasitelif`. Ama o alanın adı "Olası Telif Oranı";
"önerilen" olan, yayın kurulu toplantısında önerilen orandır ve ayrı bir tabloda durur.

Canlı ölçüm (2026-09-21, CRM .28):
  new_yayinkurulutoplantilariBase.new_onerilenteliforani → 31 kayıt, ortalama %5,645  (altın referans: %5,64)
  new_projeBase.new_olasitelif                            → 202 kayıt, ortalama %6,06  (köprünün bugünkü yanlış cevabı %5,96)

Eşlemeye dokunulmaz (alan gerçekten "olası telif"tir); terim daraltılır ve doğru kavram eklenir.
Kuru koşu varsayılan; --apply ile yazar.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping, SemanticType, ConceptStatus, Evidence, EvidenceType
from semantic_layer.evidence.engine import EvidenceEngine

WHO = "operator:claude (iş kararı 2026-09-21)"
OLD_ID = "sem_3f7cd5c208f4"
ENTITY, PATTERN, COLUMN = "NEW_YAYINKURULUTOPLANTILARIBASE", "NEW_YAYINKURULUTOPLANTILARIBASE", "new_onerilenteliforani"
REASON = ("yayın kurulu toplantısında önerilen telif oranı; canlı ölçüm 31 kayıt / ortalama %5,645. "
          "NEW_PROJEBASE.new_olasitelif 'olası' telif oranıdır (202 kayıt / %6,06), başka bir şeydir.")

st = open_store(os.environ["SEMANTIC_STORE_DSN"])
old = st.get_concept(OLD_ID)
print("DARALTILACAK:", (old.term if old else "?"), "→ 'olası telif oranı'  (eşleme aynı: NEW_PROJEBASE.new_olasitelif)")
print("EKLENECEK   : 'önerilen telif oranı' →", f"{ENTITY}.{COLUMN}")
if "--apply" not in sys.argv:
    raise SystemExit("KURU KOŞU — yazılmadı. Uygulamak için: --apply")

if old is not None and old.term != "olası telif oranı":
    st.rename_concept(OLD_ID, "olası telif oranı")
    print("daraltıldı:", st.get_concept(OLD_ID).term)

m = Mapping(concept_id="", entity=ENTITY, table_pattern=PATTERN, column=COLUMN, operator="COLUMN")
c, created = st.upsert_concept("default", "logo", "önerilen telif oranı", SemanticType.COLUMN,
                               mapping=m, status=ConceptStatus.CANDIDATE)
st.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-21:onerilen-telif",
                         support_count=1, weight=1.0, payload={"snippet": REASON, "by": WHO}))
EvidenceEngine(st).human_certify(c.id, WHO, reason=REASON)
c = st.get_concept(c.id)
print("YAZILDI:", c.id, c.term, c.status, "| yeni mi:", created)
