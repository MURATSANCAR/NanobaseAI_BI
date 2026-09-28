"""Öneri 15/16/17/19 kabulünün bıraktığı izler.

- `kabul.py` yazma ucu çağırmaz; `--gece` ile koşan iki gece turu ürün verisi üretir (etiket, özet, uyarı) — test verisi
  değildir, silinmez.
- Ekran denemesinde (telefon/masaüstü) kabul oturumunun (varsayılan timasai) kişisel «Bugün» önbelleği
  (`semantic_today_briefs`) silinir: kişiye ait, bir sonraki açılışta yeniden yazılır.
- Değişiklik kaydı (`semantic_audit`): gerçek hesabın (timasai) satırları AGENTS.md kuralı gereği **silinmez**; `--since`
  sonrası bu işlerin (not_sinyali_ozet, okur_sesi_uyari, marketing_plan hedef açığı paragrafı) kimlik aralığı yazılır,
  günlüğe geçirilir. Uydurma bir hesap adıyla yazılmış satır varsa (`--actor` timasai değilse) silinir.
- «Görüldü» işaretlenen baskı hatası uyarısı `--geri-al <anahtar,…>` ile yeniden «açık» yapılır (deneme işaretlemesi).

Kullanım: temizlik.py --since 2026-09-28T10:00:00+00:00 [--actor timasai] [--geri-al K1,K2] [--dry]
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("ZK_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--since", required=True)
ap.add_argument("--actor", default="timasai")
ap.add_argument("--geri-al", dest="undo", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
since = datetime.fromisoformat(a.since)
settings = SemanticSettings.from_env()
eng = open_store(settings.store_dsn).engine
insp = sa.inspect(eng)
kinds = ["not_sinyali_ozet", "okur_sesi_uyari"]
out: dict[str, object] = {}
with eng.begin() as c:
    if insp.has_table("semantic_today_briefs"):
        T = sa.Table("semantic_today_briefs", sa.MetaData(), autoload_with=eng)
        cond = [T.c.kullanici == a.actor.lower()]
        out["bugün önbelleği"] = c.execute(sa.select(sa.func.count()).select_from(T).where(*cond)).scalar()
        if not a.dry:
            c.execute(T.delete().where(*cond))
    if insp.has_table("semantic_audit"):
        AU = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
        cond = [AU.c.kind.in_(kinds), AU.c.actor == a.actor, AU.c.at >= since]
        ids = [r[0] for r in c.execute(sa.select(AU.c.id).where(*cond).order_by(AU.c.id))]
        out["değişiklik kaydı"] = f"{len(ids)} satır" + (f", kimlik {ids[0]}–{ids[-1]}" if ids else "")
        if a.actor != "timasai" and not a.dry:
            c.execute(AU.delete().where(*cond))
            out["değişiklik kaydı"] = f"{len(ids)} satır silindi (uydurma hesap)"
    keys = [k for k in a.undo.split(",") if k]
    if keys and insp.has_table("semantic_reader_voice_alerts"):
        AL = sa.Table("semantic_reader_voice_alerts", sa.MetaData(), autoload_with=eng)
        cond = [AL.c.urun_anahtar.in_(keys), AL.c.goren == a.actor]
        out["görüldü geri alındı"] = c.execute(sa.select(sa.func.count()).select_from(AL).where(*cond)).scalar()
        if not a.dry:
            c.execute(AL.update().where(*cond).values(durum="acik", goren=None, gorulme=None))
for k, v in out.items():
    print(f"{k}: {v}")
print("kuru koşu (hiçbir şey silinmedi)" if a.dry else "tamam")
