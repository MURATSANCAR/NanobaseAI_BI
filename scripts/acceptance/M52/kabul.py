#!/usr/bin/env python3
"""M52 Tedarik ve baskı — gerçek DB kabulü (test sunucusunda koşar; Mac'te koşmaz).

Köprünün kullanıcıya verdiği sonucu (`/api/v1/supply/*`, gerçek oturum) aynı Logo/CRM veritabanında **bağımsız** yazılmış
referans SQL ile ya da M12'nin kendi ucuyla karşılaştırır. Referans SQL'ler `supply_sql/` dosyalarından alınmaz; analiz
belgesinin §14 kabul listesinden ve katalogdaki sertifikalı SQL'lerden elle yazılmıştır.

Kontroller (analiz §14 «Kabul testleri»):
  1. Ay × matbaa iş sayısı ve adet = M12 `/cards` (bütün sayfalar) aynı süzgeçle (baskıdan çıkmamış, plan baskı ayı) — fark 0.
     Bilgi: doğrudan CRM (`statuscode` ile) matbaa × baskı ayı sayımı yazdırılır (M12 aşaması Logo'yu da okuduğundan birebir
     beklenmez).
  2. Matbaa/kağıtçı cari listesi = `LG_<firma>_CLCARD` 320 carilerinde özel kod ayardaki değerlerle (Türkçe harf/büyük-küçük
     farkı gözetmeden) — birebir. Boşsa özel kodun yazımı ölçülür, kural uydurulmaz.
  3. Tedarikçi bakiyesi: 10 cari için ekran = CLFLINE alacak − borç (yıl başından) — kuruş.
  4. FIFO vadesi geçmiş = katalog «satici-borcu-vadesi-gecmis-fifo» SQL'i aynı carilerle — kuruş.
  5. Üretimden giriş (ay bazında, bu yıl) = Kural 20 (STLINE TRCODE 13, IOCODE 1) + gerçek fiş (PRODSTAT 0) — fark 0.
     Bilgi: PRODSTAT süzgeçsiz Kural 20 toplamı da yazdırılır (planlanan fişler dahil olursa ne kadar şiştiği).
  6. Kağıt ihtiyacı: ekrandaki ay × kağıt cinsi kg = CRM kart alanlarının (parça başına brüt ya da net kg) toplamı, kart
     kümesi ekrandaki yük tablosundan — fark 0.
  7. Alış toplamı (bu yıl, matbaa ve kağıtçı carileri) = katalog «satinalma» (Σ NETTOTAL, TRCODE 1/4) aynı cari süzgeciyle.
  8. Yetki: «tedarikçi borç» yetkisi olmayan oturumla /payments 403 ve /suppliers'ta bakiye alanı yok (NOBORC_COOKIE verilirse).
  9. Yazma: geçersiz gövdeler 400/403/404; `--yaz` ile tek şartname taslağı (kaydın kimliği `--ids` dosyasına; sonra
     cleanup.py siler).

Kullanım (test sunucusunda, köprünün ortam dosyası yüklü; `timasai` 15 dk'lık oturumu, bitince oturum silinir):
  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  SUPPLY_COOKIE='timas_session=…' python3 scripts/acceptance/M52/kabul.py --out /tmp/claude-<oturum>/m52.json \\
      --ids /tmp/claude-<oturum>/m52-ids.json [--yaz]
  SUPPLY_COOKIE yönetici ya da `tedarik.borc` + `tedarik.maliyet` yetkili oturum olmalı.

Sonuç: her kontrol BAŞARILI / BAŞARISIZ / DOĞRULANAMADI; kanıt JSON'u `--out`'a.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402

TOL = 0.01
PARTS = ["kapak", "icsayfabir", "icsayfaiki", "somiz", "harita", "afis", "yankagit", "ayrac"]
_TR = str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")


def fold(s) -> str:
    return " ".join(str(s or "").translate(_TR).lower().split())


def api(base: str, path: str, cookie: str, method: str = "GET", body=None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"cookie": cookie, "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def rows(conn, sql: str) -> list[dict]:
    _c, rs, trunc = conn.execute(sql, 5_000_000)
    assert not trunc, "referans sorgu kesildi"
    return [{str(k).lower(): v for k, v in r.items()} for r in rs]


def near(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOL


def mkey(v) -> str | None:
    if v is None:
        return None
    s = str(v)[:10]
    return s[:7] if len(s) >= 7 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8795")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--firm", default="411", help="bu yılın Logo firması (L_CAPIPERIOD; 411 = 2026)")
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--schema", default=os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo"))
    ap.add_argument("--yaz", action="store_true", help="tek şartname taslağı yaz (sonra cleanup.py)")
    args = ap.parse_args()
    cookie = os.environ["SUPPLY_COOKIE"]
    logo = connector_from_file(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    f, y, p = args.firm, args.year, args.schema.rstrip(".") + "."
    results: list[dict] = []
    ids: dict[str, list[str]] = {"suggestions": []}

    def record(no: int, name: str, status: str, detail: object) -> None:
        results.append({"no": no, "kontrol": name, "durum": status, "kanit": detail})
        print(f"[{status}] {no}. {name}")

    st, meta = api(args.bridge, "/api/v1/supply/meta", cookie)
    if st != 200:
        print("köprü okunamadı:", st, meta)
        return 2
    s = meta["settings"]

    # 1. Yük = M12 kartları
    st, load = api(args.bridge, "/api/v1/supply/load?aylar=12", cookie)
    cards, page = [], 0
    while True:
        s2, part = api(args.bridge, f"/api/v1/editorial/production/cards?durum=acik&page={page}", cookie)
        if s2 != 200:
            break
        cards += part["items"]
        if (page + 1) * part["pageSize"] >= part["total"]:
            break
        page += 1
    if st != 200 or s2 != 200:
        record(1, "Ay × matbaa yükü = M12 kartları", "DOĞRULANAMADI", {"load": st, "cards": s2})
    else:
        months = {m["key"] for m in load["aylar"] if m["key"] not in ("gecikmis", "tarihsiz")}
        want: dict[tuple, list] = {}
        for c in cards:
            if c["stage"] not in ("hazirlik", "matbaa-secildi", "matbaada"):
                continue
            m = mkey((c.get("plan") or {}).get("baski"))
            if m in months:
                k = (c.get("printer") or "Matbaa belirlenmedi", m)
                x = want.setdefault(k, [0, 0.0])
                x[0] += 1
                x[1] += float(c.get("qty") or 0)
        got = {(r["matbaa"], k): [v["jobs"], v["adet"]] for r in load["satirlar"] for k, v in r["hucreler"].items()
               if k in months and v["jobs"]}
        diff = {f"{k[0]} {k[1]}": {"ekran": got.get(k), "m12": want.get(k)} for k in set(got) | set(want)
                if not (got.get(k) and want.get(k) and got[k][0] == want[k][0] and near(got[k][1], want[k][1]))}
        crm_info = rows(crm, f"""SELECT CAST(r.new_Matbaa AS int) AS matbaa, r.new_baskiayi AS ay, COUNT(*) AS kart,
  SUM(r.new_kesinlesenbaskiadeti) AS adet FROM {p}new_UretimBase r WHERE r.statecode = 0
  AND CAST(r.statuscode AS int) NOT IN (100000006, 100000007) AND r.CreatedOn >= '{y - 2}-01-01'
GROUP BY CAST(r.new_Matbaa AS int), r.new_baskiayi""")
        record(1, "Ay × matbaa yükü = M12 kartları (fark 0)", "BAŞARILI" if not diff else "BAŞARISIZ",
               {"hucre": len(got), "fark": diff, "bilgi_crm_dogrudan": crm_info[:200]})

    # 2. Cari listesi
    st, sup = api(args.bridge, "/api/v1/supply/suppliers", cookie)
    if st != 200:
        record(2, "Matbaa/kağıtçı cari listesi", "DOĞRULANAMADI", sup)
        sup = None
    else:
        pc = {fold(x) for x in s["printerSpecodes"]}
        kc = {fold(x) for x in s["paperSpecodes"]}
        ref = rows(logo, f"SELECT CODE AS kod, SPECODE AS oz FROM dbo.LG_{f}_CLCARD WHERE CODE LIKE '{s['supplierPrefix']}%'")
        want_p = {r["kod"] for r in ref if fold(r["oz"]) in pc}
        want_k = {r["kod"] for r in ref if fold(r["oz"]) in kc}
        got_p = {x["kod"] for x in sup["items"] if x["tur"] == "matbaa" and x["turKaynak"] == "ozel-kod"}
        got_k = {x["kod"] for x in sup["items"] if x["tur"] == "kagit"}
        ok = want_p == got_p and want_k == got_k
        status = "BAŞARILI" if ok else "BAŞARISIZ"
        if ok and not want_p and not want_k:
            status = "DOĞRULANAMADI"   # özel kod Logo'da bu yazımla yok: dağılım yazdırılır, ayar düzeltilir
        record(2, "Matbaa/kağıtçı cari listesi = CLCARD özel kodu", status,
               {"matbaa": sorted(want_p ^ got_p), "kagit": sorted(want_k ^ got_k), "sayi": [len(want_p), len(want_k)],
                "ozel_kod_dagilimi": sup.get("ozelKodlar")})

    # 3–4. Bakiye ve FIFO vadesi geçmiş
    if not sup or "bakiye" not in (sup["items"][0] if sup and sup["items"] else {}):
        record(3, "Tedarikçi bakiyesi", "DOĞRULANAMADI", "borç alanı gelmedi (yetki ya da Logo)")
        record(4, "FIFO vadesi geçmiş = katalog", "DOĞRULANAMADI", "borç alanı gelmedi")
    else:
        sample = sorted((x for x in sup["items"] if x["tur"] in ("matbaa", "kagit")), key=lambda x: -abs(x["bakiye"]))[:10]
        codes = ", ".join("'" + x["kod"].replace("'", "''") + "'" for x in sample) or "''"
        bal = {r["code"]: float(r["b"] or 0) for r in rows(logo, f"""SELECT c.CODE AS code,
  SUM(CASE WHEN f.SIGN = 1 THEN f.AMOUNT ELSE -f.AMOUNT END) AS b
FROM dbo.LG_{f}_01_CLFLINE f JOIN dbo.LG_{f}_CLCARD c ON c.LOGICALREF = f.CLIENTREF
WHERE f.CANCELLED = 0 AND f.DATE_ >= '{y}-01-01' AND c.CODE IN ({codes}) GROUP BY c.CODE""")}
        d3 = {x["kod"]: [x["bakiye"], bal.get(x["kod"], 0.0)] for x in sample if not near(x["bakiye"], bal.get(x["kod"], 0.0))}
        record(3, "Tedarikçi bakiyesi (10 cari) = CLFLINE", "BAŞARILI" if sample and not d3 else ("BAŞARISIZ" if d3 else "DOĞRULANAMADI"),
               {"cari": len(sample), "fark": d3})
        fifo = {r["code"]: float(r["vg"] or 0) for r in rows(logo, f"""
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 1 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
    FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
    WHERE L.CANCELLED = 0 AND C.CODE LIKE '320%' AND L.DATE_ >= DATEFROMPARTS(YEAR(GETDATE()), 1, 1)
    GROUP BY L.CLIENTREF),
  N AS (SELECT P.CARDREF, SUM(P.TOTAL) AS gelmemis FROM dbo.LG_{f}_01_PAYTRANS P
    WHERE P.CANCELLED = 0 AND P.SIGN = 1 AND P.DATE_ >= CAST(GETDATE() AS date) GROUP BY P.CARDREF)
SELECT C.CODE AS code, CASE WHEN B.bakiye - ISNULL(N.gelmemis, 0) > 0 THEN B.bakiye - ISNULL(N.gelmemis, 0) ELSE 0 END AS vg
FROM B JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = B.CLIENTREF LEFT JOIN N ON N.CARDREF = B.CLIENTREF
WHERE B.bakiye > 0 AND C.CODE IN ({codes})""")}
        d4 = {x["kod"]: [x["vadesiGecmis"], fifo.get(x["kod"], 0.0)] for x in sample if not near(x["vadesiGecmis"], fifo.get(x["kod"], 0.0))}
        record(4, "FIFO vadesi geçmiş = katalog SQL'i", "BAŞARILI" if sample and not d4 else ("BAŞARISIZ" if d4 else "DOĞRULANAMADI"),
               {"fark": d4})

    # 5. Üretimden giriş
    st, inc = api(args.bridge, "/api/v1/supply/incoming?aylar=1", cookie)
    if st != 200:
        record(5, "Üretimden giriş (ay)", "DOĞRULANAMADI", inc)
    else:
        real = {f"{int(r['yil']):04d}-{int(r['ay']):02d}": float(r["adet"] or 0) for r in rows(logo, f"""
SELECT YEAR(l.DATE_) AS yil, MONTH(l.DATE_) AS ay, SUM(l.AMOUNT) AS adet
FROM dbo.LG_{f}_01_STLINE l JOIN dbo.LG_{f}_01_STFICHE fi ON fi.LOGICALREF = l.STFICHEREF
WHERE l.TRCODE = 13 AND l.IOCODE = 1 AND l.LINETYPE = 0 AND l.CANCELLED = 0 AND fi.CANCELLED = 0 AND fi.PRODSTAT = 0
  AND l.DATE_ >= '{y}-01-01' GROUP BY YEAR(l.DATE_), MONTH(l.DATE_)""")}
        bare = {f"{int(r['yil']):04d}-{int(r['ay']):02d}": float(r["adet"] or 0) for r in rows(logo, f"""
SELECT YEAR(DATE_) AS yil, MONTH(DATE_) AS ay, SUM(AMOUNT) AS adet FROM dbo.LG_{f}_01_STLINE
WHERE TRCODE = 13 AND IOCODE = 1 AND LINETYPE = 0 AND CANCELLED = 0 AND DATE_ >= '{y}-01-01' GROUP BY YEAR(DATE_), MONTH(DATE_)""")}
        got = {m["ay"]: m["adet"] for m in inc["gecmis"] if m["ay"].startswith(str(y))}
        d5 = {k: [got.get(k, 0), real.get(k, 0)] for k in set(got) | set(real) if not near(got.get(k, 0), real.get(k, 0))}
        record(5, "Üretimden giriş = Kural 20 + gerçek fiş", "BAŞARILI" if not d5 else "BAŞARISIZ",
               {"fark": d5, "bilgi_prodstat_suzgecsiz": bare})

    # 6. Kağıt ihtiyacı
    st, paper = api(args.bridge, "/api/v1/supply/paper?aylar=12", cookie)
    if st != 200 or not load or not isinstance(load, dict):
        record(6, "Kağıt ihtiyacı = CRM kart alanları", "DOĞRULANAMADI", paper)
    else:
        measure = paper["olcu"]
        month_of = {}
        for r in load["satirlar"]:
            for k, cell in r["hucreler"].items():
                for c in cell["cards"]:
                    month_of[c["id"]] = k
        ids_sql = ", ".join(f"'{i}'" for i in month_of) or "NULL"
        cols = ", ".join(f"r.new_{x}{'brutkagitihtiyacikg' if measure == 'brut' else 'netkagitihtiyacikg'} AS {x}_kg, "
                         f"r.new_{x}kagitcinsiid AS {x}_cins" for x in PARTS)
        ref6: dict[tuple, float] = {}
        for r in rows(crm, f"SELECT r.new_UretimId AS id, {cols} FROM {p}new_UretimBase r WHERE r.new_UretimId IN ({ids_sql})"):
            m = month_of.get(str(r["id"]).lower())
            for x in PARTS:
                kg = float(r.get(f"{x}_kg") or 0)
                if kg:
                    k = (m, str(r.get(f"{x}_cins") or "-").lower())
                    ref6[k] = ref6.get(k, 0.0) + kg
        got6 = {(r["ay"], (r["cins"] or "-").lower()): r["kg"] for r in paper["satirlar"]}
        d6 = {f"{k[0]} {k[1]}": [got6.get(k, 0), ref6.get(k, 0)] for k in set(got6) | set(ref6)
              if k[0] in {m["key"] for m in paper["aylar"]} and not near(got6.get(k, 0), ref6.get(k, 0))}
        record(6, "Kağıt ihtiyacı (ay × cins) = CRM kart alanları", "BAŞARILI" if not d6 else "BAŞARISIZ",
               {"olcu": measure, "hucre": len(got6), "fark": d6})

    # 7. Alış toplamı
    if not sup or "alisBuYil" not in (sup["items"][0] if sup["items"] else {}):
        record(7, "Alış toplamı = satinalma", "DOĞRULANAMADI", "alış alanı gelmedi")
    else:
        focus = [x for x in sup["items"] if x["tur"] in ("matbaa", "kagit")]
        codes = ", ".join("'" + x["kod"].replace("'", "''") + "'" for x in focus) or "''"
        buy = {r["code"]: float(r["t"] or 0) for r in rows(logo, f"""SELECT C.CODE AS code, SUM(i.NETTOTAL) AS t
FROM dbo.LG_{f}_01_INVOICE i JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = i.CLIENTREF
WHERE i.CANCELLED = 0 AND i.TRCODE IN (1, 4) AND i.DATE_ >= '{y}-01-01' AND C.CODE IN ({codes}) GROUP BY C.CODE""")}
        d7 = {x["kod"]: [x["alisBuYil"], buy.get(x["kod"], 0.0)] for x in focus if not near(x["alisBuYil"], buy.get(x["kod"], 0.0))}
        record(7, "Alış toplamı (bu yıl) = satinalma ölçüsü", "BAŞARILI" if focus and not d7 else ("BAŞARISIZ" if d7 else "DOĞRULANAMADI"),
               {"cari": len(focus), "toplam_ekran": round(sum(x["alisBuYil"] for x in focus), 2),
                "toplam_referans": round(sum(buy.values()), 2), "fark": d7})

    # 8. Yetki
    nob = os.environ.get("NOBORC_COOKIE")
    if not nob:
        record(8, "Borç yetkisi olmadan tutar yok", "DOĞRULANAMADI", "NOBORC_COOKIE verilmedi")
    else:
        a, _ = api(args.bridge, "/api/v1/supply/payments", nob)
        b, sp = api(args.bridge, "/api/v1/supply/suppliers", nob)
        leak = b == 200 and any("bakiye" in x for x in sp["items"])
        record(8, "Borç yetkisi olmadan tutar yok", "BAŞARILI" if a == 403 and not leak else "BAŞARISIZ", {"payments": a, "sizinti": leak})

    # 9. Yazma uçları
    checks = {
        "capacity_bos": api(args.bridge, "/api/v1/supply/capacity", cookie, "PUT", {})[0],
        "karar_yok": api(args.bridge, "/api/v1/supply/suggestions/" + "0" * 32 + "/decision", cookie, "POST", {"karar": "kabul"})[0],
        "taslak_tur": api(args.bridge, "/api/v1/supply/drafts", cookie, "POST", {"tur": "x"})[0],
        "bag_gecersiz": api(args.bridge, "/api/v1/supply/invoice-links", cookie, "POST", {"firma": "x"})[0],
    }
    ok9 = checks["capacity_bos"] == 400 and checks["karar_yok"] == 404 and checks["taslak_tur"] == 400 and checks["bag_gecersiz"] in (400, 403)
    if args.yaz and cards:
        st, dr = api(args.bridge, "/api/v1/supply/drafts", cookie, "POST", {"tur": "sartname", "kartId": cards[0]["id"]})
        checks["taslak"] = st
        if st == 201:
            ids["suggestions"].append(dr["id"])
            ok9 = ok9 and "TASLAK" in (dr.get("metin") or "")
        else:
            ok9 = False
    record(9, "Yazma uçları (geçersiz gövde, taslak)", "BAŞARILI" if ok9 else "BAŞARISIZ", checks)

    with open(args.ids, "w") as fh:
        json.dump(ids, fh)
    with open(args.out, "w") as fh:
        json.dump({"tarih": date.today().isoformat(), "sonuclar": results}, fh, ensure_ascii=False, indent=2, default=str)
    bad = [r for r in results if r["durum"] == "BAŞARISIZ"]
    print(f"toplam {len(results)} · başarısız {len(bad)} · doğrulanamadı {sum(r['durum'] == 'DOĞRULANAMADI' for r in results)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
