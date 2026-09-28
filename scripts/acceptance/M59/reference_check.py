#!/usr/bin/env python3
"""M59 Bayi riski — gerçek DB kabulü (test sunucusunda koşar; Mac'te koşmaz).

Köprünün kullanıcıya verdiği sonucu (`/api/v1/dealers/*`, gerçek oturum) aynı Logo/CRM veritabanında **bağımsız** yazılmış
referans SQL ile karşılaştırır. Referans SQL'ler `dealers_sources.py` / `field_sales_sources.py`'den alınmaz; analiz
belgesinin §14 kabul listesinden ve sertifikalı `vadesi-gecmis-yaslandirma-fifo.md`'den elle yazılmıştır.

«Bugün» = Logo veri son günü (`/meta` → run.dataEnd; ayar `DEALERS_AGING_ASOF=veri-sonu`).

Kontroller (analiz §14 → «Kabul testleri»):
  1. Kapsam: CLCARD `CODE LIKE '120%' AND SPECODE2 IN (kural kanalları)` sayısı = listedeki cari sayısı (hareketsiz dahil).
  2. Yaşlandırma: sertifikalı FIFO SQL'i (GETDATE yerine veri son günü, kapsam kanallarıyla) → kova toplamları ve 90+ cari
     sayısı = Pano.
  3. Bakiye (10 cari): yıl başından CLFLINE borç − alacak = kart bakiyesi.
  4. İade oranı (5 cari): 12 ay penceresinde STLINE faturalı satır iade ÷ satış (LINENET, iki yıl firması) = kart.
  5. CRM limit (5 cari): AccountBase toplam risk limiti ve toplam risk = kart; boşsa kart «girilmemiş» (null).
  6. Karşılıksız çek (5 cari): 12 ayda CSTRANS STATUS 11 olayı (çek başına bir kez, cari = portföy giriş hareketi) = kart.
     Ayrıca 2026 toplamı yazdırılır (analiz ölçümü: 6 çek / 6.326.658 ₺).
  7. Risk onayı: new_siparisBase statuscode 100000004/100000016 (etkin) cari başına sayı = kart (5 cari).
  8. Tekrar üretilebilirlik: `--rerun` verilirse günlük tur aynı gün ikinci kez koşar; 20 carinin parmak izi aynı kalmalı
     (donmuş Logo kopyasında girdi değişmez). Verilmezse DOĞRULANAMADI.
  9. Kapsam yetkisi: DEALERS_BMT_COOKIE (bütün bayileri görme yetkisi olmayan temsilci) + DEALERS_OTHER_CODE (başkasının
     carisi) → 403. Verilmezse DOĞRULANAMADI.

Kullanım (test sunucusunda, köprünün ortam dosyası yüklü; `timasai` 15 dk'lık oturumuyla, bitince oturum silinir):
  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  DEALERS_COOKIE='timas_session=…' python3 scripts/acceptance/M59/reference_check.py \\
      --bridge http://127.0.0.1:8795 --out /tmp/claude-<oturum>/m59.json [--rerun]
  DEALERS_COOKIE yetkisi `ozellik:bayi.herkesinki` olan hesabın (yönetici de olur).

Sonuç: her kontrol BAŞARILI / BAŞARISIZ / DOĞRULANAMADI; kanıt JSON'u `--out`'a.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402

TOL = 0.01


def api(base: str, path: str, cookie: str, method: str = "GET") -> tuple[int, object]:
    req = urllib.request.Request(base + path, method=method, data=b"{}" if method == "POST" else None,
                                 headers={"cookie": cookie, "content-type": "application/json",
                                          "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def rows(conn, sql: str) -> list[dict]:
    _c, rs, trunc = conn.execute(sql, 5_000_000)
    assert not trunc, "referans sorgu kesildi"
    return [{str(k).lower(): v for k, v in r.items()} for r in rs]


def near(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOL


def q(s: str) -> str:
    return s.replace("'", "''")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8795")
    ap.add_argument("--out", required=True)
    ap.add_argument("--firm", default="411", help="bu yılın Logo firması (L_CAPIPERIOD; 411 = 2026)")
    ap.add_argument("--prev-firm", default="211", help="önceki yıl(lar)ın firması (211 = 2021–2025)")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--schema", default=os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo"))
    ap.add_argument("--rerun", action="store_true", help="8. kontrol: günlük turu aynı gün ikinci kez koştur")
    args = ap.parse_args()
    cookie = os.environ["DEALERS_COOKIE"]
    logo = connector_from_file(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    f, pf, y, p = args.firm, args.prev_firm, args.year, args.schema.rstrip(".") + "."
    results: list[dict] = []

    def record(no: int, name: str, status: str, detail: object) -> None:
        results.append({"no": no, "kontrol": name, "durum": status, "kanit": detail})
        print(f"[{status}] {no}. {name}")

    st, meta = api(args.bridge, "/api/v1/dealers/meta", cookie)
    st2, summ = api(args.bridge, "/api/v1/dealers/summary", cookie)
    if st != 200 or st2 != 200 or not meta["run"].get("gun"):
        print("köprü okunamadı ya da günlük tur koşmadı:", st, st2)
        return 2
    if not meta["me"]["canAll"]:
        print("DEALERS_COOKIE bütün bayileri görmüyor (ozellik:bayi.herkesinki)")
        return 2
    kanallar = meta["rule"]["kapsam"]["kanallar"]
    kin = ", ".join(f"N'{q(k)}'" for k in kanallar)
    end = date.fromisoformat(meta["run"]["dataEnd"])
    asof = date.fromisoformat(meta["run"]["agingAsof"] or meta["run"]["dataEnd"])
    first = date(end.year - 1 if end.month < 12 else end.year, (end.month % 12) + 1, 1)   # 12 ay penceresinin ilk günü

    # 1. Kapsam sayısı
    ref = rows(logo, f"SELECT COUNT(*) AS n FROM dbo.LG_{f}_CLCARD WHERE CODE LIKE '120%' AND UPPER(LTRIM(RTRIM(SPECODE2))) IN ({kin})")[0]["n"]
    s, lst = api(args.bridge, "/api/v1/dealers/list?durum=hepsi&size=1", cookie)
    got = lst["count"] if s == 200 else None
    record(1, "Kapsam: cari sayısı = kanal sayımı", "BAŞARILI" if got == int(ref) else "BAŞARISIZ",
           {"api": got, "referans": int(ref), "kanallar": kanallar,
            "not": "Fark varsa önce kanal yazımına bakın (köprü Türkçe harf duyarsız karşılaştırır; SQL UPPER)"})

    # 2. Yaşlandırma (sertifikalı FIFO SQL; GETDATE → veri son günü; kapsam kanalları)
    cert = rows(logo, f"""
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 0 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
  FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
  WHERE L.CANCELLED = 0 AND C.CODE LIKE '120%' AND L.DATE_ >= '{y}-01-01' AND UPPER(LTRIM(RTRIM(C.SPECODE2))) IN ({kin})
  GROUP BY L.CLIENTREF),
P AS (SELECT X.CARDREF, X.DATE_, X.TOTAL,
    SUM(X.TOTAL) OVER (PARTITION BY X.CARDREF ORDER BY X.DATE_ DESC, X.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) AS kumulatif
  FROM dbo.LG_{f}_01_PAYTRANS X WHERE X.CANCELLED = 0 AND X.SIGN = 0 AND X.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye > 0)),
A AS (SELECT P.CARDREF, P.DATE_,
    CASE WHEN B.bakiye >= P.kumulatif THEN P.TOTAL WHEN B.bakiye > P.kumulatif - P.TOTAL THEN B.bakiye - (P.kumulatif - P.TOTAL) ELSE 0 END AS acik
  FROM P JOIN B ON B.CLIENTREF = P.CARDREF)
SELECT kova, SUM(acik) AS tutar, COUNT(DISTINCT CARDREF) AS cari FROM (
  SELECT A.CARDREF, A.acik, CASE WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 0 THEN '0'
    WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 30 THEN 'k_1_30' WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 60 THEN 'k_31_60'
    WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 90 THEN 'k_61_90' ELSE 'k_90p' END AS kova
  FROM A WHERE A.acik > 0) x GROUP BY kova""")
    want = {r["kova"]: (float(r["tutar"] or 0), int(r["cari"])) for r in cert}
    ev, ok = {}, True
    for k in ("k_1_30", "k_31_60", "k_61_90", "k_90p"):
        w = want.get(k, (0.0, 0))
        same = abs(summ["kovalar"][k] - w[0]) <= max(TOL, 1e-9 * w[0] * 1000) and summ["kovaCari"][k] == w[1]
        ok &= same
        ev[k] = {"api": [summ["kovalar"][k], summ["kovaCari"][k]], "referans": list(w), "ayni": same}
    record(2, "Yaşlandırma kovaları ve cari sayısı = Pano", "BAŞARILI" if ok else "BAŞARISIZ", ev)

    # Örneklem: vadesi geçmişi olan 10 cari + rastgele
    s, top = api(args.bridge, "/api/v1/dealers/list?order=vadesi&size=10", cookie)
    s2, allr = api(args.bridge, "/api/v1/dealers/list?size=0", cookie)
    pool = allr["items"] if s2 == 200 else []
    random.seed(59)
    sample = (top["items"] if s == 200 else []) + random.sample(pool, min(10, len(pool)))
    seen, uniq = set(), []
    for d in sample:
        if d["code"] not in seen:
            seen.add(d["code"])
            uniq.append(d)
    cards = {}
    for d in uniq[:15]:
        sc, c = api(args.bridge, f"/api/v1/dealers/{urllib.parse.quote(d['code'])}", cookie)
        if sc == 200:
            cards[d["code"]] = c

    # 3. Bakiye (10 cari)
    ok, ev = True, []
    for code, c in list(cards.items())[:10]:
        r = rows(logo, f"""SELECT SUM(CASE WHEN L.SIGN = 0 THEN L.AMOUNT ELSE -L.AMOUNT END) AS b
FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
WHERE L.CANCELLED = 0 AND C.CODE = N'{q(code)}' AND L.DATE_ >= '{y}-01-01'""")[0]["b"]
        same = near(c["bakiye"], r)
        ok &= same
        ev.append({"code": code, "api": c["bakiye"], "referans": float(r or 0), "ayni": same})
    record(3, "Bakiye (10 cari)", "BAŞARILI" if ok and ev else "BAŞARISIZ" if ev else "DOĞRULANAMADI", ev)

    # 4. İade oranı (5 cari) — 12 ay penceresi, iki firma
    ok, ev = True, []
    for code, c in list(cards.items())[:5]:
        sat = iad = 0.0
        for firm, lo, hi in ((pf, first, date(y - 1, 12, 31)), (f, max(first, date(y, 1, 1)), end)):
            if lo > hi:
                continue
            r = rows(logo, f"""SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE 0 END) AS s,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.LINENET ELSE 0 END) AS i
FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE C.CODE = N'{q(code)}' AND S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{lo}' AND S.DATE_ < '{hi + timedelta(days=1)}'""")[0]
            sat += float(r["s"] or 0)
            iad += float(r["i"] or 0)
        want = round(iad / sat, 4) if sat > 0 else None
        got = c.get("iadeOrani")
        same = (want is None and got is None) or (want is not None and got is not None and abs(want - got) < 1e-4)
        ok &= same
        ev.append({"code": code, "api": got, "referans": want, "satis": sat, "iade": iad, "ayni": same})
    record(4, "İade oranı 12 ay (5 cari)", "BAŞARILI" if ok and ev else "BAŞARISIZ" if ev else "DOĞRULANAMADI", ev)

    # 5. CRM limit (5 cari)
    ok, ev = True, []
    crm_cards = [(k, c) for k, c in cards.items() if c.get("crmEsi")][:5]
    for code, c in crm_cards:
        r = rows(crm, f"""SELECT TOP 1 new_toplamrisklimiti AS lim, new_toplamrisk AS risk, new_acikhesaprisklimiti AS acik
FROM {p}AccountBase WHERE new_CariKodu = N'{q(code)}' AND StateCode = 0""")
        want = r[0] if r else {}
        lim = c["limit"].get("limit_toplam")
        same = (want.get("lim") is None and lim is None) or near(lim, want.get("lim"))
        same &= (want.get("risk") is None and c["limit"].get("risk_toplam") is None) or near(c["limit"].get("risk_toplam"), want.get("risk"))
        ok &= same
        ev.append({"code": code, "api": {"limit": lim, "risk": c["limit"].get("risk_toplam")},
                   "referans": {k: (float(v) if v is not None else None) for k, v in want.items()}, "ayni": same})
    record(5, "CRM limit ve risk (5 cari)", "BAŞARILI" if ok and ev else "BAŞARISIZ" if ev else "DOĞRULANAMADI",
           {"satirlar": ev, "not": "Eşleşme CRM new_CariKodu ile; köprü önce cari kodu, yoksa new_logicalref ile eşler"})

    # 6. Karşılıksız çek (5 cari) + 2026 toplamı
    ok, ev = True, []
    since = end - timedelta(days=365)
    for code, c in list(cards.items())[:5]:
        n = 0
        for firm in (f, pf):
            r = rows(logo, f"""SELECT COUNT(*) AS n FROM dbo.LG_{firm}_01_CSCARD K
WHERE K.CANCELLED = 0 AND K.DOC IN (1, 2)
  AND EXISTS (SELECT 1 FROM dbo.LG_{firm}_01_CSTRANS T WHERE T.CSREF = K.LOGICALREF AND T.STATUS = 11 AND T.DEVIR = 0
              AND T.CANCELLED = 0 AND T.DATE_ >= '{since}')
  AND K.LOGICALREF IN (SELECT G.CSREF FROM dbo.LG_{firm}_01_CSTRANS G JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = G.CARDREF
                       WHERE C.CODE = N'{q(code)}' AND G.STATUS = 1 AND G.CANCELLED = 0)""")
            n += int(r[0]["n"])
        same = int(c.get("karsiliksiz") or 0) == n
        ok &= same
        ev.append({"code": code, "api": c.get("karsiliksiz"), "referans": n, "ayni": same})
    tot = rows(logo, f"""SELECT COUNT(DISTINCT T.CSREF) AS n, SUM(K.AMOUNT) AS tutar FROM dbo.LG_{f}_01_CSTRANS T
JOIN dbo.LG_{f}_01_CSCARD K ON K.LOGICALREF = T.CSREF WHERE T.STATUS = 11 AND T.DEVIR = 0 AND T.CANCELLED = 0 AND T.DATE_ >= '{y}-01-01'""")[0]
    record(6, "Karşılıksız çek/senet (5 cari)", "BAŞARILI" if ok and ev else "BAŞARISIZ" if ev else "DOĞRULANAMADI",
           {"satirlar": ev, "yilToplami": {"adet": int(tot["n"] or 0), "tutar": float(tot["tutar"] or 0)},
            "not": "Yıl toplamı bilgi amaçlı (2026-09-20 ölçümü 6 / 6.326.658 ₺)"})

    # 7. Riske takılı sipariş (5 cari)
    ok, ev = True, []
    for code, c in crm_cards:
        r = rows(crm, f"""SELECT COUNT(*) AS n FROM {p}new_siparisBase s JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid
WHERE a.new_CariKodu = N'{q(code)}' AND a.StateCode = 0 AND s.statecode = 0 AND CAST(s.statuscode AS int) IN (100000004, 100000016)""")[0]["n"]
        same = int(c.get("siparisRiskte") or 0) == int(r)
        ok &= same
        ev.append({"code": code, "api": c.get("siparisRiskte"), "referans": int(r), "ayni": same,
                   "not": "API günlük tur anının sayısıdır; tur sonrası CRM'de değişen sipariş fark yaratır"})
    record(7, "Riske takılı sipariş (5 cari)", "BAŞARILI" if ok and ev else "BAŞARISIZ" if ev else "DOĞRULANAMADI", ev)

    # 8. Tekrar üretilebilirlik
    if args.rerun:
        before = {k: c["fingerprint"] for k, c in list(cards.items())}
        sr, out = api(args.bridge, "/api/v1/dealers/run-due?tur=gunluk", cookie, "POST")
        after = {}
        for code in before:
            sc, c = api(args.bridge, f"/api/v1/dealers/{urllib.parse.quote(code)}", cookie)
            after[code] = c["fingerprint"] if sc == 200 else None
        same = sr == 200 and before == after
        record(8, "Aynı gün ikinci tur: parmak izleri aynı", "BAŞARILI" if same else "BAŞARISIZ",
               {"tur": out if sr != 200 else {k: out.get(k) for k in ("gun", "kural", "scope", "ms")},
                "farkli": [k for k in before if before[k] != after.get(k)]})
    else:
        record(8, "Aynı gün ikinci tur: parmak izleri aynı", "DOĞRULANAMADI", {"not": "--rerun verilmedi"})

    # 9. Kapsam yetkisi
    bmt_cookie, other = os.environ.get("DEALERS_BMT_COOKIE"), os.environ.get("DEALERS_OTHER_CODE")
    if bmt_cookie and other:
        sc, _ = api(args.bridge, f"/api/v1/dealers/{urllib.parse.quote(other)}", bmt_cookie)
        record(9, "BMT başkasının carisini göremez (403)", "BAŞARILI" if sc == 403 else "BAŞARISIZ", {"durum": sc})
    else:
        record(9, "BMT başkasının carisini göremez (403)", "DOĞRULANAMADI", {"not": "DEALERS_BMT_COOKIE / DEALERS_OTHER_CODE yok"})

    json.dump({"meta": {"gun": meta["run"]["gun"], "dataEnd": meta["run"]["dataEnd"], "kural": meta["rule"]["surum"]},
               "sonuclar": results}, open(args.out, "w"), ensure_ascii=False, indent=2, default=str)
    bad = sum(1 for r in results if r["durum"] == "BAŞARISIZ")
    print(f"özet: {len(results)} kontrol, {bad} başarısız, {sum(1 for r in results if r['durum'] == 'DOĞRULANAMADI')} doğrulanamadı")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
