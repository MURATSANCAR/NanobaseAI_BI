#!/usr/bin/env python3
"""Yükleme kabulünün temizliği: kabul.py'nin dosyadan açtığı eser dosyalarını (M3/M5) ve çeviri işlerini (M4) siler;
bu kayıtlara ait `semantic_audit` satırlarını da kaldırır (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

kabul.py kendi açtıklarını sonunda bununla siler; yarıda kesilirse elle:

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/yukleme/temizlik.py --eser <id> --is <id>            # listeler
    python3 ../scripts/acceptance/yukleme/temizlik.py --eser <id> --is <id> --uygula                           # siler
    # id bilinmiyorsa: test hesabının belirli bir andan sonra dosyadan açtıkları
    python3 ../scripts/acceptance/yukleme/temizlik.py --actor timasai --since 2026-09-29T08:00:00+03:00 [--uygula]

Yalnız verilen kimlikler (ya da `--actor`un `--since`ten sonra `fromFile` ile açtıkları) silinir; başka kayda dokunulmaz.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import editorial_desk as desk  # noqa: E402
from semantic_bridge import editorial_translation as tr  # noqa: E402

DESK_TABLES = ("SUGGESTIONS", "CHAPTERS", "CHECKS", "SIGNATURES", "FILES")


def delete_work(engine: sa.engine.Engine, work_id: str) -> dict[str, int]:
    """Eser dosyasını bütün alt kayıtları ve diskteki dosyalarıyla siler; silinen satır sayıları döner."""
    out: dict[str, int] = {}
    with engine.begin() as c:
        # Alt tabloların hepsinde work_id var (öneri, bölüm, kontrol, imza, dosya); önce onlar, sonra eser.
        for name in DESK_TABLES:
            t = getattr(desk, name)
            out[t.name] = c.execute(sa.delete(t).where(t.c.work_id == work_id)).rowcount
        out[desk.WORKS.name] = c.execute(sa.delete(desk.WORKS).where(desk.WORKS.c.id == work_id)).rowcount
    shutil.rmtree(os.path.join(desk._root(), work_id), ignore_errors=True)
    return out


def delete_audit(engine: sa.engine.Engine, object_ids: list[str]) -> int:
    if not object_ids:
        return 0
    with engine.begin() as c:
        return c.execute(sa.delete(admin_mod.AUDIT).where(admin_mod.AUDIT.c.object_id.in_(object_ids))).rowcount


def created_since(engine: sa.engine.Engine, actor: str, since: datetime) -> tuple[list[str], list[str]]:
    """Değişiklik kaydından: kişinin `since`ten sonra dosyadan açtığı eser ve çeviri işleri."""
    works, jobs = [], []
    with engine.connect() as c:
        rows = c.execute(sa.select(admin_mod.AUDIT).where(admin_mod.AUDIT.c.actor == actor, admin_mod.AUDIT.c.action == "create",
                                                          admin_mod.AUDIT.c.at >= since,
                                                          admin_mod.AUDIT.c.kind.in_(("editorial_work", "translation_job")))).all()
    for r in rows:
        try:
            detail = json.loads(r.detail or "{}")
        except ValueError:
            detail = {}
        if not detail.get("fromFile"):
            continue
        (works if r.kind == "editorial_work" else jobs).append(r.object_id)
    return works, jobs


def clean(engine: sa.engine.Engine, tenant: str, actor: str, works: list[str], jobs: list[str], apply: bool) -> dict:
    report: dict = {"eser": works, "ceviri_isi": jobs, "uygulandi": apply}
    if not apply:
        return report
    report["silinen_eser"] = {w: delete_work(engine, w) for w in works}
    report["silinen_is"] = {}
    for j in jobs:
        try:
            report["silinen_is"][j] = tr.delete_job(engine, tenant, actor, True, j)
        except tr.TranslationError as e:
            report["silinen_is"][j] = f"silinemedi: {e}"
    report["silinen_kayit_satiri"] = delete_audit(engine, works + jobs)
    return report


def main() -> int:
    from semantic_layer.store.catalog_store import open_store

    ap = argparse.ArgumentParser()
    ap.add_argument("--eser", action="append", default=[], help="eser dosyası kimliği (tekrarlanabilir)")
    ap.add_argument("--is", dest="jobs", action="append", default=[], help="çeviri işi kimliği (tekrarlanabilir)")
    ap.add_argument("--actor", default="timasai")
    ap.add_argument("--since", help="kabulün başladığı an (ISO, saat dilimiyle); kimlik verilmezse kayıttan bulunur")
    ap.add_argument("--uygula", action="store_true")
    a = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    desk.ensure(engine)
    tr.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    works, jobs = list(a.eser), list(a.jobs)
    if a.since:
        w2, j2 = created_since(engine, a.actor, datetime.fromisoformat(a.since))
        works += [w for w in w2 if w not in works]
        jobs += [j for j in j2 if j not in jobs]
    print(json.dumps(clean(engine, tenant, a.actor, works, jobs, a.uygula), ensure_ascii=False, indent=2, default=str))
    if not a.uygula:
        print("Yalnız listelendi; silmek için --uygula.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
