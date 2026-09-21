"""'Sabit kıymet' terimi bugün STLINE.LINETYPE=8'e (sabit kıymet SATIRI) bağlı ve
"sabit kıymetlerimiz ne kadar" sorusuna 3.469.868 ₺ diyor; gerçek sabit kıymet kayıtları
FAREGIST'te, giriş maliyeti 99.504.559 ₺ — yani 29 kat yanlış, üstelik kapıdan sessizce geçiyor.

Eşleme yanlış değil (LINETYPE=8 gerçekten sabit kıymet satırıdır, kardeşi LINETYPE=4 katalogda
zaten 'hizmet satırı' adıyla duruyor); kusur terimin genişliğinde. Terim daraltılır, eşlemeye
dokunulmaz. Boşalan anahtarı parti 1'in FAREGIST kavramları doldurur.

Kuru koşu varsayılan; --apply ile yazar.
"""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store

WHO = "operator:claude (iş kararı 2026-09-21)"
OLD_ID = "sem_6e4f6a20811d"          # 'sabit kiymet' → STLINE.LINETYPE (CERTIFIED)
NEW_TERM = "sabit kıymet satırı"

st = open_store(os.environ["SEMANTIC_STORE_DSN"])
c = st.get_concept(OLD_ID)
if c is None:
    raise SystemExit(f"kavram yok: {OLD_ID}")
m = st.list_mappings(OLD_ID)
print("ÖNCE :", c.term, "|", c.status, "|", (m[0].entity if m else "-"), (m[0].column if m else ""))
print("SONRA:", NEW_TERM, "(eşleme aynı kalır; 'sabit kıymet' anahtarı FAREGIST kavramlarına açılır)")
if "--apply" not in sys.argv:
    raise SystemExit("KURU KOŞU — yazılmadı. Uygulamak için: --apply")

st.rename_concept(OLD_ID, NEW_TERM)
c = st.get_concept(OLD_ID)
print("YAZILDI:", c.term, "| normalized:", c.normalized_term, "| status:", c.status)
