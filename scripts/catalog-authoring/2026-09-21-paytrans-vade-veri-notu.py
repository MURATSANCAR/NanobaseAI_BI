"""Muhasebe testi M015/M016/M027/M028 — 2026-09-21. Vade/yaşlandırma soruları yalnız yaklaşık cevaplanabilir:
PAYTRANS'ta ödeme kapama yok. Kolon düzeyi VERİ NOTU, PAYTRANS.DATE_'e koşul/kırılım dayandıran her cevabın özetine
ve dataNotes alanına taşınır (column_facts.predicate_column_notes). Kuru koşu varsayılan; --apply yazar."""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Annotation

WHO = "operator:claude (muhasebe testi, 2026-09-21)"
ENTITY, COLUMN = "PAYTRANS", "DATE_"
TEXT = ("VERİ NOTU: Vade tarihi. Logo'da ödeme kapama kullanılmıyor — 116.514 ödeme planı satırının yalnız 14'ünde "
        "ödenen tutar dolu, kapatan ödeme bağlantısı (CROSSREF) yok. Bu tablodan hesaplanan açık, vadesi geçmiş ve "
        "yaşlandırma tutarları FIFO yaklaşımıdır (bakiye en yeni vadelerden geriye dağıtılır), kesin değildir.")

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
