#!/usr/bin/env python3
"""M30 Saha satış ve tahsilat — gerçek DB kabulü (test sunucusunda koşar; Mac'te koşmaz).

Köprünün kullanıcıya verdiği sonucu (`/api/v1/field/*`, gerçek oturum) aynı Logo/CRM veritabanında **bağımsız** yazılmış
referans SQL ile karşılaştırır. Referans SQL'ler `field_sales_sources.py`'den alınmaz; analiz belgesinin §14 kabul
listesinden ve sertifikalı `vadesi-gecmis-yaslandirma-fifo.md`'den elle yazılmıştır.

Kontroller (analiz §14 → «Kabul testleri»):
  1. FIFO kovaları: 5 carinin 1–30/31–60/61–90/90+ tutarı = sertifikalı SQL'in `C.LOGICALREF = @ref` süzgeçli sonucu (kuruş).
  2. YTD net ciro: brifingdeki tutar = STLINE faturalı satır (satış − iade) doğrudan toplamı (5 cari).
  3. Portföy: temsilcinin cari sayısı ≥ CRM'de sahibi o olan etkin ve Logo kodu eşleşen cari sayısı (BMT İl carileri ayrıca
     il tablosundan; fark yazdırılır).
  4. CRM tahsilat: onay bekleyen sayı ve tutar = new_tahsilatBase doğrudan (OwnerId = temsilci).
  5. Karşılıksız olay: brifingdeki 12 ay sayısı = CSTRANS STATUS 11 olay sorgusu (5 cari; cari = portföy giriş hareketi).
  6. Risk doluluğu = new_toplamrisk / new_toplamrisklimiti (5 cari).
  7. Hedef dağıtımı: portföydeki cari yıllık hedeflerinin toplamı = yürürlükteki bütçe planı toplamı (M46 kaynaklıysa).
  8. Kapsam: temsilci hesabıyla başka temsilcinin carisine brifing → 403.

Kullanım (test sunucusunda, köprünün ortam dosyası yüklü; `timasai` 15 dk'lık oturumuyla, bitince oturum silinir):
  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  FIELD_COOKIE='timas_session=…' FIELD_REP=ayseb FIELD_OTHER_CODE=120.xx.yyy \\
    python3 scripts/acceptance/M30/reference_check.py --bridge http://127.0.0.1:8795 --out /tmp/claude-<oturum>/m30.json
  FIELD_COOKIE yetkisi `ozellik:saha.herkesinki` olan hesabın; FIELD_REP kontrol edilecek temsilcinin AD hesabı.
  Kapsam denetimi (8) için FIELD_REP_COOKIE (temsilcinin kendi oturumu) verilirse koşar, yoksa «DOĞRULANAMADI».

Sonuç: her kontrol BAŞARILI / BAŞARISIZ / DOĞRULANAMADI; kanıt JSON'u `--out`'a.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402

TOL = 0.01


def api(base: str, path: str, cookie: str) -> tuple[int, object]:
    req = urllib.request.Request(base + path, headers={"cookie": cookie, "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def rows(conn, sql: str) -> list[dict]:
    _c, rs, trunc = conn.execute(sql, 5_000_000)
    assert not trunc, "referans sorgu kesildi"
    return [{str(k).lower(): v for k, v in r.items()} for r in rs]


def near(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8795")
    ap.add_argument("--out", required=True)
    ap.add_argument("--firm", default="411", help="bu yılın Logo firması (L_CAPIPERIOD'dan; 411 = 2026)")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--schema", default=os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo"))
    args = ap.parse_args()
    cookie = os.environ["FIELD_COOKIE"]
    rep = os.environ["FIELD_REP"].lower()
    logo = connector_from_file(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    f, y, p = args.firm, args.year, args.schema.rstrip(".") + "."
    results: list[dict] = []

    def record(no: int, name: str, status: str, detail: object) -> None:
        results.append({"no": no, "kontrol": name, "durum": status, "kanit": detail})
        print(f"[{status}] {no}. {name}")

    st, meta = api(args.bridge, "/api/v1/field/meta", cookie)
    st2, port = api(args.bridge, f"/api/v1/field/portfolio?temsilci={rep}", cookie)
    if st != 200 or st2 != 200:
        print("köprü okunamadı:", st, st2, meta if st != 200 else port)
        return 2
    items = port["items"]
    sample = [c for c in items if (c.get("vadesiGecmis") or 0) > 0][:5] or items[:5]
    briefs = {}
    for c in sample:
        s, b = api(args.bridge, f"/api/v1/field/customers/{urllib.parse.quote(c['code'])}/brief", cookie)
        briefs[c["code"]] = b if s == 200 else None
    asof = date.fromisoformat(meta["run"]["agingAsof"] or meta["run"]["asof"])
    data_end = date.fromisoformat(meta["run"]["dataEnd"])

    # 1. FIFO — sertifikalı SQL (vadesi-gecmis-yaslandirma-fifo.md), adlar firmaya çevrildi, tek cari süzgeci eklendi.
    ok, ev = True, []
    for c in sample:
        ref = rows(logo, f"SELECT LOGICALREF AS r FROM dbo.LG_{f}_CLCARD WHERE CODE = '{c['code']}'")[0]["r"]
        cert = rows(logo, f"""
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 0 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
  FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
  WHERE L.CANCELLED = 0 AND C.CODE LIKE '120%' AND L.DATE_ >= '{y}-01-01' AND C.LOGICALREF = {int(ref)}
  GROUP BY L.CLIENTREF),
P AS (SELECT X.CARDREF, X.DATE_, X.TOTAL,
    SUM(X.TOTAL) OVER (PARTITION BY X.CARDREF ORDER BY X.DATE_ DESC, X.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) AS kumulatif
  FROM dbo.LG_{f}_01_PAYTRANS X WHERE X.CANCELLED = 0 AND X.SIGN = 0 AND X.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye > 0)),
A AS (SELECT P.CARDREF, P.DATE_,
    CASE WHEN B.bakiye >= P.kumulatif THEN P.TOTAL WHEN B.bakiye > P.kumulatif - P.TOTAL THEN B.bakiye - (P.kumulatif - P.TOTAL) ELSE 0 END AS acik
  FROM P JOIN B ON B.CLIENTREF = P.CARDREF)
SELECT kova, SUM(acik) AS tutar FROM (
  SELECT A.acik, CASE WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 0 THEN '0'
    WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 30 THEN 'k_1_30' WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 60 THEN 'k_31_60'
    WHEN DATEDIFF(day, A.DATE_, '{asof}') <= 90 THEN 'k_61_90' ELSE 'k_90p' END AS kova
  FROM A WHERE A.acik > 0) x GROUP BY kova""")
        want = {r["kova"]: float(r["tutar"] or 0) for r in cert}
        got = c["kovalar"]
        same = all(near(got.get(k), want.get(k, 0)) for k in ("k_1_30", "k_31_60", "k_61_90", "k_90p"))
        ok &= same
        ev.append({"code": c["code"], "api": got, "referans": want, "ayni": same})
    record(1, "FIFO kovaları (5 cari)", "BAŞARILI" if ok and sample else "BAŞARISIZ" if sample else "DOĞRULANAMADI", ev)

    # 2. YTD net ciro
    ok, ev = True, []
    for c in sample:
        r = rows(logo, f"""SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net
FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE C.CODE = '{c['code']}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{y}-01-01' AND S.DATE_ < '{data_end + timedelta(days=1)}'""")[0]["net"]
        b = briefs.get(c["code"]) or {}
        got = (b.get("signals") or {}).get("ytd_net_ciro")
        same = near(got, r)
        ok &= same
        ev.append({"code": c["code"], "api": got, "referans": float(r or 0), "ayni": same})
    record(2, "YTD net ciro (5 cari)", "BAŞARILI" if ok and sample else "BAŞARISIZ" if sample else "DOĞRULANAMADI", ev)

    # 3. Portföy sayısı (sahip = temsilci; «BMT İl» carileri il tablosundan ayrıca)
    own = rows(crm, f"""SELECT COUNT(*) AS n FROM {p}AccountBase a JOIN {p}SystemUserBase u ON u.SystemUserId = a.OwnerId
WHERE LOWER(u.DomainName) LIKE '%\\{rep}' AND a.StateCode = 0 AND ISNULL(a.new_BMTilveyaCari, 1) = 1""")[0]["n"]
    il = rows(crm, f"""SELECT COUNT(*) AS n FROM {p}AccountBase a JOIN {p}new_illerBase i ON i.new_illerId = a.new_cariyeaitil
JOIN {p}SystemUserBase u ON u.SystemUserId = i.new_musteritemsilcisi
WHERE LOWER(u.DomainName) LIKE '%\\{rep}' AND a.StateCode = 0 AND a.new_BMTilveyaCari = 0""")[0]["n"]
    got = port["count"]
    record(3, "Portföy cari sayısı", "BAŞARILI" if got <= int(own) + int(il) and got > 0 else "BAŞARISIZ",
           {"api": got, "crmSahip": int(own), "crmIl": int(il),
            "not": "API yalnız Logo'da kodu eşleşen müşteri carilerini sayar; fark = Logo'da olmayan CRM carisi"})

    # 4. CRM onay bekleyen tahsilat
    s, colr = api(args.bridge, f"/api/v1/field/collections/crm?durum=onay-bekliyor&temsilci={rep}", cookie)
    ref = rows(crm, f"""SELECT COUNT(*) AS n, SUM(t.new_tutar) AS tutar FROM {p}new_tahsilatBase t
JOIN {p}SystemUserBase u ON u.SystemUserId = t.OwnerId
WHERE t.statecode = 0 AND t.statuscode = 100000000 AND LOWER(u.DomainName) LIKE '%\\{rep}'""")[0]
    same = s == 200 and colr["count"] >= int(ref["n"]) and colr["total"] >= float(ref["tutar"] or 0) - TOL
    record(4, "CRM onay bekleyen tahsilat", "BAŞARILI" if same else "BAŞARISIZ",
           {"api": colr if s != 200 else {"count": colr["count"], "total": colr["total"]}, "referans": {"n": int(ref["n"]), "tutar": float(ref["tutar"] or 0)},
            "not": "API sahibi temsilci olan + portföyündeki carinin kaydını gösterir; referans yalnız sahibi (alt küme)"})

    # 5. Karşılıksız olay (12 ay) — analiz §14 kabul 5
    ok, ev = True, []
    since = asof - timedelta(days=365)
    for c in sample:
        n = 0
        for firm in (f, os.environ.get("FIELD_PREV_FIRM", "211")):
            r = rows(logo, f"""SELECT COUNT(*) AS n FROM dbo.LG_{firm}_01_CSCARD K
WHERE K.CANCELLED = 0 AND K.DOC IN (1, 2)
  AND EXISTS (SELECT 1 FROM dbo.LG_{firm}_01_CSTRANS T WHERE T.CSREF = K.LOGICALREF AND T.STATUS = 11 AND T.DEVIR = 0
              AND T.CANCELLED = 0 AND T.DATE_ >= '{since}')
  AND K.LOGICALREF IN (SELECT G.CSREF FROM dbo.LG_{firm}_01_CSTRANS G JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = G.CARDREF
                       WHERE C.CODE = '{c['code']}' AND G.STATUS = 1 AND G.CANCELLED = 0)""")
            n += int(r[0]["n"])
        got = ((briefs.get(c["code"]) or {}).get("signals") or {}).get("karsiliksiz_olay_12ay")
        same = int(got or 0) == n
        ok &= same
        ev.append({"code": c["code"], "api": got, "referans": n, "ayni": same})
    record(5, "Karşılıksız çek/senet olayı (5 cari)", "BAŞARILI" if ok and sample else "BAŞARISIZ" if sample else "DOĞRULANAMADI", ev)

    # 6. Risk doluluğu
    ok, ev = True, []
    for c in sample:
        r = rows(crm, f"""SELECT new_toplamrisk / NULLIF(new_toplamrisklimiti, 0) AS d FROM {p}AccountBase
WHERE new_CariKodu = '{c['code']}' AND StateCode = 0""")
        want = float(r[0]["d"]) if r and r[0]["d"] is not None else None
        got = ((briefs.get(c["code"]) or {}).get("signals") or {}).get("risk_doluluk")
        same = (want is None and got is None) or (want is not None and got is not None and abs(want - got) < 1e-3)
        ok &= same
        ev.append({"code": c["code"], "api": got, "referans": want, "ayni": same})
    record(6, "Risk doluluğu (5 cari)", "BAŞARILI" if ok and sample else "BAŞARISIZ" if sample else "DOĞRULANAMADI", ev)

    # 7. Hedef dağıtımı: cari hedeflerinin toplamı = yürürlükteki planın toplamı
    tgt = meta["run"].get("target") or {}
    if tgt.get("kaynak") == "m46":
        s, allp = api(args.bridge, "/api/v1/field/portfolio", cookie)
        # Cari yıllık hedefi portföy satırında yok; toplam hedef, beklenen ÷ pay ile geri kurulur.
        pay = tgt.get("pay") or 0
        total = sum((c.get("hedefBeklenen") or 0) for c in allp["items"]) / pay if pay else None
        same = total is not None and abs(total - float(tgt["toplamHedef"])) <= max(1.0, 1e-6 * float(tgt["toplamHedef"]))
        record(7, "Hedef dağıtımı toplamı = plan", "BAŞARILI" if same else "BAŞARISIZ", {"api": total, "plan": tgt["toplamHedef"]})
    else:
        record(7, "Hedef dağıtımı toplamı = plan", "DOĞRULANAMADI", {"not": "yürürlükte bütçe planı yok (M46)", "kaynak": tgt.get("kaynak")})

    # 8. Kapsam
    rc, other = os.environ.get("FIELD_REP_COOKIE"), os.environ.get("FIELD_OTHER_CODE")
    if rc and other:
        s, _ = api(args.bridge, f"/api/v1/field/customers/{urllib.parse.quote(other)}/brief", rc)
        record(8, "Başka temsilcinin carisi 403", "BAŞARILI" if s == 403 else "BAŞARISIZ", {"durum": s})
    else:
        record(8, "Başka temsilcinin carisi 403", "DOĞRULANAMADI", {"not": "FIELD_REP_COOKIE / FIELD_OTHER_CODE verilmedi"})

    with open(args.out, "w") as fh:
        json.dump({"asof": str(asof), "dataEnd": str(data_end), "rep": rep, "sonuclar": results}, fh, ensure_ascii=False, indent=2, default=str)
    bad = [r for r in results if r["durum"] == "BAŞARISIZ"]
    print(f"\n{len(results) - len(bad)}/{len(results)} başarısız değil · kanıt {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":


    sys.exit(main())
