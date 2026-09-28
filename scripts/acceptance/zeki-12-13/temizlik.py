"""Öneri 12/13 kabulünün bıraktığı kayıtları siler: sentetik başvuru (kayıt, dosyalar, değerlendirme, günlük, yazışma,
kurul raporu, ön okumalar) ve diskteki dosyaları; kabulde başlatılan ön okuma kayıtları (gerçek başvuruda yalnız ön
okuma satırı); sözleşme belgesi okuması ve diskteki belgesi. Değişiklik kaydı (`semantic_audit`) gerçek hesabın izi
olduğu için silinmez. Silinen sayılar ekrana yazılır.

Kullanım: temizlik.py --ids-file /tmp/claude-zeki1213/kabul.json [--dry]
"""
import argparse
import json
import os

import sqlalchemy as sa
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", required=True)
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = json.load(open(a.ids_file))
eng = open_store(SemanticSettings.from_env().store_dsn).engine
counts: dict[str, int] = {}
paths: list[str] = []


def run(c, name: str, sql: str, params: dict) -> None:
    n = c.execute(sa.text(sql.replace("DELETE", "SELECT COUNT(*)", 1)), params).scalar() or 0
    counts[name] = counts.get(name, 0) + int(n)
    if not a.dry:
        c.execute(sa.text(sql), params)


with eng.begin() as c:
    for pid in ids.get("onokuma") or []:
        run(c, "ön okuma", "DELETE FROM semantic_editorial_application_prereads WHERE id = :i", {"i": pid})
    for aid in ids.get("basvuru") or []:
        paths += [r[0] for r in c.execute(sa.text("SELECT path FROM semantic_editorial_application_files WHERE app_id = :i"), {"i": aid})]
        for name, table in (("ön okuma", "semantic_editorial_application_prereads"), ("dosya", "semantic_editorial_application_files"),
                            ("değerlendirme", "semantic_editorial_application_evals"), ("günlük", "semantic_editorial_application_log"),
                            ("yazışma", "semantic_editorial_application_letters"), ("kurul raporu", "semantic_editorial_application_reports")):
            run(c, name, f"DELETE FROM {table} WHERE app_id = :i", {"i": aid})
        run(c, "başvuru", "DELETE FROM semantic_editorial_applications WHERE id = :i", {"i": aid})
    for eid in ids.get("belge") or []:
        paths += [r[0] for r in c.execute(sa.text("SELECT path FROM semantic_contract_extracts WHERE id = :i"), {"i": eid})]
        run(c, "sözleşme belgesi okuması", "DELETE FROM semantic_contract_extracts WHERE id = :i", {"i": eid})
for p in paths:
    if not a.dry and os.path.isfile(p):
        os.remove(p)
counts["diskteki dosya"] = len(paths)
for k, v in counts.items():
    print(f"{'(kuru) ' if a.dry else ''}silinen {k}: {v}")
