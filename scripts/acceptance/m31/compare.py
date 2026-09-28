"""M31 Okul tanıtım: gerçek DB kabulü — köprünün cevabı (gerçek oturumla API) ile doğrudan SQL referansı karşılaştırılır.

Test sunucusunda, aday ağaç kurulduktan ve `run-due` bir kez elle koşturulduktan sonra:

    export ADMIN_COOKIE='timas_session=…'   # timasai'nin kısa ömürlü (15 dk) oturumu; iş bitince silinir
    export REP_COOKIE='timas_session=…'     # (isteğe bağlı) okul.herkesinki yetkisi olmayan hesabın oturumu
    /data/nanobaseai/bi/semantic-venv/bin/python compare.py [--write] [--out /tmp/claude-m31/created.json]

Salt okunur; `--write` yalnız 7. kontrol için tek bir ziyaret raporu yazar ve kimliğini `--out` dosyasına koyar
(cleanup.py ile silinir). Her kontrol: ad, sonuç (GEÇTİ/KALDI/DOĞRULANAMADI), ayrıntı.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, os.environ.get("BI_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import school_visits as SV  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--write", action="store_true", help="7. kontrol için bir ziyaret raporu yazar (sonra cleanup.py)")
ap.add_argument("--out", default="/tmp/claude-m31/created.json")
ap.add_argument("--samples", type=int, default=5)
a = ap.parse_args()

BASE = os.environ.get("BRIDGE", "http://127.0.0.1:8795")
TOKEN = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
ADMIN = os.environ["ADMIN_COOKIE"]
REP = os.environ.get("REP_COOKIE", "")
S = "Timas_MSCRM.dbo"
crm = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
logo = connector_from_file(os.environ.get("LOGO_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/logo-mssql-connection.json"))
crm.query_timeout = logo.query_timeout = 900
store = open_store(SemanticSettings.from_env().store_dsn).engine
results = []


def q(conn, sql):
    _, rows, trunc = conn.execute(sql, 5_000_000)
    assert not trunc, "referans sorgusu kesildi"
    return rows


def api(method, path, cookie, body=None, timeout=600):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Cookie": cookie, "X-Semantic-Caller": TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(name, ok, detail):
    status = "GEÇTİ" if ok is True else ("KALDI" if ok is False else "DOĞRULANAMADI")
    results.append({"kontrol": name, "sonuc": status, "ayrinti": detail})
    print(f"[{status}] {name}: {detail}", flush=True)


t0 = time.time()
st, meta = api("GET", "/api/v1/schools/meta", ADMIN)
if st != 200 or not meta["me"]["all"]:
    sys.exit(f"meta {st}: oturum geçersiz ya da okul.herkesinki yok — {meta}")
print("meta", round(time.time() - t0, 1), "sn; okul:", meta["status"].get("schools"))

# 1. il × kademe
ref = {}
for r in q(crm, f"SELECT i.new_name AS il, CAST(z.new_okulkademesi AS int) AS kademe, COUNT(*) AS n FROM {S}.new_ziyaretyerleriBase z "
                f"LEFT JOIN {S}.new_illerBase i ON i.new_illerId = z.new_ili WHERE z.statecode = 0 AND z.new_KurumTipi = 1 "
                "GROUP BY i.new_name, z.new_okulkademesi"):
    key = (SV.fold(r["il"]), r["kademe"])
    ref[key] = ref.get(key, 0) + int(r["n"])
st, allp = api("GET", "/api/v1/schools?kapsam=hepsi", ADMIN)
total_ok = st == 200 and allp["total"] == sum(ref.values())
bad = []
names = {SV.fold(x): x for x in meta["ils"]}
checked = 0
for (il, k), n in sorted(ref.items(), key=lambda x: -x[1]):
    if not il or k is None:
        continue
    st, r = api("GET", f"/api/v1/schools?kapsam=hepsi&il={urllib.request.quote(names.get(il, il))}&kademe={k}", ADMIN)
    checked += 1
    if st != 200 or r["total"] != n:
        bad.append({"il": il, "kademe": k, "sql": n, "api": r.get("total") if st == 200 else st})
check("1 il × kademe dağılımı", total_ok and not bad,
      f"toplam SQL {sum(ref.values())} / API {allp.get('total') if st == 200 else st}; {checked} hücre, {len(bad)} fark {bad[:5]}")

# 2. öğrenci sayısı temizliği
dolu = int(q(crm, f"SELECT COUNT(*) AS n FROM {S}.new_ziyaretyerleriBase WHERE statecode = 0 AND new_KurumTipi = 1 "
                  "AND TRY_CAST(new_renciSays AS int) IS NOT NULL")[0]["n"])
with store.connect() as c:
    kopya = c.execute(sa.text("SELECT COUNT(*) FROM semantic_school_profiles WHERE kaynak = 'crm' AND ogrenci IS NOT NULL "
                              "AND kurum_tipi = 'Okul'")).scalar()
samp = q(crm, f"SELECT TOP {a.samples} new_ziyaretyerleriId AS id, TRY_CAST(new_renciSays AS int) AS ogr, new_renciSays AS ham "
              f"FROM {S}.new_ziyaretyerleriBase WHERE statecode = 0 AND new_KurumTipi = 1 AND new_renciSays IS NOT NULL "
              "AND TRY_CAST(new_renciSays AS int) IS NULL")
samp += q(crm, f"SELECT TOP {a.samples} new_ziyaretyerleriId AS id, TRY_CAST(new_renciSays AS int) AS ogr, new_renciSays AS ham "
               f"FROM {S}.new_ziyaretyerleriBase WHERE statecode = 0 AND new_KurumTipi = 1 AND TRY_CAST(new_renciSays AS int) > 0 "
               "ORDER BY TRY_CAST(new_renciSays AS int) DESC")
diff = []
for r in samp:
    st, card = api("GET", f"/api/v1/schools/{str(r['id']).lower()}", ADMIN)
    got = card["school"]["students"] if st == 200 else st
    if got != r["ogr"]:
        diff.append({"id": str(r["id"]), "ham": r["ham"], "sql": r["ogr"], "api": got})
check("2 öğrenci sayısı temizliği", dolu == kopya and not diff,
      f"SQL dolu {dolu} / gece kopyası {kopya}; {len(samp)} örnek kart (çevrilemeyen dahil), fark {diff}")

# 3. geçmiş ziyaret sayısı
top = q(crm, f"SELECT TOP {a.samples} new_ZiyaretYeri AS id, COUNT(*) AS n FROM {S}.new_etkinlikBase WHERE statecode = 0 "
             "AND new_ZiyaretYeri IS NOT NULL AND new_ziyarettipi IN (1,2,3) AND statuscode = 100000002 "
             "GROUP BY new_ZiyaretYeri ORDER BY COUNT(*) DESC")
diff = []
for r in top:
    st, card = api("GET", f"/api/v1/schools/{str(r['id']).lower()}", ADMIN)
    got = card.get("crmDoneLinked") if st == 200 else st
    if got != int(r["n"]):
        diff.append({"id": str(r["id"]), "sql": int(r["n"]), "api": got})
# CRM'de okul bağlı tamamlanmış ziyaret yoksa karşılaştıracak veri yoktur: geçti/kaldı değil, doğrulanamadı
# (2026-09-28 ölçümü: new_etkinlikBase 57 bin kayıt, hiçbirinde new_ZiyaretYeri ya da new_ziyarettipi dolu değil).
check("3 okul kartındaki geçmiş ziyaret", (not diff) if top else None,
      f"{len(top)} okul, fark {diff}" if top else "CRM'de okula bağlı tamamlanmış ziyaret kaydı yok")

# 4. dönem siparişleri
term = meta["term"]
bas, bit = SV.term_range(term)
rows = q(crm, f"SELECT new_siparistipi AS tip, COUNT(*) AS n FROM {S}.new_siparisBase WHERE statecode = 0 AND new_siparistipi IN (10,11,13) "
              f"AND DATEADD(hour, 3, CreatedOn) >= '{bas}' AND DATEADD(hour, 3, CreatedOn) < DATEADD(day, 1, '{bit}') GROUP BY new_siparistipi")
sql = {int(r["tip"]): int(r["n"]) for r in rows}
st, rep = api("GET", f"/api/v1/schools/report/term?donem={urllib.request.quote(term)}", ADMIN)
got = {o["type"]: o["count"] for o in rep["orders"]["items"]} if st == 200 else {}
check("4 dönem raporu sipariş tipleri", st == 200 and all(got.get(t, 0) == sql.get(t, 0) for t in (10, 11, 13)),
      f"{term}: SQL {sql} / API {got}")

# 5. katalog: stok > 0 ve fiyat = geçerli genel liste
periods = q(logo, "SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1")
firm = f"{max(periods, key=lambda r: r['ENDDATE'])['FIRMNR']:03d}"
st, lst = api("GET", "/api/v1/schools?kapsam=hepsi&kademe=3&sirala=ogrenci", ADMIN)
sid = lst["items"][0]["id"] if st == 200 and lst["items"] else None
if sid:
    st, cat = api("POST", f"/api/v1/schools/{sid}/catalog", ADMIN, {"adet": "hepsi", "onizleme": True})
    codes = [b["code"] for b in cat.get("items", [])] if st in (200, 201) else []   # uç 201 döner; önizleme kayıt yazmaz
    if codes:
        inl = ", ".join("N'%s'" % c.replace("'", "''") for c in codes)
        stock = {r["CODE"]: float(r["bakiye"]) for r in q(logo, f"SELECT I.CODE, SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS bakiye "
                                                                 f"FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_ITEMS I ON I.LOGICALREF = S.STOCKREF "
                                                                 f"WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.IOCODE IN (1,2,3,4) AND I.CODE IN ({inl}) GROUP BY I.CODE")}
        price = {r["CODE"]: float(r["fiyat"]) for r in q(logo, f"SELECT I.CODE, MIN(P.PRICE) AS fiyat FROM dbo.LG_{firm}_PRCLIST P "
                                                                f"JOIN dbo.LG_{firm}_ITEMS I ON I.LOGICALREF = P.CARDREF WHERE P.PTYPE = 2 AND P.ACTIVE = 0 "
                                                                "AND P.CURRENCY IN (0,160) AND ISNULL(P.CLSPECODE, '') = '' AND P.BEGDATE <= CAST(GETDATE() AS date) "
                                                                f"AND P.ENDDATE >= CAST(GETDATE() AS date) AND I.CODE IN ({inl}) GROUP BY I.CODE")}
        bad = [b for b in cat["items"] if stock.get(b["code"], 0) <= 0
               or (b["priceBasis"] or "").startswith("Logo genel") and round(price.get(b["code"], -1), 2) != b["price"]]
        check("5 katalog stok ve fiyat", not bad, f"okul {sid}, {len(codes)} kitap (uygun toplam {cat['total']}), fark {bad[:5]}")
    else:
        check("5 katalog stok ve fiyat", None, f"okul {sid}: katalog boş ya da {st}")
else:
    check("5 katalog stok ve fiyat", None, "ilkokul bulunamadı")

# 6. geçmiş bayi eşleşmesi
pairs = {(str(r["new_ZiyaretYeri"]).lower(), str(r["new_AracMteriId"]).lower()) for r in q(
    crm, f"SELECT DISTINCT new_ZiyaretYeri, new_AracMteriId FROM {S}.new_etkinlikBase WHERE statecode = 0 AND new_ziyaretsekli = 1 "
         "AND new_AracMteriId IS NOT NULL AND new_ZiyaretYeri IS NOT NULL")}
with store.connect() as c:
    mine = {(r[0], (r[1] or "").lower()) for r in c.execute(sa.text(
        "SELECT ziyaret_yeri_id, crm_account_id FROM semantic_school_dealer_links WHERE kaynak = 'gecmis'"))}
check("6 geçmiş bayi eşleşmesi", pairs <= mine,
      f"SQL {len(pairs)} çift / portal {len(mine)}; eksik {len(pairs - mine)} {list(pairs - mine)[:3]}; "
      f"CRM'de artık olmayan (portalda kalan) {len(mine - pairs)}")

# 7. kapsam (başkasının raporu 403)
created = {"visits": []}
if a.write and REP:
    st, bad_body = api("POST", f"/api/v1/schools/{sid}/visits", ADMIN, {})
    st2, v = api("POST", f"/api/v1/schools/{sid}/visits", ADMIN,
                 {"durum": "yapildi", "gerceklesen": date.today().isoformat(), "ilgi": "orta", "not": "KABUL TESTİ — silinecek"})
    if st2 == 201:
        created["visits"].append(v["id"])
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(created, open(a.out, "w"))
        s_rep, _ = api("GET", f"/api/v1/schools/visits/{v['id']}", REP)
        s_adm, _ = api("GET", f"/api/v1/schools/visits/{v['id']}", ADMIN)
        check("7 kapsam: başkasının ziyaret raporu", s_rep == 403 and s_adm == 200 and st == 400,
              f"boş gövde {st}; temsilci {s_rep}, yetkili {s_adm}; silinecek kimlik {v['id']} → {a.out}")
    else:
        check("7 kapsam: başkasının ziyaret raporu", None, f"rapor yazılamadı {st2} {v}")
else:
    check("7 kapsam: başkasının ziyaret raporu", None, "--write ve REP_COOKIE verilmedi")

print(json.dumps({"sure_sn": round(time.time() - t0, 1), "sonuclar": results}, ensure_ascii=False, indent=1))
