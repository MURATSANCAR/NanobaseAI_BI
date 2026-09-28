#!/usr/bin/env python3
"""M55 İşe alım + İK-0 — test sunucusunda gerçek CRM/AD ve köprü veritabanıyla kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M55/kabul.py --out /tmp/claude-<oturum>/m55-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M55/kabul.py --api
    # Yazma akışı (geçici İK rolü + yapay aday + kanıtlı özet + e-posta aktarımı): kimlikler --ids dosyasına yazılır,
    # temizlik.py siler. Yapay aday verisi kişisel veri değildir («KABUL TESTİ» adlı, uydurma özgeçmiş).
    ... kabul.py --api --yazma --ids /tmp/claude-<oturum>/m55-ids.json

Her kontrol: OK / FARK / DOĞRULANAMADI. Portal tarafı köprünün ekrana verdiği değerdir (API, yoksa aynı işlev);
referans aynı CRM/DB'de bağımsız SQL'dir (referans.sql). Uygulamanın SQL'i yeniden koşturulmaz.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import access as A  # noqa: E402
from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import hr_core as H  # noqa: E402
from semantic_bridge import hr_recruit as R  # noqa: E402
from semantic_bridge import hr_sources as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
TEST_NAME = "KABUL TESTİ M55"
#: Uydurma özgeçmiş: gerçek kişiye ait değil; T.C. no örnek sağlamalı numara, telefon/e-posta hayali.
FAKE_CV = """KABUL TESTİ M55
Doğum tarihi: 01.01.1990
T.C. 10000000146
Tel: 0555 000 00 00 · kabul@example.invalid
2019-2024 Örnek Yayınevi, redaktör: çocuk kitaplarında redaksiyon
Yabancı dil: İngilizce (ileri)
"""


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:400]}")


def http(method: str, path: str, body=None, cookie: bool = True, token: bool = False):
    url = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795") + path
    headers = {"Content-Type": "application/json"}
    if cookie and os.environ.get("TIMAS_COOKIE"):
        headers["Cookie"] = os.environ["TIMAS_COOKIE"]
    if token and os.environ.get("SEMANTIC_CALLER_TOKEN"):
        headers["X-Semantic-Caller"] = os.environ["SEMANTIC_CALLER_TOKEN"]
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw[:300]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m55-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m55-ids.json")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    R.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    schema = admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"
    mgr_col = admin_mod.conf("HR_CRM_UNIT_MANAGER_COLUMN") or "new_departmanyoneticisiid"

    # ------------------------------------------------------------------ portal değeri: eşitleme önizlemesi
    pv = None
    if args.api:
        code, pv = http("POST", "/api/v1/hr/employees/sync-preview", {})
        record("API eşitleme önizlemesi", "OK" if code == 200 else "FARK", durum=code)
        if code != 200:
            pv = None
    if pv is None:
        try:
            pv = S.read_preview(crm_file, schema, mgr_col, {k: admin_mod.conf(k) for k in admin_mod.store_keys("ad")},
                                H.list_employees(engine, tenant, status=""), H.list_units(engine, tenant))
        except Exception as e:  # noqa: BLE001
            record("eşitleme önizlemesi", "DOĞRULANAMADI", hata=str(e)[:300])
    try:
        crm = S.runner(crm_file)
        p = S.prefix(schema)
    except Exception as e:  # noqa: BLE001
        record("CRM bağlantısı", "DOĞRULANAMADI", hata=str(e)[:300])
        crm = None
    if pv is not None and crm is not None:
        st = pv["stats"]
        # K1 — CRM'de etkin (etkileşimli) kullanıcı
        ref = crm(f"SELECT COUNT(*) AS v FROM {p}SystemUserBase WHERE IsDisabled = 0 AND AccessMode IN (0, 1) "
                  f"AND DomainName IS NOT NULL AND DomainName <> ''")[0]["v"]
        ref_timas = crm(f"SELECT COUNT(*) AS v FROM {p}SystemUserBase WHERE IsDisabled = 0 AND AccessMode IN (0, 1) "
                        f"AND DomainName LIKE 'TIMAS\\%'")[0]["v"]
        record("K1 CRM etkin kullanıcı", "OK" if int(ref) == int(st["crmInteractive"]) else "FARK",
               portal=st["crmInteractive"], referans=ref, timas_alan_adi=ref_timas, ad_bakildi=st["adChecked"], ad_eslesen=st["matched"])
        ref_enabled = crm(f"SELECT COUNT(*) AS v FROM {p}SystemUserBase WHERE IsDisabled = 0")[0]["v"]
        record("K1b devre dışı olmayan CRM hesabı", "OK" if int(ref_enabled) == int(st["crmEnabled"]) else "FARK",
               portal=st["crmEnabled"], referans=ref_enabled)
        # K2 — birim başına devre dışı olmayan kullanıcı (bütün birimler)
        rows = crm(f"SELECT CAST(b.BusinessUnitId AS nvarchar(40)) AS id, b.Name AS ad, COUNT(*) AS n FROM {p}SystemUserBase u "
                   f"JOIN {p}BusinessUnitBase b ON b.BusinessUnitId = u.BusinessUnitId WHERE u.IsDisabled = 0 AND b.IsDisabled = 0 "
                   f"GROUP BY b.BusinessUnitId, b.Name")
        passive = crm(f"SELECT COUNT(*) AS v FROM {p}SystemUserBase u JOIN {p}BusinessUnitBase b ON b.BusinessUnitId = u.BusinessUnitId "
                      f"WHERE u.IsDisabled = 0 AND b.IsDisabled = 1")[0]["v"]
        refmap = {str(r["id"]).strip("{}").lower(): int(r["n"]) for r in rows}
        app = {u["crmBusinessUnitId"]: int(u["enabledUsers"]) for u in pv["units"]}
        diff = {k: {"portal": app.get(k, 0), "referans": v} for k, v in refmap.items() if app.get(k, 0) != v}
        # Pasif birimdeki etkin kullanıcı portalda birimsiz kalır: ayrıca raporlanır.
        record("K2 birim dağılımı (etkin birimler)", "OK" if not diff else "FARK", birim=len(refmap), fark=diff,
               pasif_birimdeki_kullanici=passive)
        # K3 — yöneticisi bilinen birim
        try:
            r3 = crm(f"SELECT COUNT(*) AS birim, SUM(CASE WHEN {mgr_col} IS NOT NULL THEN 1 ELSE 0 END) AS yoneticili "
                     f"FROM {p}BusinessUnitBase WHERE IsDisabled = 0")[0]
            ok = int(r3["birim"]) == int(st["units"]) and int(r3["yoneticili"] or 0) == int(st["unitsWithManager"])
            record("K3 yöneticisi bilinen birim", "OK" if ok else "FARK", portal=[st["units"], st["unitsWithManager"]],
                   referans=[r3["birim"], r3["yoneticili"]], olculecek="doluluk ilk kez ölçülüyor")
        except Exception as e:  # noqa: BLE001
            record("K3 yöneticisi bilinen birim", "DOĞRULANAMADI", kolon=mgr_col, hata=str(e)[:200], notlar=pv["notes"])
        # K4 — ekip başına etkin üye
        rows = crm(f"SELECT CAST(t.TeamId AS nvarchar(40)) AS id, t.Name AS ad, COUNT(*) AS n FROM {p}TeamMembership m "
                   f"JOIN {p}TeamBase t ON t.TeamId = m.TeamId JOIN {p}SystemUserBase u ON u.SystemUserId = m.SystemUserId "
                   f"WHERE u.IsDisabled = 0 GROUP BY t.TeamId, t.Name")
        refmap = {str(r["id"]).strip("{}").lower(): int(r["n"]) for r in rows}
        app = {t["teamId"]: int(t["members"]) for t in pv["teams"]}
        diff = {k: {"portal": app.get(k, 0), "referans": v} for k, v in refmap.items() if app.get(k, 0) != v}
        record("K4 ekip üyeliği", "OK" if not diff and set(app) == set(refmap) else "FARK", ekip=len(refmap), fark=diff)
        # K4b — Kampüs rehberi (son 365 gün girişi süzgeçli) bilgi amaçlı
        if args.api:
            code, people = http("GET", "/api/v1/people")
            if code == 200:
                record("K4b rehber toplamı (bilgi)", "OK", rehber=people.get("total"), ik_onerisi=st["matched"],
                       not_="rehber son 365 gün girişi olmayanı ayıklar; İK önerisi ayıklamaz")

    # ------------------------------------------------------------------ K5 pano sayaçları (köprü DB)
    who_all = H.Who("kabul", "Kabul", False, frozenset({R.F_ALL}))
    board = R.pipeline(engine, tenant, who_all)
    with engine.connect() as c:
        ref = c.execute(sa.text("SELECT COALESCE(position_id, '-') AS p, stage, COUNT(*) AS n FROM semantic_hr_candidates "
                                "WHERE tenant_id = :t AND purged_at IS NULL GROUP BY COALESCE(position_id, '-'), stage"),
                        {"t": tenant}).all()
    refmap = {(r.p, r.stage): int(r.n) for r in ref}
    app: dict = {}
    for stage, cards in board["columns"].items():
        for card in cards:
            k = (card["positionId"] or "-", stage)
            app[k] = app.get(k, 0) + 1
    record("K5 pano: pozisyon × aşama sayıları", "OK" if app == refmap else "FARK", portal=len(app), referans=len(refmap),
           fark={f"{k[0]}/{k[1]}": [app.get(k), refmap.get(k)] for k in set(app) | set(refmap) if app.get(k) != refmap.get(k)})
    sla = H.settings(admin_mod.conf)["slaDays"]
    if sla:
        with engine.connect() as c:
            ref_over = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_candidates WHERE tenant_id = :t AND purged_at IS NULL "
                                         "AND stage <> 'sonuc' AND stage_since < now() - make_interval(days => :d)"),
                                 {"t": tenant, "d": int(sla)}).scalar()
        record("K5b eşik üstü bekleyen", "OK" if int(ref_over) == int(R.pipeline(engine, tenant, who_all, sla_days=sla)["counters"]["overSla"]) else "FARK",
               referans=ref_over, esik=sla)
    else:
        record("K5b eşik üstü bekleyen", "DOĞRULANAMADI", neden="HR_RECRUIT_SLA_DAYS ayarlanmadı (ölçülecek: İK kararı)")

    # ------------------------------------------------------------------ K6 imha (gerçek zamanlayıcı ucu)
    with engine.connect() as c:
        before = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_candidates WHERE tenant_id = :t AND retention_until < now() "
                                   "AND purged_at IS NULL AND outcome IN ('ret', 'cekildi')"), {"t": tenant}).scalar()
    code, out = http("POST", "/api/v1/hr/purge/run-due", {}, cookie=False, token=True)
    if code != 200:
        record("K6 imha işi", "DOĞRULANAMADI", durum=code, cevap=str(out)[:200])
    else:
        with engine.connect() as c:
            after = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_candidates WHERE tenant_id = :t AND retention_until < now() "
                                      "AND purged_at IS NULL"), {"t": tenant}).scalar()
            last = c.execute(sa.text("SELECT purged_count FROM semantic_hr_purge_runs WHERE tenant_id = :t AND data_class = 'aday' "
                                     "ORDER BY id DESC LIMIT 1"), {"t": tenant}).scalar()
        record("K6 imha: süresi dolmuş kalmadı, tutanak = önceki sayı", "OK" if int(after) == 0 and int(last or 0) == int(before) else "FARK",
               once=before, sonra=after, tutanak=last)

    # ------------------------------------------------------------------ K8 yetki (yalnız okuma)
    A._ready.clear()
    acc = A.effective(engine, tenant, "yetki-denetimi-okuma", admin_mod.is_admin)
    record("K8 Herkes rolü İK sayfasını açmaz", "OK" if not acc.can("sayfa:ik-ise-alim") else "FARK", herkes_butun=acc.all)
    if args.api:
        code, _ = http("GET", "/api/v1/hr/recruit/pipeline")
        record("K8b API pano (yönetici oturumu)", "OK" if code == 200 else "FARK", durum=code)
        code, body = http("POST", "/api/v1/hr/recruit/candidates", {})
        record("K8c yönetici rolsüz aday ekleyemez (403) ya da boş gövde 422", "OK" if code in (403, 422) else "FARK", durum=code)
        code, _ = http("POST", "/api/v1/hr/recruit/intake", {})
        record("K8d intake çerezle kapalı (yönetici hariç)", "OK" if code in (403, 422) else "FARK", durum=code)
        if args.yazma:
            write_flow(args, engine, tenant)
    return finish(args)


def write_flow(args, engine, tenant: str) -> None:
    """Geçici İK rolü → yapay aday + özgeçmiş → kanıtlı özet (model izi) → e-posta aktarımı (tekrar yok). Kimlikler dosyaya."""
    ids: dict = {"roles": [], "candidates": [], "positions": []}
    user = os.environ.get("KABUL_USER", "timasai")

    def save() -> None:
        Path(args.ids).write_text(json.dumps(ids, ensure_ascii=False))

    try:
        role = A.save_role(engine, tenant, user, {"name": f"{TEST_NAME} (silinecek)", "perms": [
            "sayfa:ik-ise-alim", "sayfa:ik-pozisyonlar", "ozellik:ik.aday-hepsi", "ozellik:ik.aday-karar", "ozellik:ik.pozisyon-ac"]})
        ids["roles"].append(role["id"])
        save()
        A.add_binding(engine, tenant, user, role["id"], {"type": "user", "subject": user})
        A.invalidate()
        time.sleep(31)                                   # köprünün yetki belleği 30 sn
        code, pos = http("POST", "/api/v1/hr/recruit/positions", {"title": f"{TEST_NAME} redaktör", "competencies": ["Redaksiyon", "İngilizce"]})
        record("Y1 pozisyon aç", "OK" if code == 201 else "FARK", durum=code)
        if code != 201:
            return
        ids["positions"].append(pos["id"])
        save()
        code, cand = http("POST", "/api/v1/hr/recruit/candidates", {"fullName": TEST_NAME, "positionId": pos["id"]})
        record("Y2 aday aç", "OK" if code == 201 else "FARK", durum=code)
        if code != 201:
            return
        ids["candidates"].append(cand["id"])
        save()
        req = urllib.request.Request(os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795")
                                     + f"/api/v1/hr/recruit/candidates/{cand['id']}/files?filename=kabul.txt",
                                     method="POST", data=FAKE_CV.encode(), headers={"Cookie": os.environ["TIMAS_COOKIE"],
                                                                                    "Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=120) as r:
            up = json.loads(r.read())
        record("Y3 özgeçmiş maskesi", "OK" if up["maskCounts"].get("kimlik") == 1 and up["maskCounts"].get("telefon") == 1 else "FARK",
               maske=up["maskCounts"])
        started = datetime.now(timezone.utc)
        code, job = http("POST", f"/api/v1/hr/recruit/candidates/{cand['id']}/evidence", {})
        if code == 202:
            for _ in range(120):
                code, job = http("GET", f"/api/v1/hr/jobs/{job['id']}")
                if job.get("state") != "calisiyor":
                    break
                time.sleep(2)
        record("Y4 kanıtlı özet işi", "OK" if job.get("state") == "bitti" else "FARK", is_=job)
        with engine.connect() as c:
            rows = c.execute(sa.text("SELECT purpose, question FROM sl_llm_queue WHERE purpose LIKE '%ik%' AND enqueued_at >= :s "
                                     "ORDER BY enqueued_at DESC"), {"s": started}).all()
        leaked = [r.question for r in rows if "redaktör" in (r.question or "") or "KABUL" in (r.question or "")]
        record("K7 model izi: sıra kaydında yalnız etiket", "OK" if rows and not leaked and all((r.question or "").startswith("ik:") for r in rows) else "FARK",
               satir=len(rows), ornek=[r.question for r in rows[:3]], sizan=len(leaked), saklama="ölçülecek")
        body = {"messageId": f"<kabul-m55-{started.timestamp()}@example.invalid>", "from": {"name": TEST_NAME, "email": "kabul@example.invalid"},
                "subject": f"{TEST_NAME} redaktör başvurusu", "body": "Yapay kabul iletisi.",
                "attachments": [{"filename": "kabul.txt", "contentBase64": base64.b64encode(FAKE_CV.encode()).decode()}]}
        code, first = http("POST", "/api/v1/hr/recruit/intake", body, cookie=False, token=True)
        if code == 201:
            ids["candidates"].append(first["id"])
            save()
        code2, second = http("POST", "/api/v1/hr/recruit/intake", body, cookie=False, token=True)
        record("Y5 e-postadan başvuru bir kez", "OK" if code == 201 and first.get("created") and second.get("created") is False else "FARK",
               ilk=[code, first.get("files") if isinstance(first, dict) else first], ikinci=[code2, second])
    finally:
        save()


def finish(args) -> int:
    Path(args.out).write_text(json.dumps({"zaman": datetime.now().isoformat(), "sonuc": RESULTS}, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] != "OK"]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} OK · FARK {sum(r['durum'] == 'FARK' for r in RESULTS)} · "
          f"DOĞRULANAMADI {sum(r['durum'] == 'DOĞRULANAMADI' for r in RESULTS)} → {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
