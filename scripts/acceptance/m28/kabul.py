#!/usr/bin/env python3
"""M28 Kurumsal ilişkiler — test sunucusunda gerçek CRM ile kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla; önce köprü yeni kodla yeniden yüklenmiş olmalı):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/m28/kabul.py --out /tmp/claude-<oturum>/m28-kabul.json
    # API tarafı (uygulamanın ekrana verdiği değer): timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/m28/kabul.py --api
    # Yazma akışı (kişi kartı + iki kez aynı hediye → 409, yasak alan → 422, bütçe kapısı → 400); kimlikler --ids
    # dosyasına yazılır, ardından temizlik.py siler:
    ... kabul.py --api --yazma --ids /tmp/claude-<oturum>/m28-ids.json
    python3 ../scripts/acceptance/m28/temizlik.py --ids /tmp/claude-<oturum>/m28-ids.json

Her kontrol: OK / FARK / DOĞRULANAMADI. Portal değeri API'den (ya da köprünün kendi tablosundan) okunur; referans aynı
CRM'de bağımsız SQL'dir (referans.sql). Uygulamanın SQL'i yeniden koşturulmaz. CRM'e yazılmaz.
Ölçülecekler (kodda ayar, burada ölçülür): iptal/birleştirilmiş sipariş kodları, sipariş satırı düzeyinde iptal
(`new_siparissatiriBase.statuscode` 100000001) toplamı ne kadar değiştiriyor, «kanaat önderi» diye bir CRM kişi rolü var mı.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import public_affairs as PA  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
IDS: dict[str, list[str]] = {"people": [], "gifts": [], "projects": [], "notes": [], "orgs": []}


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:400]}")


def api(method: str, path: str, body=None, expect_json: bool = True):
    base = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795").rstrip("/")
    cookie = os.environ.get("TIMAS_COOKIE", "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"cookie": cookie, "Content-Type": "application/json", "Origin": base})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if expect_json else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode("utf-8", "replace")[:300]


def q(s: str) -> str:
    return s.replace("'", "''")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m28-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m28-ids.json")
    ap.add_argument("--ornek", type=int, default=5, help="il/sözcük başına örnek sayısı (en az 5)")
    ap.add_argument("--yil", type=int, default=date.today().year)
    args = ap.parse_args()
    n = max(5, args.ornek)

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    PA.ensure(engine)
    admin_mod.ensure(engine)
    st = PA.settings_from(admin_mod.conf)
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    schema = admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo")
    p = schema.rstrip(".") + "."
    try:
        crm = bsrc.runner(crm_file)
        crm("SELECT 1 AS ok")
    except Exception as e:  # noqa: BLE001
        record("CRM bağlantısı", "DOĞRULANAMADI", hata=str(e)[:300])
        return finish(args)
    use_api = args.api and os.environ.get("TIMAS_COOKIE")
    if args.api and not use_api:
        record("API", "DOĞRULANAMADI", neden="TIMAS_COOKIE verilmedi")

    # K1 — il istatistiği: okul sayısı ve öğrenci toplamı en kalabalık n ilde
    cities = crm(f"""SELECT TOP {n} z.new_ili AS il, i.new_name AS ad, COUNT(*) AS c FROM {p}new_ziyaretyerleriBase z
JOIN {p}new_illerBase i ON i.new_illerId = z.new_ili WHERE z.statecode = 0 AND z.new_KurumTipi = 1
GROUP BY z.new_ili, i.new_name ORDER BY COUNT(*) DESC""")
    for c in cities:
        il = str(c["il"]).strip("{}").lower()
        ref = crm(f"""SELECT COUNT(z.new_ziyaretyerleriId) AS kurum, SUM(TRY_CAST(z.new_renciSays AS int)) AS ogrenci,
SUM(CASE WHEN TRY_CAST(z.new_renciSays AS int) IS NULL THEN 1 ELSE 0 END) AS sayisiz
FROM {p}new_ziyaretyerleriBase z WHERE z.statecode = 0 AND z.new_KurumTipi = 1 AND z.new_ili = '{il}'""")[0]
        bos = crm(f"""SELECT COUNT(*) AS bos FROM {p}new_ziyaretyerleriBase z WHERE z.statecode = 0 AND z.new_KurumTipi = 1
AND z.new_ili = '{il}' AND LTRIM(RTRIM(z.new_renciSays)) = N''""")[0]["bos"]
        if not use_api:
            record(f"K1 il istatistiği {c['ad']}", "DOĞRULANAMADI", referans=ref, bos=bos, neden="API yok")
            continue
        code, app = api("GET", f"/api/v1/public-affairs/crm/city-stats?il={il}&kurumTipi=1")
        ok = code == 200 and app["places"] == int(ref["kurum"] or 0) and app["students"] == int(ref["ogrenci"] or 0) \
            and app["studentsUnknown"] == int(ref["sayisiz"] or 0) + int(bos or 0)
        record(f"K1 il istatistiği {c['ad']}", "OK" if ok else "FARK", portal=app, referans=ref, bos=bos)

    # K2–K3 — tanıtım/bağış/örnek siparişleri (yıl)
    y = args.yil
    ref_rows = crm(f"""SELECT CAST(s.new_siparistipi AS int) AS tip, COUNT(DISTINCT s.new_siparisId) AS siparis, SUM(ss.new_adet) AS adet
FROM {p}new_siparisBase s JOIN {p}new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId
WHERE s.new_siparistipi IN (10, 11, 12, 15)
  AND DATEADD(hour, 3, s.new_siparistarihi) >= '{y}-01-01' AND DATEADD(hour, 3, s.new_siparistarihi) < '{y + 1}-01-01'
  AND s.statuscode NOT IN (SELECT m.AttributeValue FROM {p}StringMapBase m WHERE m.AttributeName = 'statuscode' AND m.LangId = 1055
      AND m.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_siparis')
      AND (m.Value LIKE N'%İptal%' OR m.Value LIKE N'%Birleştir%'))
GROUP BY s.new_siparistipi""")
    ref = {int(r["tip"]): r for r in ref_rows}
    excluded = crm(f"""SELECT m.AttributeValue AS kod, m.Value AS ad FROM {p}StringMapBase m WHERE m.AttributeName = 'statuscode'
AND m.LangId = 1055 AND m.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_siparis')
AND (m.Value LIKE N'%İptal%' OR m.Value LIKE N'%Birleştir%')""")
    record("K2 ön koşul: sayılmayan durum kodları ayarla aynı mı", "OK" if sorted(int(r["kod"]) for r in excluded) == st["excludedStatus"] else "FARK",
           crm=excluded, ayar=st["excludedStatus"])
    line_cancel = crm(f"""SELECT SUM(ss.new_adet) AS adet FROM {p}new_siparisBase s JOIN {p}new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId
WHERE s.new_siparistipi IN (10, 11, 12, 15) AND ss.statuscode = 100000001
  AND DATEADD(hour, 3, s.new_siparistarihi) >= '{y}-01-01' AND DATEADD(hour, 3, s.new_siparistarihi) < '{y + 1}-01-01'""")[0]["adet"]
    record("ölçüm: satır düzeyinde iptal edilmiş adet (toplamda sayılıyor)", "OK", adet=line_cancel,
           not_="0 değilse satır iptali de düşülmeli mi karar verilir; günlüğe yaz")
    if use_api:
        code, rep = api("GET", f"/api/v1/public-affairs/report?year={y}")
        app = {t["type"]: t for t in (rep.get("crm", {}).get("types") or [])} if code == 200 else {}
        for tip in (12, 15, 10, 11):
            r = ref.get(tip, {"siparis": 0, "adet": 0})
            a = app.get(tip, {"orders": 0, "books": 0})
            ok = code == 200 and int(a["orders"]) == int(r["siparis"] or 0) and int(a["books"]) == int(float(r["adet"] or 0))
            record(f"K2/K3 sipariş tipi {tip} ({y})", "OK" if ok else "FARK", portal=a, referans=r)
    else:
        record("K2/K3 sipariş tipleri", "DOĞRULANAMADI", referans=ref_rows, neden="API yok")

    # K4 — «Karar Veren» rolündeki etkin kişi
    ref_dm = crm(f"SELECT COUNT(*) AS n FROM {p}ContactBase WHERE statecode = 0 AND AccountRoleCode = 1")[0]["n"]
    if use_api:
        code, roles = api("GET", "/api/v1/public-affairs/crm/roles")
        record("K4 Karar Veren kişi sayısı", "OK" if code == 200 and roles["decisionMakers"] == int(ref_dm) else "FARK",
               portal=roles.get("decisionMakers") if code == 200 else roles, referans=ref_dm)
        names = [r["name"] for r in roles.get("personRoles", [])] if code == 200 else []
        record("ölçüm: CRM kişi rolleri (kanaat önderi rolü var mı)", "OK", roller=names)
    else:
        record("K4 Karar Veren kişi sayısı", "DOĞRULANAMADI", referans=ref_dm, neden="API yok")

    # K5 — CRM kişi ve ziyaret yeri araması toplamları (n sözcük)
    words = ["ahmet", "mehmet", "öğretmen", "müdür", "belediye", "üniversite", "okul"][: max(n, 5)]
    for w in words:
        ref_c = crm(f"""SELECT COUNT(*) AS n FROM {p}ContactBase k LEFT JOIN {p}AccountBase a ON a.AccountId = k.ParentCustomerId
WHERE k.statecode = 0 AND (k.FullName LIKE N'%{q(w)}%' OR a.Name LIKE N'%{q(w)}%' OR k.JobTitle LIKE N'%{q(w)}%')""")[0]["n"]
        ref_p = crm(f"""SELECT COUNT(*) AS n FROM {p}new_ziyaretyerleriBase z WHERE z.statecode = 0 AND z.new_KurumTipi = 1
AND (z.new_kurumadi LIKE N'%{q(w)}%' OR z.new_okuladi LIKE N'%{q(w)}%')""")[0]["n"]
        if use_api:
            c1, a1 = api("GET", "/api/v1/public-affairs/crm/contacts?q=" + urllib.parse.quote(w))
            c2, a2 = api("GET", "/api/v1/public-affairs/crm/places?kurumTipi=1&q=" + urllib.parse.quote(w))
            record(f"K5 kişi araması «{w}»", "OK" if c1 == 200 and a1["total"] == int(ref_c) else "FARK",
                   portal=a1.get("total") if c1 == 200 else a1, referans=ref_c)
            record(f"K5 kurum araması «{w}»", "OK" if c2 == 200 and a2["total"] == int(ref_p) else "FARK",
                   portal=a2.get("total") if c2 == 200 else a2, referans=ref_p)
        else:
            record(f"K5 arama «{w}»", "DOĞRULANAMADI", kisi=ref_c, kurum=ref_p, neden="API yok")

    # K6 — ayın yeni kitapları (son n ay)
    today = date.today()
    for i in range(n):
        m = (today.month - 1 - i) % 12 + 1
        yy = today.year + ((today.month - 1 - i) // 12)
        a0 = date(yy, m, 1)
        b0 = date(yy + (m == 12), m % 12 + 1, 1)
        ref_b = crm(f"""SELECT COUNT(*) AS n FROM {p}new_kitapBase b WHERE b.statecode = 0 AND ISNULL(b.new_StokKodu, N'') <> N''
AND ISNULL(CAST(b.new_kitap_yayincilikstatusu AS int), 0) NOT IN (100000001, 100000003, 100000005, 100000006)
AND DATEADD(hour, 3, b.new_ilkyayintarihi) >= '{a0}' AND DATEADD(hour, 3, b.new_ilkyayintarihi) < '{b0}'""")[0]["n"]
        key = f"{yy:04d}-{m:02d}"
        if use_api:
            code, a = api("GET", f"/api/v1/public-affairs/crm/books?month={key}")
            record(f"K6 ayın yeni kitapları {key}", "OK" if code == 200 and a["total"] == int(ref_b) else "FARK",
                   portal=a.get("total") if code == 200 else a, referans=ref_b)
        else:
            record(f"K6 ayın yeni kitapları {key}", "DOĞRULANAMADI", referans=ref_b, neden="API yok")

    # K7 — portal: aynı kişiye aynı kitap tekrarı yok; KVKK alan taraması 0
    with engine.connect() as c:
        dups = c.execute(sa.text("SELECT person_id, crm_book_id, COUNT(*) AS n FROM semantic_rel_gifts WHERE status <> 'iptal' "
                                 "GROUP BY person_id, crm_book_id HAVING COUNT(*) > 1")).fetchall()
        bad = c.execute(sa.text("SELECT key, label FROM semantic_rel_fields WHERE lower(label) LIKE '%inanç%' OR lower(label) LIKE '%mezhep%' "
                                "OR lower(label) LIKE '%cemaat%' OR lower(label) LIKE '%siyasi%' OR lower(label) LIKE '%parti%' "
                                "OR lower(label) LIKE '%etnik%' OR lower(label) LIKE '%sendika%'")).fetchall()
    record("K7 hediye tekrarı (portal tablosu)", "OK" if not dups else "FARK", tekrar=[tuple(r) for r in dups])
    record("K8 KVKK alan taraması (portal tablosu)", "OK" if not bad else "FARK", bulunan=[tuple(r) for r in bad])
    if use_api:
        code, scan = api("GET", "/api/v1/public-affairs/kvkk-scan")
        record("K8b KVKK taraması (uç)", "OK" if code == 200 and scan["count"] == 0 else "FARK", portal=scan)
        code, res = api("POST", "/api/v1/public-affairs/fields", {"label": "Siyasi görüş"})
        record("K8c yasak alan eklenemez (422, kayıt yazılmaz)", "OK" if code == 422 else "FARK", kod=code, cevap=res)

    if args.yazma and use_api:
        write_flow(args)
    return finish(args)


def write_flow(args) -> None:
    """Yazma: yalnız kabul kaydı (adı «KABUL TESTİ M28»), kimlikler dosyaya; temizlik.py siler."""
    try:
        code, person = api("POST", "/api/v1/public-affairs/people", {"name": "KABUL TESTİ M28 kişi", "priority": "kritik", "isPublicOfficial": True})
        if code != 200:
            record("Y1 kişi kartı", "FARK", kod=code, cevap=person)
            return
        IDS["people"].append(person["id"])
        code, books = api("GET", "/api/v1/public-affairs/crm/books?q=" + urllib.parse.quote("tarih"))
        book = (books.get("items") or [None])[0] if code == 200 else None
        if not book:
            record("Y2 hediye tekrarı", "DOĞRULANAMADI", neden="CRM kitap bulunamadı")
        else:
            body = {"personId": person["id"], "crmBookId": book["id"], "bookName": book["name"], "stockCode": book["stockCode"]}
            c1, g1 = api("POST", "/api/v1/public-affairs/gifts", body)
            if c1 == 200:
                IDS["gifts"].append(g1["id"])
            c2, g2 = api("POST", "/api/v1/public-affairs/gifts", dict(body, month="2099-01"))
            if c2 == 200:
                IDS["gifts"].append(g2["id"])
            record("Y2 aynı kişiye aynı kitap ikinci kez → 409", "OK" if c1 == 200 and c2 == 409 else "FARK", ilk=c1, ikinci=c2)
            c3, a3 = api("POST", "/api/v1/public-affairs/gifts/approve", {"ids": [g1["id"]] if c1 == 200 else []})
            record("Y3 kamu görevlisine hukuk onayı işaretlenmeden onay yok", "OK" if c3 == 200 and not a3.get("done") else "FARK", cevap=a3)
        code, n = api("POST", f"/api/v1/public-affairs/people/{person['id']}/notes",
                      {"topic": "KABUL TESTİ not", "text": "gizli", "visibility": "ozel", "date": date.today().isoformat(), "time": "00:00"})
        if code == 200:
            IDS["notes"].append(n["id"])
        record("Y4 gizli not yazıldı (başka kullanıcıyla okuma pytest'te)", "OK" if code == 200 else "FARK", kod=code)
        code, pr = api("POST", "/api/v1/public-affairs/projects", {"title": "KABUL TESTİ M28 proje", "kind": "bagis", "budget": "1000"})
        if code == 200:
            IDS["projects"].append(pr["id"])
            c4, r4 = api("PATCH", f"/api/v1/public-affairs/projects/{pr['id']}", {"stage": "uygulama"})
            record("Y5 bütçe onayı olmadan uygulamaya geçilmez → 400", "OK" if c4 == 400 else "FARK", kod=c4, cevap=r4)
        else:
            record("Y5 proje", "FARK", kod=code, cevap=pr)
    finally:
        Path(args.ids).write_text(json.dumps(IDS, ensure_ascii=False), encoding="utf-8")
        print(f"kimlikler: {args.ids} — temizlik.py ile silin")


def finish(args) -> int:
    Path(args.out).write_text(json.dumps({"at": datetime.now().isoformat(), "sonuclar": RESULTS}, ensure_ascii=False, indent=1, default=str),
                              encoding="utf-8")
    counts: dict[str, int] = {}
    for r in RESULTS:
        counts[r["durum"]] = counts.get(r["durum"], 0) + 1
    print(json.dumps(counts, ensure_ascii=False))
    return 0 if not counts.get("FARK") else 1


if __name__ == "__main__":
    sys.exit(main())
