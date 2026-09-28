"""H1 Kategori ağacı kabulü — test sunucusunda, gerçek CRM (.28) / Logo / meta veritabanına karşı. Mac'te koşulmaz.

Koşum (köprünün env'i ile; önce kaynak okuması yapılmış olmalı: `systemctl start timas-categories.service` ya da
ekrandan «Kaynakları yenile»):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/categories/accept.py [--api-cookie 'timas_session=…'] [--out kanit.json]

`--api-cookie` verilirse aynı sayılar köprünün gerçek uçlarından (`/api/v1/categories/overview`, `/findings`,
`/profile/{stok}`) da okunup karşılaştırılır (oturum: `timasai` kısa ömürlü oturumu; test bitince silinir). Verilmezse
modülün depo işlevleri kullanılır. Referanslar doğrudan SQL'dir (CRM ve Logo ayrı bağlantı, `connector_from_file`).

Denetimler (hepsi geçmeli; «ölçülecek» olanlar rapora sayıyla yazılır):
  1. Aktif kitap: CRM `statecode = 0 AND new_Tip = 1` = özetteki «aktif kitap» (2026-09-24'te 9.091).
  2. Kitaplık doluluğu: CRM = doluluk çubuğu.
  3. Ürün kategorisi bağlı aktif kitap: CRM COUNT(DISTINCT) = doluluk çubuğu.
  4. «Yetişkin kitabı Çocuk web kategorisinde»: CRM sayısı = `hedef_kitle_web` kuralının (Yetişkin, Çocuk) bulguları
     (açık + yok sayılan).
  5. Tema bağı: aktif kitaplardaki bağ sayısı CRM = özetteki tema bağı (tabloların tamamı da ayrıca raporlanır).
  6. Öncelik puanı: satış önceliği en yüksek 5 kitap + rastgele 5 satışlı kitap için Logo'dan doğrudan son N ay net
     adet (her yıl kendi firmasında) = profildeki puan.
  7. T-soft: barkodu SEO eşitlemesindeki bir ürüne düşen aktif kitap sayısı (doğrudan meta SQL) = anlık görüntüdeki.
  8. Uydurma kategori yok: profillerdeki bütün kategori önerisi ve kararı yürürlükteki ağacın etkin düğümü.
  9. Onay izi: karar verilmiş her alanın `semantic_book_profile_events`'te kullanıcı + zamanlı kaydı var.
Çıktı JSON'dur; kanıt olarak kaydedin.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import categories as C  # noqa: E402
from semantic_bridge import categories_sources as src  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

CRM_FILE = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
BRIDGE = os.environ.get("CATEGORY_ACCEPT_BRIDGE", "http://127.0.0.1:8795")


def api(path: str, cookie: str) -> dict:
    req = urllib.request.Request(BRIDGE + path, headers={"cookie": cookie})
    with urllib.request.urlopen(req, timeout=600) as r:  # noqa: S310 — yerel köprü
        return json.loads(r.read())


def one(run, sql: str) -> int:
    rows = run(sql)
    v = list(rows[0].values())[0] if rows else 0
    return int(v or 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-cookie", default="", help="portal oturum çerezi (timas_session=…); verilirse uçlar da denetlenir")
    ap.add_argument("--schema", default=os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo"))
    ap.add_argument("--out", default="", help="kanıt JSON dosyası")
    args = ap.parse_args()

    s = SemanticSettings.from_env()
    engine = open_store(s.store_dsn, create=False).engine
    tenant = s.tenant_id
    crm = src.runner(CRM_FILE)
    logo = src.runner(s.connection_file)
    p = args.schema.rstrip(".") + "."
    report: dict = {"tenant": tenant, "checks": [], "failures": [], "measured": {}}

    def check(name: str, ok: bool, **detail) -> None:
        report["checks"].append({"name": name, "ok": bool(ok), **detail})
        if not ok:
            report["failures"].append(name)

    if args.api_cookie:
        ov = api("/api/v1/categories/overview", args.api_cookie)
        source = "api"
    else:
        ov = C.overview(engine, tenant, None)
        source = "modul"
    report["source"] = source
    fill = {f["key"]: f["filled"] for f in ov["fill"]}
    sync = ov.get("sync") or {}
    report["sync"] = {"at": sync.get("at"), "crm": sync.get("crm"), "logo": sync.get("logo"), "tsoft": sync.get("tsoft")}

    active = "k.statecode = 0 AND k.new_Tip = 1"
    # 1
    ref = one(crm, f"SELECT COUNT(*) AS n FROM {p}new_kitapBase k WHERE {active}")
    check("1-aktif-kitap", ref == ov["activeBooks"], referans=ref, ekran=ov["activeBooks"])
    # 2
    ref = one(crm, f"SELECT SUM(CASE WHEN k.new_kitaplikid IS NOT NULL THEN 1 ELSE 0 END) AS n FROM {p}new_kitapBase k WHERE {active}")
    check("2-kitaplik-dolulugu", ref == fill.get("kitaplik"), referans=ref, ekran=fill.get("kitaplik"))
    # 3
    ref = one(crm, f"SELECT COUNT(DISTINCT u.new_kitapid) AS n FROM {p}new_new_urunkategorisi_new_kitapBase u "
                   f"JOIN {p}new_kitapBase k ON k.new_kitapId = u.new_kitapid WHERE {active}")
    check("3-urun-kategorisi-bagli", ref == fill.get("urunkategorisi"), referans=ref, ekran=fill.get("urunkategorisi"))
    # 4
    ref = one(crm, f"SELECT COUNT(*) AS n FROM {p}new_kitapBase k WHERE {active} AND k.new_hedefkitle = 3 "
                   f"AND LTRIM(k.new_webkategorileritext) LIKE N'Çocuk;%'")
    F, P = C.FINDINGS.c, C.PROFILES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(F.detail_json).select_from(C.FINDINGS.join(C.PROFILES, sa.and_(
            P.tenant_id == F.tenant_id, P.book_id == F.book_id))).where(
            F.tenant_id == tenant, F.rule_key == "hedef_kitle_web", F.status.in_(("acik", "yoksay")), P.active.is_(True))).all()
    mine = sum(1 for (d,) in rows if C.fold(C.loads(d, {}).get("hedefKitle")) == C.fold("Yetişkin")
               and C.fold(C.loads(d, {}).get("webRoot")) == C.fold("Çocuk"))
    check("4-yetiskin-cocuk-web", ref == mine, referans=ref, modul=mine, kuralToplam=len(rows))
    # 5
    ref_active = one(crm, f"SELECT COUNT(*) AS n FROM {p}new_new_kitap_new_temaBase t JOIN {p}new_kitapBase k "
                          f"ON k.new_kitapId = t.new_kitapid WHERE {active}")
    ref_all = one(crm, f"SELECT COUNT(*) AS n FROM {p}new_new_kitap_new_temaBase")
    check("5-tema-bagi", ref_active == (ov.get("links") or {}).get("tema"), referans=ref_active, ekran=(ov.get("links") or {}).get("tema"),
          tabloToplami=ref_all)
    # 6
    months = int((ov.get("priority") or {}).get("months") or C.thresholds()["priorityMonths"])
    firms = bsrc.firms_by_year(logo)
    end = bsrc.read_data_end(logo, firms)
    start = src.months_back(end, months)
    with engine.connect() as c:
        top = [r[0] for r in c.execute(sa.select(P.stock_code).where(P.tenant_id == tenant, P.active.is_(True), P.stock_code.isnot(None))
                                       .order_by(P.priority_score.desc()).limit(5))]
        pool = [r[0] for r in c.execute(sa.select(P.stock_code).where(P.tenant_id == tenant, P.active.is_(True), P.priority_score > 0))]
        sample = top + random.Random(28).sample([x for x in pool if x not in top], min(5, max(0, len(pool) - len(top))))
        scores = dict(c.execute(sa.select(P.stock_code, P.priority_score).where(P.tenant_id == tenant, P.stock_code.in_(sample))).all())
    from datetime import date
    diffs = []
    for code in sample:
        total = 0.0
        for y in range(start.year, end.year + 1):
            if y not in firms:
                continue
            a, b = max(start, date(y, 1, 1)), min(date.fromordinal(end.toordinal() + 1), date(y + 1, 1, 1))
            safe = code.replace("'", "''")
            rows = logo(f"SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet "
                        f"FROM dbo.LG_{firms[y]}_01_STLINE S JOIN dbo.LG_{firms[y]}_ITEMS I ON I.LOGICALREF = S.STOCKREF "
                        f"WHERE I.CODE = '{safe}' AND S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 "
                        f"AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'")
            total += float((rows[0].get("adet") if rows else 0) or 0)
        got = float(scores.get(code) or 0)
        diffs.append({"stok": code, "referans": total, "profil": got})
    check("6-oncelik-puani", all(abs(d["referans"] - d["profil"]) < 0.001 for d in diffs), ornekler=diffs,
          pencere=f"{start.isoformat()}..{end.isoformat()}")
    if args.api_cookie and sample:
        prof = api(f"/api/v1/categories/profile/{urllib.request.quote(sample[0])}", args.api_cookie)
        check("6b-profil-ucu", abs(float(prof.get("priority") or 0) - diffs[0]["referans"]) < 0.001, stok=sample[0],
              uc=prof.get("priority"), referans=diffs[0]["referans"])
    # 7
    from semantic_bridge.seo_geo.store import PRODUCTS
    with engine.connect() as c:
        eans = {str(C.loads(d, {}).get("Barcode") or "").strip() for (d,) in c.execute(
            sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant))}
        eans = {"".join(ch for ch in e if ch.isdigit()) for e in eans} - {""}
        snaps = [C.loads(r[0], {}) for r in c.execute(sa.select(P.crm_snapshot_json).where(P.tenant_id == tenant, P.active.is_(True)))]
    ref = sum(1 for b in snaps if b.get("ean") and b["ean"] in eans)
    mine = sum(1 for b in snaps if b.get("tsoft"))
    check("7-tsoft-eslesmesi", ref == mine, referans=ref, modul=mine, seoUrun=len(eans))
    # 8
    live = C.in_force(engine, tenant)
    ctx = C.tree_ctx(engine, live)
    bad = []
    with engine.connect() as c:
        for bid, raw in c.execute(sa.select(P.book_id, P.fields_json).where(P.tenant_id == tenant)):
            k = (C.loads(raw, {}) or {}).get("kategori") or {}
            for key in ("proposed", "value"):
                v = k.get(key)
                if v and k.get("state") in ("oneri", "kabul", "duzeltme") and (key == "value" or k.get("state") == "oneri") and not ctx.active(v):
                    bad.append({"bookId": bid, key: v})
    check("8-uydurma-kategori-yok", not bad, ihlal=bad[:50], ihlalSayisi=len(bad), agac=(live or {}).get("version"))
    # 9
    missing = []
    E = C.EVENTS.c
    with engine.connect() as c:
        decided = [(bid, f, v) for bid, raw in c.execute(sa.select(P.book_id, P.fields_json).where(P.tenant_id == tenant))
                   for f, v in (C.loads(raw, {}) or {}).items() if v.get("state") in C.DECIDED]
        for bid, f, v in decided:
            n = c.execute(sa.select(sa.func.count()).where(E.tenant_id == tenant, E.book_id == bid, E.field == f,
                                                           E.action == v["state"], E.user == v.get("by"))).scalar()
            if not n:
                missing.append({"bookId": bid, "field": f})
    check("9-onay-izi", not missing, kararli=len(decided), eksik=missing[:50])

    report["measured"] = {"durum": ov.get("status"), "yerlesen": ov.get("placed"), "acikBulgu": (ov.get("findings") or {}).get("byRule"),
                          "crmFarki": ov.get("crmDiff"), "agac": (live or {}).get("version")}
    report["ok"] = not report["failures"]
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
