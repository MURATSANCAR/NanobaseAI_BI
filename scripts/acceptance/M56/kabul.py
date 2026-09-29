#!/usr/bin/env python3
"""M56 Performans yönetimi — test sunucusunda gerçek Logo/CRM ve köprü veritabanıyla kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M56/kabul.py --out /tmp/claude-<oturum>/m56-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M56/kabul.py --api
    # Yazma akışı (yapay «KABUL TESTİ M56» çalışanları, hedef, dönem, değerlendirme; işlev düzeyinde): kimlikler --ids'e,
    # temizlik.py siler. Gerçek çalışanın değerlendirme verisi yazılmaz.
    ... kabul.py --yazma --ids /tmp/claude-<oturum>/m56-ids.json

Her kontrol: OK / FARK / DOĞRULANAMADI / ÖLÇÜM. Portal tarafı köprünün ekrana verdiği değerdir (API, yoksa aynı işlev);
referans aynı DB'de bağımsız SQL'dir (referans.sql).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import hr_core as H  # noqa: E402
from semantic_bridge import hr_performance as P  # noqa: E402
from semantic_bridge import hr_performance_sources as S  # noqa: E402
from semantic_bridge import hr_sources  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
PREFIX = "KABUL TESTİ M56"
START, END = date(2026, 1, 1), date(2026, 8, 17)     # sabit kabul penceresi (eski kopyanın son günü; canlı .25'te de kapalı dönem)


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:500]}")


def http(method: str, path: str, body=None):
    url = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795") + path
    headers = {"Content-Type": "application/json"}
    if os.environ.get("TIMAS_COOKIE"):
        headers["Cookie"] = os.environ["TIMAS_COOKIE"]
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m56-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m56-ids.json")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    P.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    logo_file = admin_mod.DB_FILE
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    schema = admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    # ------------------------------------------------------------------ K1 temsilci alanı doluluğu (Logo)
    try:
        logo = bsrc.runner(logo_file, 600)
        firm = bsrc.firms_by_year(logo).get(2026)
        ref = logo("SELECT COUNT(*) AS satir, SUM(CASE WHEN i.SALESMANREF <> 0 THEN 1 ELSE 0 END) AS temsilcili "
                   f"FROM LG_{firm}_01_INVOICE i WHERE i.CANCELLED = 0 AND i.TRCODE IN (7,8,9) "
                   "AND i.DATE_ >= '2026-01-01' AND i.DATE_ < '2027-01-01'")[0]
        if args.api:
            code, app = http("GET", "/api/v1/hr/performance/logo-salesman-fill?year=2026")
            app = app if code == 200 else None
        else:
            app = S.salesman_fill(logo, 2026)
        ok = app and int(app["invoices"]) == int(ref["satir"]) and int(app["withSalesman"]) == int(ref["temsilcili"] or 0)
        record("K1 temsilci alanı doluluğu (2026)", "OK" if ok else "FARK", portal=app, referans=ref, firma=firm)
    except Exception as e:  # noqa: BLE001
        logo = None
        record("K1 temsilci alanı doluluğu", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K2 temsilci net satışı
    if logo is not None:
        try:
            refrows = logo(
                "SELECT s.CODE AS kod, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET WHEN l.TRCODE IN (2,3) THEN -l.LINENET ELSE 0 END) AS net "
                f"FROM LG_{firm}_01_STLINE l JOIN LG_{firm}_01_INVOICE i ON i.LOGICALREF = l.INVOICEREF "
                "JOIN LG_SLSMAN s ON s.LOGICALREF = i.SALESMANREF "
                "WHERE l.CANCELLED = 0 AND l.LINETYPE = 0 AND l.INVOICEREF <> 0 AND l.DATE_ >= '2026-01-01' AND l.DATE_ < '2026-08-18' "
                "GROUP BY s.CODE")
            refrows.sort(key=lambda r: -abs(float(r["net"] or 0)))
            diffs = []
            for r in refrows[:8]:
                app = S.salesman_net(logo, str(r["kod"]).strip(), START, END)
                if abs(app["value"] - round(float(r["net"] or 0), 2)) > 0.01:
                    diffs.append({"kod": r["kod"], "portal": app["value"], "referans": float(r["net"] or 0)})
            record("K2 temsilci bazında net satış (ilk 8 kod)", "OK" if not diffs else "FARK", kod=len(refrows), fark=diffs,
                   not_="Hedef ekranındaki ilerleme bu işlevden; API ile ayrıca GET /goals/{id}/progress (sistem ölçüsü açıkken)")
        except Exception as e:  # noqa: BLE001
            record("K2 temsilci net satışı", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K3 CRM ↔ Logo temsilci köprüsü (ölçüm)
    try:
        crm = hr_sources.runner(crm_file)
        p = hr_sources.prefix(schema)
        codes = [str(r["kod"]).strip() for r in crm(f"SELECT new_KullancKoduLogoyaGnderilen AS kod FROM {p}SystemUserBase "
                                                    "WHERE IsDisabled = 0 AND new_KullancKoduLogoyaGnderilen IS NOT NULL")]
        slsman = {str(r["CODE"]).strip() for r in logo(f"SELECT CODE FROM LG_SLSMAN WHERE FIRMNR = {int(firm)}")} if logo is not None else set()
        record("K3 CRM kişi ↔ Logo temsilcisi (ölçüm)", "ÖLÇÜM", crm_kodlu=len(codes), eslesen=len(set(codes) & slsman),
               not_="Portalda bu eşleme ekranı yok; hedefte temsilci kodu elle girilir. Karar için ölçüm")
    except Exception as e:  # noqa: BLE001
        crm = None
        record("K3 CRM ↔ Logo köprüsü", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K4 editör iş özeti (M2 görevleri)
    try:
        with engine.connect() as c:
            eds = [r[0] for r in c.execute(sa.text(
                "SELECT editor_id FROM semantic_editorial_tasks WHERE tenant_id = :t AND status = 'tamamlandi' "
                "GROUP BY editor_id ORDER BY COUNT(*) DESC LIMIT 5"), {"t": tenant}).all()]
            diffs = []
            for ed in eds:
                q = ("SELECT COUNT(*) FROM semantic_editorial_tasks WHERE tenant_id = :t AND lower(editor_id) = lower(:e) "
                     "AND status = 'tamamlandi' AND done_at >= :b AND done_at < :s")
                prm = {"t": tenant, "e": ed, "b": START, "s": END + timedelta(days=1)}
                done = c.execute(sa.text(q), prm).scalar()
                on_time = c.execute(sa.text(q + " AND due_date IS NOT NULL AND done_at::date <= due_date"), prm).scalar()
                app = S.editorial_facts(engine, tenant, ed, START, END)
                if app.get("done") != done or app.get("onTime") != on_time:
                    diffs.append({"editor": ed[-6:], "portal": [app.get("done"), app.get("onTime")], "referans": [done, on_time]})
        record("K4 editör iş özeti (tamamlanan, termininde)", "OK" if eds and not diffs else ("FARK" if diffs else "DOĞRULANAMADI"),
               editor=len(eds), fark=diffs, not_="done_at UTC; ::date oturum saat dilimine bağlı — fark çıkarsa gece yarısı kaymasına bakın")
    except Exception as e:  # noqa: BLE001
        record("K4 editör iş özeti", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K5 CRM proje/sözleşme sahipliği
    if crm is not None:
        try:
            with engine.connect() as c:
                users = [r[0] for r in c.execute(sa.text(
                    "SELECT crm_systemuser_id FROM semantic_hr_employees WHERE tenant_id = :t AND status = 'aktif' "
                    "AND crm_systemuser_id IS NOT NULL LIMIT 5"), {"t": tenant}).all()]
            diffs = []
            for u in users:
                rng = f"CreatedOn >= '2026-01-01' AND CreatedOn < '2026-08-18'"
                ref = {k: int(crm(f"SELECT COUNT(*) AS n FROM {p}{tbl} WHERE OwnerId = '{u}' AND {rng}")[0]["n"])
                       for k, tbl in (("projects", "new_projeBase"), ("contracts", "new_sozlesmeBase"))}
                app = S.crm_ownership(crm, p, u, START, END)
                if app != ref:
                    diffs.append({"kullanici": u[-6:], "portal": app, "referans": ref})
            record("K5 CRM proje/sözleşme sahipliği", "OK" if users and not diffs else ("FARK" if diffs else "DOĞRULANAMADI"),
                   kisi=len(users), fark=diffs)
        except Exception as e:  # noqa: BLE001
            record("K5 CRM sahipliği", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K6 dönem tamamlanma
    hr_who = H.Who("kabul", "Kabul", False, frozenset({P.F_CYCLE, P.F_REVIEW_APPROVE}))
    sc = P.Scope(engine, tenant, hr_who)
    cycles = P.list_cycles(engine, tenant)
    if not cycles:
        record("K6 dönem tamamlanma", "DOĞRULANAMADI", neden="dönem yok (yazma akışı açar)")
    for cy in cycles:
        with engine.connect() as c:
            ref = c.execute(sa.text(
                "SELECT COUNT(*) FILTER (WHERE self_submitted_at IS NOT NULL) * 1.0 / NULLIF(COUNT(*), 0), "
                "COUNT(*) FILTER (WHERE manager_submitted_at IS NOT NULL) * 1.0 / NULLIF(COUNT(*), 0) "
                "FROM semantic_hr_reviews WHERE cycle_id = :c"), {"c": cy["id"]}).first()
        st = P.cycle_status(engine, tenant, sc, cy["id"])
        same = all((a is None and b is None) or (a is not None and b is not None and abs(float(a) - float(b)) < 1e-9)
                   for a, b in ((st["selfRate"], ref[0]), (st["managerRate"], ref[1])))
        record(f"K6 dönem tamamlanma · {cy['name']}", "OK" if same else "FARK", portal=[st["selfRate"], st["managerRate"]],
               referans=[ref[0], ref[1]])

    # ------------------------------------------------------------------ K7 kapsam (manager_id zinciri)
    with engine.connect() as c:
        managers = [r[0] for r in c.execute(sa.text(
            "SELECT DISTINCT manager_id FROM semantic_hr_employees WHERE tenant_id = :t AND manager_id IS NOT NULL"), {"t": tenant}).all()]
        diffs = []
        for m in managers:
            ref = {r[0] for r in c.execute(sa.text(
                "WITH RECURSIVE ekip AS (SELECT id FROM semantic_hr_employees WHERE tenant_id = :t AND manager_id = :m "
                "UNION SELECT e.id FROM semantic_hr_employees e JOIN ekip ON e.manager_id = ekip.id WHERE e.tenant_id = :t) "
                "SELECT id FROM ekip"), {"t": tenant, "m": m}).all()} - {m}
            user = c.execute(sa.text("SELECT username FROM semantic_hr_employees WHERE id = :m"), {"m": m}).scalar()
            if not user:
                continue
            app = P.Scope(engine, tenant, H.Who(user, user, False, frozenset())).team
            if app != ref:
                diffs.append({"yonetici": m[-6:], "portal": len(app), "referans": len(ref)})
    record("K7 Ekibim kapsamı = WITH RECURSIVE", "OK" if not diffs else "FARK", yonetici=len(managers), fark=diffs)
    if args.api:
        code, team = http("GET", "/api/v1/hr/performance/team")
        record("K7b API /team", "OK" if code == 200 else "FARK", durum=code, kisi=len((team or {}).get("people") or []))

    # ------------------------------------------------------------------ K8 hiyerarşi doluluğu
    with engine.connect() as c:
        ref = c.execute(sa.text("SELECT COUNT(*) FILTER (WHERE manager_id IS NULL) FROM semantic_hr_employees "
                                "WHERE tenant_id = :t AND status = 'aktif'"), {"t": tenant}).scalar()
    app = len(P.hierarchy_gaps(sc))
    record("K8 yöneticisi kayıtlı olmayan aktif çalışan", "OK" if app == ref else "FARK", portal=app, referans=ref)

    # ------------------------------------------------------------------ yazma akışı (yapay kayıt, işlev düzeyinde)
    if args.yazma:
        ids: dict[str, list[str]] = {"employees": [], "units": [], "goals": [], "cycles": [], "forms": []}
        try:
            unit, _ = H.save_unit(engine, tenant, "kabul", {"name": f"{PREFIX} birim"})
            ids["units"].append(unit["id"])
            mgr, _ = H.save_employee(engine, tenant, "kabul", {"displayName": f"{PREFIX} yönetici", "username": "kabul-m56-y", "unitId": unit["id"]})
            emp, _ = H.save_employee(engine, tenant, "kabul", {"displayName": f"{PREFIX} çalışan", "username": "kabul-m56-c",
                                                               "unitId": unit["id"], "managerId": mgr["id"]})
            ids["employees"] += [mgr["id"], emp["id"]]
            keys = frozenset({P.F_GOAL_WRITE, P.F_GOAL_APPROVE, P.F_REVIEW_WRITE, P.F_WORK})
            m_sc = P.Scope(engine, tenant, H.Who("kabul-m56-y", "Y", False, keys))
            e_sc = P.Scope(engine, tenant, H.Who("kabul-m56-c", "C", False, frozenset()))
            g, _ = P.save_goal(engine, tenant, e_sc, {"title": f"{PREFIX} hedef", "period": "2026-Q4"})
            ids["goals"].append(g["id"])
            P.goal_transition(engine, tenant, e_sc, g["id"], "submit")
            ok = P.goal_transition(engine, tenant, m_sc, g["id"], "approve")["state"] == "yururlukte"
            form, _ = P.save_form(engine, tenant, "kabul", {**P.STARTER_FORM, "name": f"{PREFIX} form", "state": "yururlukte"})
            ids["forms"].append(form["id"])
            cy, _ = P.save_cycle(engine, tenant, "kabul", {"name": f"{PREFIX} dönem", "periodStart": "2026-01-01", "periodEnd": "2026-12-31",
                                                           "startsOn": date.today().isoformat(), "endsOn": (date.today() + timedelta(days=7)).isoformat(),
                                                           "formTemplateId": form["id"], "units": [unit["id"]]})
            ids["cycles"].append(cy["id"])
            hr_sc = P.Scope(engine, tenant, H.Who("kabul-ik", "İK", False, frozenset({P.F_CYCLE, P.F_REVIEW_APPROVE})))
            P.cycle_transition(engine, tenant, hr_sc, cy["id"], "open")
            rid = next(x["reviewId"] for x in P.cycle_status(engine, tenant, hr_sc, cy["id"])["people"] if x["employeeId"] == emp["id"])
            P.save_review(engine, tenant, e_sc, rid, {"self": {"notes": {"guclu": "kabul"}}}, submit="self")
            P.save_review(engine, tenant, m_sc, rid, {"manager": {"overall": 3}}, submit="manager")
            hidden = P.get_review(engine, tenant, e_sc, rid)["manager"] is None
            P.review_action(engine, tenant, m_sc, rid, "share", {})
            P.review_action(engine, tenant, e_sc, rid, "comment", {"comment": "kabul"})
            done = P.review_action(engine, tenant, hr_sc, rid, "approve", {})["state"] == "onaylandi"
            outsider = P.Scope(engine, tenant, H.Who("kabul-yok", "x", False, keys))
            try:
                P.get_review(engine, tenant, outsider, rid)
                denied = False
            except H.HrError as e:
                denied = e.status == 403
            with engine.connect() as c:
                logged = c.execute(sa.select(sa.func.count()).select_from(H.ACCESS_LOG).where(
                    H.ACCESS_LOG.c.username == "kabul-yok", H.ACCESS_LOG.c.action == "reddedildi")).scalar()
            record("Y1 yazma akışı: hedef onayı, değerlendirme, paylaşım gizliliği, İK onayı, zincir dışı 403 + erişim kaydı",
                   "OK" if ok and hidden and done and denied and logged else "FARK",
                   hedef=ok, paylasimdan_once_gizli=hidden, onay=done, red=denied, erisim_kaydi=logged)
        except Exception as e:  # noqa: BLE001
            record("Y1 yazma akışı", "FARK", hata=f"{type(e).__name__}: {e}"[:300])
        Path(args.ids).write_text(json.dumps(ids, ensure_ascii=False, indent=2))
        print(f"kimlikler: {args.ids} — temizlik.py ile silin")

    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))
    bad = [r for r in RESULTS if r["durum"] == "FARK"]
    print(f"\n{len(RESULTS)} kontrol · FARK {len(bad)} · DOĞRULANAMADI {sum(r['durum'] == 'DOĞRULANAMADI' for r in RESULTS)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
