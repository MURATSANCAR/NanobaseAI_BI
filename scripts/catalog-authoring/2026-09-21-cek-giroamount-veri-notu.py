"""Muhasebe testi M059 — 2026-09-21. CSCARD.GIROAMOUNT hiç dolmuyor; açıklaması "Ciro tutarı" olduğu için
"ciro edilen çeklerin tutarı" bu kolona gidip 0 dönüyordu (gerçek 539,1 Mn / bu yıl 158,1 Mn).
Eski notun ardılı: Kolon düzeyi VERİ NOTU beyanı (şema açıklaması olarak).

Ölçüm (salt-okunur, 2026-09-20): LG_211_01_ORFLINE + LG_411_01_ORFLINE malzeme satırlarında DUEDATE dolu olan
~762 bin satırın 2'si dışında hepsinde DUEDATE = DATE_ (sipariş tarihi). ORGDUEDATE %93+ boş. Gerçek termin tutulmuyor.
Köprü (column_facts.predicate_column_notes) "VERİ NOTU:" ile başlayan kolon açıklamasını, o kolona koşul/kırılım
dayandıran her cevabın özetine ve dataNotes alanına taşır. CRM termin alanları için beyan GEREKMEZ: profil
null_ratio=1.0 ölçüyor, not ölçümden gelir.

Kullanım (sunucuda):  SEMANTIC_STORE_DSN=… python apply.py            → KURU koşu (varsayılan)
                      SEMANTIC_STORE_DSN=… python apply.py --apply    → yazar (yalnız ana oturum)
"""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Annotation

WHO = "operator:claude (muhasebe testi, 2026-09-21)"
ENTITY, COLUMN = "CSCARD", "GIROAMOUNT"
TEXT = ("VERİ NOTU: Bu alan kullanılmıyor — 2021–2026 bütün çek/senet kartlarında (12.257 kayıt) 0. "
        "Ciro edilen çeklerin tutarı AMOUNT kolonundadır; ciro durumu CURRSTAT = 2 ile seçilir.")

st = open_store(os.environ["SEMANTIC_STORE_DSN"])
import sqlalchemy as sa
with st.engine.connect() as c:
    ds = os.environ.get("SEMANTIC_DATASOURCE_ID") or c.execute(sa.text(
        "select datasource_id from sl_schema_profile group by 1 order by count(*) desc limit 1")).scalar()
patterns = sorted({p.table_pattern for p in st.list_profiles(ds)
                   if (p.entity or "").upper().replace("LG_", "") == ENTITY and p.column(COLUMN) is not None
                   and p.table_name.upper().startswith("LG_")})
print("datasource:", ds, "| hedef kalıplar:", patterns)
for pat in patterns:
    for a in st.list_annotations(ds, pat):
        if (a.column or "").upper() == COLUMN:
            print("  MEVCUT açıklama:", a.id, a.author, "|", a.text[:120])
print("YAZILACAK (", WHO, "):\n ", TEXT)
if "--apply" not in sys.argv:
    print("KURU KOŞU — hiçbir şey yazılmadı. Yazmak için --apply. Sonrasında köprü açıklamaları yeniden yükler (yeniden başlatma / katalog yenileme).")
    sys.exit(0)
for pat in patterns:
    ann = st.add_annotation(Annotation(datasource_id=ds, table_pattern=pat, column=COLUMN, text=TEXT, author=WHO))
    print("yazıldı:", pat, ann.id)
