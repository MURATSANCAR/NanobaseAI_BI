#!/usr/bin/env python3
"""M57 Eğitim ve gelişim — test sunucusunda gerçek Logo ve köprü veritabanıyla kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M57/kabul.py --out /tmp/claude-<oturum>/m57-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M57/kabul.py --api
    # Yazma akışı (geçici rol, yapay eğitim/oturum, anket, rehber, ziyaret sayacı): kimlikler --ids dosyasına, temizlik.py siler.
    ... kabul.py --api --yazma --ids /tmp/claude-<oturum>/m57-ids.json

Her kontrol: OK / FARK / DOĞRULANAMADI. Portal tarafı köprünün ekrana verdiği değerdir (API, yoksa aynı işlev); referans
aynı veritabanında bağımsız SQL'dir (referans.sql). Uygulamanın SQL'i yeniden koşturulmaz.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import access as A  # noqa: E402
from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import hr_core as H  # noqa: E402
from semantic_bridge import hr_learning as L  # noqa: E402
from semantic_bridge import hr_learning_sources as S  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
TEST_NAME = "KABUL TESTİ M57"
CLOSE = "('711','721','731','741','751','761','771','781','791')"


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:500]}")


def http(method: str, path: str, body=None, cookie: bool = True, token: bool = False, raw: bytes | None = None):
    url = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795") + path
    headers = {"Content-Type": "application/octet-stream" if raw is not None else "application/json"}
    if cookie and os.environ.get("TIMAS_COOKIE"):
        headers["Cookie"] = os.environ["TIMAS_COOKIE"]
    if token and os.environ.get("SEMANTIC_CALLER_TOKEN"):
        headers["X-Semantic-Caller"] = os.environ["SEMANTIC_CALLER_TOKEN"]
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            out = r.read()
            return r.status, (json.loads(out) if out[:1] in (b"{", b"[") else out)
    except urllib.error.HTTPError as e:
        out = e.read()
        try:
            return e.code, json.loads(out)
        except ValueError:
            return e.code, out[:300]


def firm_of(logo, year: int) -> str | None:
    """Bağımsız yıl → firma: L_CAPIPERIOD, kopya firmalar (SEMANTIC_EXCLUDE_CONTEXT) hariç, en büyük numara."""
    skip = {int(x) for x in os.environ.get("SEMANTIC_EXCLUDE_CONTEXT", "015,016").split(",") if x.strip().isdigit()}
    rows = logo(f"SELECT FIRMNR FROM L_CAPIPERIOD WHERE ACTIVE = 1 AND YEAR(BEGDATE) <= {year} AND YEAR(ENDDATE) >= {year}")
    firms = sorted(int(r["FIRMNR"]) for r in rows if int(r["FIRMNR"]) not in skip)
    return f"{firms[-1]:03d}" if firms else None


def acc(code: str) -> str:
    return f"a.CODE = '{code}' OR a.CODE LIKE '{code}.%'"


def strings(v) -> set[str]:
    out: set[str] = set()
    if isinstance(v, dict):
        for k, x in v.items():
            out.add(str(k))
            out |= strings(x)
    elif isinstance(v, list):
        for x in v:
            out |= strings(x)
    elif isinstance(v, str):
        out.add(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m57-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m57-ids.json")
    ap.add_argument("--ozet", action="store_true", help="zamanlayıcı ucunu gerçekten çağır (İK alıcılarına e-posta gidebilir)")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    L.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    st = L.settings(admin_mod.conf)
    year = L.today().year
    try:
        logo = bsrc.runner(SemanticSettings.from_env().connection_file, 600)
    except Exception as e:  # noqa: BLE001
        logo = None
        record("Logo bağlantısı", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K1 eğitim gider hesabı adayları (ölçüm)
    if logo is not None:
        try:
            if args.api:
                code, body = http("GET", f"/api/v1/hr/learning/spend/accounts?year={year}")
                portal = {x["code"] for x in body.get("items", [])} if code == 200 else None
                if code != 200:
                    record("K1 API aday hesaplar", "DOĞRULANAMADI", durum=code, cevap=str(body)[:200])
            else:
                portal = {x["code"] for x in S.read_candidates(SemanticSettings.from_env().connection_file, year)}
            firm = firm_of(logo, year)
            words = ("eğitim", "EĞİTİM", "egitim", "EGITIM", "Eğitim", "Egitim", "seminer", "SEMİNER", "SEMINER", "Seminer",
                     "kurs", "KURS", "Kurs")
            ref = {str(r["CODE"]).strip() for r in logo(
                f"SELECT CODE FROM LG_{firm}_EMUHACC WHERE CODE LIKE '7%' AND (" + " OR ".join(f"DEFINITION_ LIKE N'%{w}%'" for w in words) + ")")}
            if portal is not None:
                record("K1 eğitim gider hesabı adayları (ölçüm; İK ve Mali İşler seçer)", "OK" if portal == ref else "FARK",
                       portal=len(portal), referans=len(ref), hesaplar=sorted(ref)[:40], secili=st["accounts"])
        except Exception as e:  # noqa: BLE001
            record("K1 eğitim gider hesabı adayları", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K2 eğitim gideri, yıl yıl
    if logo is not None and st["accounts"]:
        for y in range(2021, year + 1):
            try:
                if args.api:
                    code, body = http("GET", f"/api/v1/hr/learning/spend?year={y}")
                    if code != 200:
                        record(f"K2 eğitim gideri {y}", "DOĞRULANAMADI", durum=code, cevap=str(body)[:200])
                        continue
                    portal = body["total"]
                else:
                    portal = S.read_spend(SemanticSettings.from_env().connection_file, y, st["accounts"])["total"]
                firm = firm_of(logo, y)
                if not firm:
                    record(f"K2 eğitim gideri {y}", "DOĞRULANAMADI", neden="Logo'da dönem yok")
                    continue
                ref = logo(
                    f"SELECT SUM(l.DEBIT - l.CREDIT) AS v FROM LG_{firm}_01_EMFLINE l JOIN LG_{firm}_EMUHACC a ON a.LOGICALREF = l.ACCOUNTREF "
                    f"WHERE l.CANCELLED = 0 AND (" + " OR ".join(acc(c) for c in st["accounts"]) + ") "
                    f"AND l.DATE_ >= '{y}-01-01' AND l.DATE_ < '{y + 1}-01-01' "
                    f"AND l.ACCFICHEREF NOT IN (SELECT k.ACCFICHEREF FROM LG_{firm}_01_EMFLINE k JOIN LG_{firm}_EMUHACC ka "
                    f"ON ka.LOGICALREF = k.ACCOUNTREF WHERE k.CANCELLED = 0 AND k.SIGN = 0 AND SUBSTRING(ka.CODE, 1, 3) IN {CLOSE})")[0]["v"]
                ref_v = round(float(ref or 0), 2)
                record(f"K2 eğitim gideri {y} (firma {firm})", "OK" if abs(float(portal or 0) - ref_v) <= 0.01 else "FARK",
                       portal=portal, referans=ref_v)
            except Exception as e:  # noqa: BLE001
                record(f"K2 eğitim gideri {y}", "DOĞRULANAMADI", hata=str(e)[:300])
    elif logo is not None:
        record("K2 eğitim gideri", "DOĞRULANAMADI", neden="HR_TRAINING_ACCOUNTS ayarlanmadı (ölçülecek: K1 listesinden Mali İşler seçer)")

    # ------------------------------------------------------------------ K3–K5 kullanım haritası
    umap = None
    if args.api:
        code, umap = http("GET", "/api/v1/hr/learning/usage-map?days=30")
        if code != 200:
            record("K3 API kullanım haritası", "DOĞRULANAMADI", durum=code, cevap=str(umap)[:200])
            umap = None
    if umap is None:
        umap = S.usage_map(engine, tenant, 30, st["minGroup"])
    totals = umap["totals"]
    with engine.connect() as c:
        try:
            ref3 = c.execute(sa.text(
                "SELECT COUNT(DISTINCT lower(split_part(regexp_replace(username, '^.*\\\\', ''), '@', 1))) FROM sl_query_log "
                "WHERE tenant_id = :t AND username IS NOT NULL AND username <> '' AND created_at >= now() - interval '30 days'"),
                {"t": tenant}).scalar()
            record("K3 Zeki AI soru — son 30 gün farklı kişi", "OK" if int(ref3 or 0) == int(totals.get(S.ZEKI, 0)) else "FARK",
                   portal=totals.get(S.ZEKI, 0), referans=ref3, not_="pencere sınırında yeni soru gelirse ±1 olabilir; tekrar koşturun")
        except Exception as e:  # noqa: BLE001
            record("K3 Zeki AI soru", "DOĞRULANAMADI", hata=str(e)[:300])
        try:
            rows = c.execute(sa.text(
                "SELECT kind, COUNT(DISTINCT lower(split_part(regexp_replace(actor, '^.*\\\\', ''), '@', 1))) AS n FROM semantic_audit "
                "WHERE at >= now() - interval '30 days' AND lower(actor) NOT IN ('sistem', 'eposta') GROUP BY kind")).all()
            ref4 = {f"audit:{r.kind}": int(r.n) for r in rows}
            app4 = {k: v for k, v in totals.items() if k.startswith("audit:")}
            diff = {k: [app4.get(k), ref4.get(k)] for k in set(app4) | set(ref4) if app4.get(k) != ref4.get(k)}
            record("K4 değişiklik kaydı türü başına farklı kişi", "OK" if not diff else "FARK", tur=len(ref4), fark=diff)
        except Exception as e:  # noqa: BLE001
            record("K4 değişiklik kaydı", "DOĞRULANAMADI", hata=str(e)[:300])
        rows = c.execute(sa.text(
            "SELECT route_prefix, COUNT(DISTINCT username) AS n FROM semantic_hr_page_visits WHERE tenant_id = :t "
            "AND day >= (now() AT TIME ZONE 'Europe/Istanbul')::date - 29 GROUP BY route_prefix"), {"t": tenant}).all()
        ref5 = {r.route_prefix: int(r.n) for r in rows}
        app5 = {k: v for k, v in totals.items() if not k.startswith("audit:") and k != S.ZEKI}
        diff = {k: [app5.get(k), ref5.get(k)] for k in set(app5) | set(ref5) if app5.get(k) != ref5.get(k)}
        record("K5 ekran ziyareti — ekran başına farklı kişi", "OK" if not diff else "FARK", ekran=len(ref5), fark=diff,
               not_="sayaç yeni kurulduysa ekran sayısı az olur; boş da olabilir")
        users = {str(u) for u in c.execute(sa.text("SELECT username FROM semantic_hr_employees WHERE tenant_id = :t AND username IS NOT NULL"),
                                           {"t": tenant}).scalars()}
    leaked = sorted(users & strings(umap))
    record("K9 kullanım haritasında hesap adı yok", "OK" if not leaked else "FARK", sizan=len(leaked))

    # ------------------------------------------------------------------ K6 zorunlu eğitim durumu
    days = st["alertDays"] or 0
    portal6 = {"hic_yok": 0, "doldu": 0, "dolacak": 0}
    for x in L.mandatory_status(engine, tenant, days=days):
        if x["status"] in portal6:
            portal6[x["status"]] += 1
    if args.api:
        code, body = http("GET", f"/api/v1/hr/learning/expiring?days={days}")
        if code == 200:
            portal6 = {"hic_yok": 0, "doldu": 0, "dolacak": 0}
            for x in body["items"]:
                portal6[x["status"]] += 1
        else:
            record("K6 API dolacak listesi", "DOĞRULANAMADI", durum=code, neden="rolde ik.egitim-yonet yoksa 403 beklenir")
    with engine.connect() as c:
        r6 = c.execute(sa.text("""
WITH k AS (SELECT id, required_units_json FROM semantic_hr_courses WHERE tenant_id = :t AND kind = 'zorunlu' AND active),
     e AS (SELECT id, unit_id FROM semantic_hr_employees WHERE tenant_id = :t AND status = 'aktif'),
     pairs AS (SELECT e.id AS employee_id, k.id AS course_id FROM e JOIN k
                 ON k.required_units_json IS NULL OR k.required_units_json::jsonb ? e.unit_id),
     last AS (SELECT employee_id, course_id, bool_or(expires_on IS NULL) AS suresiz, max(expires_on) AS son
                FROM semantic_hr_certificates WHERE tenant_id = :t AND verified_at IS NOT NULL GROUP BY employee_id, course_id)
SELECT COALESCE(SUM(CASE WHEN l.employee_id IS NULL THEN 1 ELSE 0 END), 0) AS hic_yok,
       COALESCE(SUM(CASE WHEN NOT l.suresiz AND l.son < (now() AT TIME ZONE 'Europe/Istanbul')::date THEN 1 ELSE 0 END), 0) AS doldu,
       COALESCE(SUM(CASE WHEN NOT l.suresiz AND l.son >= (now() AT TIME ZONE 'Europe/Istanbul')::date
                 AND l.son < (now() AT TIME ZONE 'Europe/Istanbul')::date + :gun THEN 1 ELSE 0 END), 0) AS dolacak
  FROM pairs p LEFT JOIN last l ON l.employee_id = p.employee_id AND l.course_id = p.course_id"""), {"t": tenant, "gun": days}).first()
    ref6 = {"hic_yok": int(r6.hic_yok), "doldu": int(r6.doldu), "dolacak": int(r6.dolacak)}
    record(f"K6 zorunlu eğitim durumu (gün = {days})", "OK" if ref6 == portal6 else "FARK", portal=portal6, referans=ref6,
           not_=None if st["alertDays"] else "HR_LEARNING_ALERT_DAYS ayarlanmadı: yalnız dolmuş/hiç almamış sayılır")

    # ------------------------------------------------------------------ K7 tamamlanma
    dash = L.dashboard(engine, tenant, alert_days=st["alertDays"], people=False)
    app7 = {((m["unitId"] or "-"), m["courseId"]): (m["enrolled"], m["completed"]) for m in dash["matrix"]}
    with engine.connect() as c:
        rows = c.execute(sa.text(
            "SELECT COALESCE(e.unit_id, '-') AS u, s.course_id AS k, COUNT(*) AS n, "
            "COUNT(*) FILTER (WHERE n.completed_at IS NOT NULL) AS d FROM semantic_hr_enrollments n "
            "JOIN semantic_hr_sessions s ON s.id = n.session_id LEFT JOIN semantic_hr_employees e ON e.id = n.employee_id "
            "WHERE n.tenant_id = :t AND n.approval = 'onaylandi' AND s.state <> 'iptal' GROUP BY 1, 2"), {"t": tenant}).all()
    ref7 = {(r.u, r.k): (int(r.n), int(r.d)) for r in rows}
    record("K7 birim × eğitim tamamlanma", "OK" if app7 == ref7 else "FARK", hucre=len(ref7),
           fark={f"{k[0]}/{k[1]}": [app7.get(k), ref7.get(k)] for k in set(app7) | set(ref7) if app7.get(k) != ref7.get(k)})

    # ------------------------------------------------------------------ K8 anonim şema
    with engine.connect() as c:
        cols = {r[0] for r in c.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'semantic_hr_learning_feedback'")).all()}
    bad = cols & {"employee_id", "username", "user", "actor", "created_by", "submitted_at"}
    record("K8 anket yanıt tablosunda kişi ve saat kolonu yok", "OK" if cols and not bad else "FARK", kolonlar=sorted(cols))

    # ------------------------------------------------------------------ K10 yetki (okuma)
    A._ready.clear()
    acc_ = A.effective(engine, tenant, "yetki-denetimi-okuma", admin_mod.is_admin)
    record("K10 Herkes rolü eğitim sayfalarını açmaz", "OK" if not acc_.can("sayfa:ik-egitim") and not acc_.can("sayfa:ik-egitimlerim") else "FARK")
    if args.api:
        code, _ = http("GET", "/api/v1/hr/learning/me/usage?user=baskasi-kabul")
        record("K10b kişi bazında kullanım başkasına 403 (İK dahil)", "OK" if code == 403 else "FARK", durum=code)
        code, _ = http("GET", "/api/v1/hr/learning/me")
        record("K10c Eğitimlerim oturumla açık", "OK" if code == 200 else "FARK", durum=code)
    if args.ozet:
        # Gerçek zamanlayıcı ucu: İK alıcıları tanımlıysa özet e-postası GİDER (ilk elle koşu; bellek run-it-before-it-runs-itself).
        code, out = http("POST", "/api/v1/hr/learning/reminders/run-due", {}, cookie=False, token=True)
        record("K10d sabah özeti (sistem jetonu; kişi adı yok)", "OK" if code == 200 else "FARK", durum=code,
               cevap={k: out.get(k) for k in ("lines", "mail", "recipients")} if isinstance(out, dict) else str(out)[:200])
    if args.api:
        if args.yazma:
            write_flow(args, engine, tenant)
    return finish(args)


def write_flow(args, engine, tenant: str) -> None:
    """Geçici rol → yapay eğitim ve geçmiş tarihli oturum → yoklama ve kapanış → anket (ikinci gönderim 409) → rehber
    (altyapı adı reddi, yayım, oy) → ziyaret sayacı. Bütün kimlikler --ids dosyasına; temizlik.py siler."""
    user = os.environ.get("KABUL_USER", "timasai")
    ids: dict = {"user": user, "start": datetime.now(timezone.utc).isoformat(), "roles": [], "courses": [], "sessions": [],
                 "guides": [], "employee_created": None, "visit_before": None}

    def save() -> None:
        Path(args.ids).write_text(json.dumps(ids, ensure_ascii=False))

    save()
    try:
        role = A.save_role(engine, tenant, user, {"name": f"{TEST_NAME} (silinecek)", "perms": [
            "sayfa:ik-egitim", "sayfa:ik-egitimlerim", L.F_MANAGE, L.F_GUIDES, L.F_USAGE]})
        ids["roles"].append(role["id"])
        save()
        A.add_binding(engine, tenant, user, role["id"], {"type": "user", "subject": user})
        A.invalidate()
        emp = H.employee_by_username(engine, tenant, user)
        if emp is None:
            emp, _ = H.save_employee(engine, tenant, user, {"displayName": f"{TEST_NAME} çalışanı", "username": user})
            ids["employee_created"] = emp["id"]
        save()
        time.sleep(31)                                   # köprünün yetki belleği 30 sn
        code, course = http("POST", "/api/v1/hr/learning/courses",
                            {"title": f"{TEST_NAME} gelişim", "kind": "gelisim", "delivery": "ic", "validityDays": 30})
        record("Y1 eğitim kartı", "OK" if code == 201 else "FARK", durum=code)
        if code != 201:
            return
        ids["courses"].append(course["id"])
        save()
        start = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        code, sess = http("POST", "/api/v1/hr/learning/sessions", {"courseId": course["id"], "startsAt": start, "employeeIds": [emp["id"]]})
        record("Y2 oturum ve katılımcı", "OK" if code == 201 and sess["counts"]["approved"] == 1 else "FARK", durum=code)
        if code != 201:
            return
        ids["sessions"].append(sess["id"])
        save()
        code, _ = http("POST", f"/api/v1/hr/learning/sessions/{sess['id']}/close")
        record("Y3 yoklamasız kapanış reddedilir (409)", "OK" if code == 409 else "FARK", durum=code)
        enr = sess["enrollments"][0]["id"]
        http("POST", f"/api/v1/hr/learning/sessions/{sess['id']}/attendance", {"items": [{"enrollmentId": enr, "attendance": "katildi"}]})
        code, out = http("POST", f"/api/v1/hr/learning/sessions/{sess['id']}/close")
        record("Y4 kapanış: tamamlanan 1, anket 1", "OK" if code == 200 and out.get("completed") == 1 else "FARK", durum=code, cevap=out)
        with engine.connect() as c:
            cert = c.execute(sa.text("SELECT issued_on, expires_on, verified_at IS NOT NULL AS v FROM semantic_hr_certificates "
                                     "WHERE session_id = :s"), {"s": sess["id"]}).first()
        ok = cert is not None and cert.v and (cert.expires_on - cert.issued_on).days == 30
        record("Y5 sertifika: doğrulanmış, geçerlilik 30 gün", "OK" if ok else "FARK", sertifika=dict(cert._mapping) if cert else None)
        code, me = http("GET", "/api/v1/hr/learning/me")
        token = next((f["token"] for f in me.get("feedback", []) if f["sessionId"] == sess["id"]), None) if code == 200 else None
        if token:
            c1, _ = http("POST", f"/api/v1/hr/learning/me/feedback/{token}", {"answers": {"genel": 4}, "comment": "Kabul testi yorumu"})
            c2, _ = http("POST", f"/api/v1/hr/learning/me/feedback/{token}", {"answers": {"genel": 1}})
            record("Y6 anket: ilk 200, ikinci 409", "OK" if (c1, c2) == (200, 409) else "FARK", durum=[c1, c2])
            with engine.connect() as c:
                n = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_learning_feedback WHERE session_id = :s"), {"s": sess["id"]}).scalar()
            record("Y6b yanıt satırı 1, kişisiz", "OK" if int(n) == 1 else "FARK", satir=n)
        else:
            record("Y6 anket jetonu", "FARK", neden="Eğitimlerim'de jeton görünmedi", durum=code)
        code, g = http("POST", "/api/v1/hr/learning/guides", {"moduleRoute": "ik-egitim", "title": f"{TEST_NAME} rehber",
                                                                "body": "Bu ekran Qwen ile çalışır."})
        if code == 201:
            ids["guides"].append(g["id"])
            save()
            c1, _ = http("POST", f"/api/v1/hr/learning/guides/{g['id']}/publish")
            http("PATCH", f"/api/v1/hr/learning/guides/{g['id']}", {"body": "## Adımlar\n1. Zeki AI önerisini okuyun."})
            c2, pub = http("POST", f"/api/v1/hr/learning/guides/{g['id']}/publish")
            c3, _ = http("POST", f"/api/v1/hr/learning/me/guides/{g['id']}/vote", {"useful": True})
            record("Y7 rehber: altyapı adı 422, düzeltince yayın, oy", "OK" if (c1, c2, c3) == (422, 200, 200) else "FARK", durum=[c1, c2, c3])
        else:
            record("Y7 rehber", "FARK", durum=code, cevap=str(g)[:200], not_="ik-egitim rehberi zaten varsa 409 beklenir")
        day = L.today()
        with engine.connect() as c:
            before = c.execute(sa.text("SELECT count FROM semantic_hr_page_visits WHERE tenant_id = :t AND day = :d AND "
                                       "route_prefix = 'ik-egitim' AND username = :u"), {"t": tenant, "d": day, "u": user}).scalar()
        ids["visit_before"] = {"day": day.isoformat(), "count": before}
        save()
        code, _ = http("POST", "/api/v1/hr/visit", {"route": "ik-egitim"})
        with engine.connect() as c:
            after = c.execute(sa.text("SELECT count FROM semantic_hr_page_visits WHERE tenant_id = :t AND day = :d AND "
                                      "route_prefix = 'ik-egitim' AND username = :u"), {"t": tenant, "d": day, "u": user}).scalar()
        record("Y8 ziyaret sayacı +1", "OK" if code == 200 and int(after or 0) == int(before or 0) + 1 else "FARK", once=before, sonra=after)
        code, _ = http("POST", "/api/v1/hr/visit", {"route": "../yonetim"})
        record("Y8b geçersiz ekran kimliği 422", "OK" if code == 422 else "FARK", durum=code)
    finally:
        save()
        print(f"Kimlikler {args.ids} dosyasında; temizlik: python3 ../scripts/acceptance/M57/temizlik.py --ids {args.ids}")


def finish(args) -> int:
    Path(args.out).write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "sonuclar": RESULTS}, ensure_ascii=False,
                                         indent=2, default=str))
    counts: dict[str, int] = {}
    for r in RESULTS:
        counts[r["durum"]] = counts.get(r["durum"], 0) + 1
    print(json.dumps(counts, ensure_ascii=False))
    return 0 if not counts.get("FARK") else 1


if __name__ == "__main__":
    sys.exit(main())
