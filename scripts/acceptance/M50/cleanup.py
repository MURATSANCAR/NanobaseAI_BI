"""M50 kabulünün bıraktığı kayıtları kimlikle siler: deneme sorusunun soru kaydı (sl_query_log), geri bildirim, kabulde
koşturulan kapı koşusu ve vakaları, o koşunun yazdığı sürüm satırları ve bu kayıtlara ait değişiklik kaydı satırları
(model_quality_*). Silinen sayılar yazdırılır (günlüğe geçirilir).

Kullanım: cleanup.py --ids-file /tmp/claude-m50/kabul-kimlikler.json [--actor timasai] [--keep-runs] [--dry]
`--keep-runs`: kapı koşusu gerçek bir ölçümse (kullanıcı saklanmasını isterse) koşu ve sürüm satırı bırakılır.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.environ.get("M50_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", required=True)
ap.add_argument("--actor", default="timasai")
ap.add_argument("--keep-runs", action="store_true")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = json.load(open(a.ids_file))
eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
counts: dict[str, int] = {}


def run(label: str, sql: str, **p) -> None:
    with eng.begin() as c:
        if a.dry:
            n = c.execute(sa.text("SELECT count(*) FROM (" + sql.replace("DELETE FROM", "SELECT 1 FROM", 1) + ") x"), p).scalar()
        else:
            n = c.execute(sa.text(sql), p).rowcount
    counts[label] = counts.get(label, 0) + int(n or 0)


queries, feedback = ids.get("queries", []), ids.get("feedback", [])
runs, versions = ids.get("runs", []), [int(v) for v in ids.get("versions", [])]
since = ids.get("since")
if feedback or queries:
    run("geri bildirim", "DELETE FROM semantic_mq_feedback WHERE id = ANY(:f) OR query_id = ANY(:q)", f=feedback, q=queries)
if queries:
    run("soru kaydı", "DELETE FROM sl_query_log WHERE id = ANY(:q)", q=queries)
if runs and not a.keep_runs:
    run("koşu vakası", "DELETE FROM semantic_mq_cases WHERE run_id = ANY(:r)", r=runs)
    run("koşu", "DELETE FROM semantic_mq_runs WHERE id = ANY(:r)", r=runs)
    if versions:
        run("sürüm satırı", "DELETE FROM semantic_mq_versions WHERE id = ANY(:v) AND source = 'kosu'", v=versions)
    run("değişiklik kaydı (koşu)", "DELETE FROM semantic_audit WHERE kind = 'model_quality_run' AND object_id = ANY(:r)", r=runs)
if since and a.actor:
    run("değişiklik kaydı (kişi)", "DELETE FROM semantic_audit WHERE kind LIKE 'model_quality%' AND actor = :a AND at >= :s",
        a=a.actor, s=since)
if feedback:
    run("değişiklik kaydı (geri bildirim)", "DELETE FROM semantic_audit WHERE kind = 'model_quality_feedback' AND object_id = ANY(:f)",
        f=feedback)
state = "(deneme — silinmedi)" if a.dry else "silindi"
for k, v in counts.items():
    print(f"{k}: {v} {state}")
print("toplam:", sum(counts.values()), state)
