"""Eksik tamamlama kabulünün bıraktıklarını siler (`kabul.py --out` dosyasıyla):

- finansal denetim açıklama/küme dosyaları (`FINANCIAL_AUDIT_DATA_DIR/<rapor>-<kontrol>.{explain,clusters}.json`),
- telif koşu özeti (`semantic_royalty_runs.ozet_json.anlatim` anahtarı; koşunun kendisine dokunulmaz),
- SEO önerisi ve hedef sorgu kaydı (yalnız kabulün yarattığı öneri; önceden bekleyen öneri yenisiyle silindiyse geri
  getirilemez — kimliği ekrana yazılır).

Hak haritası ve ihale risk işaretleri uygulama çıktısıdır (onay/karar verilmedi), silinmez. Değişiklik kaydı
(`semantic_audit`) gerçek hesabın izidir, silinmez.
Kullanım: temizlik.py --ids-file /tmp/claude-ze/kabul-kimlikler.json [--dry]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("ZK_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", required=True)
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = json.load(open(a.ids_file))
eng = open_store(SemanticSettings.from_env().store_dsn).engine
root = Path(os.environ.get("FINANCIAL_AUDIT_DATA_DIR", "/data/nanobaseai/bi/var/financial-audit/workpapers"))

files = [root / n for n in ids.get("auditFiles", []) if "/" not in n and n.endswith((".explain.json", ".clusters.json"))]
for p in files:
    if p.exists() and not a.dry:
        p.unlink()
print(("(deneme) " if a.dry else "") + "silinen denetim dosyası:", [p.name for p in files])

meta = sa.MetaData()
runs = sa.Table("semantic_royalty_runs", meta, autoload_with=eng)
props = sa.Table("semantic_seo_proposals", meta, autoload_with=eng)
targets = sa.Table("semantic_seo_proposal_targets", meta, autoload_with=eng)
with eng.begin() as c:
    for rid in ids.get("runNote", []):
        oz = c.execute(sa.select(runs.c.ozet_json).where(runs.c.id == rid)).scalar()
        oz = oz if isinstance(oz, dict) else json.loads(oz or "{}")
        if "anlatim" in oz and not a.dry:
            oz.pop("anlatim")
            c.execute(runs.update().where(runs.c.id == rid).values(ozet_json=oz))
    print("koşu özeti silinen koşu:", ids.get("runNote", []))
    for p in ids.get("seoProposal", []):
        if not a.dry:
            c.execute(targets.delete().where(targets.c.proposal_id == p["id"]))
            c.execute(props.delete().where(props.c.id == p["id"], props.c.status == "hazir"))
        print("SEO önerisi silindi:", p["id"], "ürün", p["product"], "— kabulden önce üründe olan öneriler:", p.get("had"))
