#!/usr/bin/env python3
"""M38 Müşteri ilişkileri — gerçek DB kabulü (test sunucusunda koşar; Mac'te koşmaz).

Köprünün kullanıcıya verdiği sonucu (`/api/v1/musteri/*`, gerçek oturum) aynı Logo/CRM veritabanında **bağımsız** yazılmış
referans SQL ile karşılaştırır. Referans SQL'ler `musteri_sources.py` / `field_sales_sources.py`'den alınmaz; analiz
belgesinin §14 kabul listesinden elle yazılmıştır. Tanım: net = faturalı satır (`STLINE`, `LINETYPE = 0`,
`INVOICEREF <> 0`, `CANCELLED = 0`) `LINENET` satış (7,8,9) − iade (2,3); fatura seviyesi (`INVOICE.NETTOTAL`) bilgi
amaçlı ayrıca yazdırılır (~%1 fark beklenir: satırı olmayan fatura, fatura seviyesi ek tutar).

Yıl kopyaları: `--firm` bu yılın firması (411 = 2026), `--prev-firm` önceki yılların firması (211 = 2021–2025). Her firma
yalnız kendi yıllarının tarih aralığında okunur (`--year-start` = bu yılın ilk günü); cari kodla birleşir.

Kontroller (analiz §14 «Kabul testleri»):
  1. Cari 12 ay net (20 cari; iki kopya, kodla) = cari ayrıntısı `net12` (kuruş).
  2. Son fatura: iki kopyada MAX(DATE_) faturalı satış = `sonFatura`.
  3. Logo bağı yok: CRM etkin cari (kod ve bağ boş) + (kodu/bağı Logo'da bulunamayan) = veri sağlığı «Logo bağı yok».
  4. Kanal dağılımı: CRM etkin cari `new_FirmaKanal` sayıları = veri sağlığı «CRM firma kanalı» dağılımı.
  5. Ortak hesap: sahibi «Timas CRM» (etkin kullanıcı, kişi sahibi) olan etkin cari = «Ortak hesaba ait» bulgusu.
  6. Kanal toplamı: bu yıl Logo özel kod 2 kanal net (120 carileri) = özet ekranı kanal «bu yıl net» değerleri.
  7. Portföy güvenliği: temsilci oturumuyla /accounts yalnız o temsilcinin carileri; başkasının carisi 403
     (MUSTERI_REP_COOKIE verilmezse DOĞRULANAMADI).
  8. İlk 10 cari (bu yıl net, satır seviyesi) = cari listesinin «Bu yıl net» sırasının ilk 10'u; fatura seviyesi kayıtlı
     SQL'in (m-teri-yo-unla-mas-2026…) ilk 10'uyla kesişim bilgi olarak.
  9. Aylık grafik (3 cari): ay başına net = `/accounts/{kod}/monthly`.
 10. Medyan alım aralığı (5 cari, «kendi» kaynaklı): son 24 ay alım günlerinin ardışık farklarının medyanı = `aralik`.

Kullanım (test sunucusunda, köprünün ortam dosyası yüklü; `timasai` 15 dk'lık oturumuyla, bitince oturum silinir):
  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  MUSTERI_COOKIE='timas_session=…' [MUSTERI_REP_COOKIE='timas_session=…' MUSTERI_REP=ayseb] \\
    python3 scripts/acceptance/M38/reference_check.py --bridge http://127.0.0.1:8795 --out /tmp/claude-<oturum>/m38.json
  MUSTERI_COOKIE yetkisi `ozellik:musteri.herkesinki` ve `sayfa:musteri-veri-sagligi` olan hesabın (yönetici).

Sonuç: her kontrol BAŞARILI / BAŞARISIZ / DOĞRULANAMADI; kanıt JSON'u `--out`'a.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402

TOL = 0.01
#: CRM `new_FirmaKanal` seçenek etiketleri (kabul için ayrıca yazıldı; köprü kodundan alınmadı).
FIRMA_KANAL = {100000008: "Bayi", 100000004: "Dağıtıcı", 100000001: "Kitapçı", 100000003: "Perakende",
               100000005: "E-ticaret", 100000002: "Market", 100000006: "Fuar", 100000009: "Tüketici-okur",
               100000000: "Sincap Kitap", 100000007: "Diğer"}


def api(base: str, path: str, cookie: str) -> tuple[int, object]:
    req = urllib.request.Request(base + path, headers={"cookie": cookie})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def rows(conn, sql: str) -> list[dict]:
    _c, rs, trunc = conn.execute(sql, 5_000_000)
    assert not trunc, "referans sorgu kesildi"
    return [{str(k).lower(): v for k, v in r.items()} for r in rs]


def d10(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10]


def near(a, b) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= TOL


def line_net_sql(firm: str, code_cond: str, lo: date, hi: date, group: str = "C.CODE") -> str:
    return f"""SELECT {group} AS k,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net,
  MAX(CASE WHEN S.TRCODE IN (7,8,9) THEN S.DATE_ END) AS son
FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) AND {code_cond}
  AND S.DATE_ >= '{lo}' AND S.DATE_ < '{hi + timedelta(days=1)}'
GROUP BY {group}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8795")
    ap.add_argument("--out", required=True)
    ap.add_argument("--firm", default="411")
    ap.add_argument("--prev-firm", default="211")
    ap.add_argument("--year-start", default="2026-01-01", help="bu yılın firmasının ilk günü")
    ap.add_argument("--schema", default=os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo"))
    ap.add_argument("--shared-owner", default="Timas CRM")
    args = ap.parse_args()
    cookie = os.environ["MUSTERI_COOKIE"]
    logo = connector_from_file(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    f, pf, p = args.firm, args.prev_firm, args.schema.rstrip(".") + "."
    y0 = date.fromisoformat(args.year_start)
    results: list[dict] = []

    def record(no: int, name: str, status: str, detail: object) -> None:
        results.append({"no": no, "kontrol": name, "durum": status, "kanit": detail})
        print(f"[{status}] {no}. {name}")

    def both(code_cond: str, lo: date, hi: date, group: str = "C.CODE") -> dict:
        """İki kopya, her biri kendi yıllarına kırpılmış; anahtar üzerinden toplanır."""
        out: dict = {}
        for firm, a, b in ((pf, lo, min(hi, y0 - timedelta(days=1))), (f, max(lo, y0), hi)):
            if a > b:
                continue
            for r in rows(logo, line_net_sql(firm, code_cond, a, b, group)):
                k = r["k"] if r["k"] not in (None, "") else "Belirsiz"
                cur = out.setdefault(k, {"net": 0.0, "son": None})
                cur["net"] += float(r["net"] or 0)
                s = d10(r["son"])
                if s and (cur["son"] is None or s > cur["son"]):
                    cur["son"] = s
        return out

    st, meta = api(args.bridge, "/api/v1/musteri/meta", cookie)
    if st != 200 or not meta["run"].get("kesim"):
        print("köprü okunamadı ya da gece turu koşmamış:", st, meta)
        return 2
    kesim = date.fromisoformat(meta["run"]["kesim"])
    st, lst = api(args.bridge, "/api/v1/musteri/accounts?sort=deger&size=1000", cookie)
    sample = [a for a in lst["items"] if (a.get("net12") or 0) > 0][:20]

    # 1–2. 12 ay net ve son fatura
    ok1 = ok2 = True
    ev1, ev2 = [], []
    details = {}
    for a in sample:
        code = a["code"].replace("'", "''")
        ref = both(f"C.CODE = '{code}'", kesim - timedelta(days=364), kesim)
        allt = both(f"C.CODE = '{code}'", kesim - timedelta(days=364 * 3), kesim)
        s, d = api(args.bridge, f"/api/v1/musteri/accounts/{urllib.parse.quote(a['code'])}", cookie)
        details[a["code"]] = d if s == 200 else None
        got = (d or {}).get("net12") if s == 200 else None
        want = sum(v["net"] for v in ref.values())
        same = got is not None and near(got, want)
        ok1 &= same
        ev1.append({"code": a["code"], "api": got, "referans": round(want, 2), "ayni": same})
        son = max((v["son"] for v in allt.values() if v["son"]), default=None)
        same2 = s == 200 and d.get("sonFatura") == son
        ok2 &= same2
        ev2.append({"code": a["code"], "api": (d or {}).get("sonFatura") if s == 200 else None, "referans": son, "ayni": same2})
    record(1, "Cari 12 ay net (20 cari, iki kopya)", "BAŞARILI" if ok1 and sample else "BAŞARISIZ" if sample else "DOĞRULANAMADI", ev1)
    record(2, "Son fatura (20 cari)", "BAŞARILI" if ok2 and sample else "BAŞARISIZ" if sample else "DOĞRULANAMADI", ev2)

    # 3–5. Veri sağlığı
    st, h = api(args.bridge, "/api/v1/musteri/health?size=1", cookie)
    counts = (h or {}).get("sayilar", {}) if st == 200 else {}
    present = lambda t: sum(counts.get(t, {}).get(k, 0) for k in ("acik", "crmde_duzeltildi", "yoksay"))  # noqa: E731
    accs = rows(crm, f"SELECT CAST(AccountId AS nvarchar(40)) AS id, new_CariKodu AS kod, new_logicalref AS ref FROM {p}AccountBase WHERE StateCode = 0")
    codes: set[str] = set()
    refs: set[int] = set()
    for firm in (f, pf):
        for r in rows(logo, f"SELECT CODE AS kod, LOGICALREF AS ref FROM dbo.LG_{firm}_CLCARD"):
            codes.add((r["kod"] or "").strip().upper())
            if firm == f:
                refs.add(int(r["ref"]))
    empty = sum(1 for a in accs if not (a["kod"] or "").strip() and not (a["ref"] or "").strip())
    missing = sum(1 for a in accs if ((a["kod"] or "").strip() or (a["ref"] or "").strip())
                  and (a["kod"] or "").strip().upper() not in codes
                  and not ((a["ref"] or "").strip().isdigit() and int(a["ref"].strip()) in refs))
    want3 = empty + missing
    record(3, "Logo bağı yok", "BAŞARILI" if st == 200 and present("logo_bagi_yok") == want3 else "BAŞARISIZ",
           {"api": present("logo_bagi_yok"), "referans": want3, "bos": empty, "logodaYok": missing, "etkinCari": len(accs)})

    kan = rows(crm, f"SELECT CAST(new_FirmaKanal AS int) AS k, COUNT(*) AS n FROM {p}AccountBase WHERE StateCode = 0 GROUP BY new_FirmaKanal")
    want4 = {}
    for r in kan:
        lab = "Boş" if r["k"] is None else FIRMA_KANAL.get(int(r["k"]), "Diğer kod")
        want4[lab] = want4.get(lab, 0) + int(r["n"])
    got4 = (h or {}).get("crmKanal") if st == 200 else None
    record(4, "CRM kanal dağılımı", "BAŞARILI" if got4 == want4 else "BAŞARISIZ", {"api": got4, "referans": want4})

    n5 = rows(crm, f"""SELECT COUNT(*) AS n FROM {p}AccountBase a JOIN {p}SystemUserBase u ON u.SystemUserId = a.OwnerId
WHERE a.StateCode = 0 AND a.OwnerIdType = 8 AND u.IsDisabled = 0 AND u.FullName = N'{args.shared_owner}'""")[0]["n"]
    record(5, "Ortak hesaba ait cari", "BAŞARILI" if present("ortak_hesap") == int(n5) else "BAŞARISIZ",
           {"api": present("ortak_hesap"), "referans": int(n5)})

    # 6. Kanal toplamı (bu yıl)
    st, ov = api(args.bridge, "/api/v1/musteri/overview", cookie)
    ref6 = both("C.CODE LIKE '120%'", y0, kesim, group="C.SPECODE2")
    got6 = {k["kanal"]: k["netYil"] for k in (ov or {}).get("kanallar", [])} if st == 200 else {}
    diff = {k: {"api": got6.get(k), "referans": round(v["net"], 2)} for k, v in ref6.items() if not near(got6.get(k), v["net"])}
    record(6, "Kanal bu yıl net (özel kod 2)", "BAŞARILI" if st == 200 and not diff else "BAŞARISIZ",
           {"fark": diff, "kanal": len(ref6), "not": "yalnız önceki yıl kartı olan carinin kanalı önceki yıl kartından"})

    # 7. Portföy güvenliği
    rep_cookie, rep = os.environ.get("MUSTERI_REP_COOKIE"), (os.environ.get("MUSTERI_REP") or "").lower()
    if rep_cookie and rep:
        s1, mine = api(args.bridge, "/api/v1/musteri/accounts?size=1000", rep_cookie)
        s2, all_rep = api(args.bridge, f"/api/v1/musteri/accounts?size=1000&temsilci={rep}", cookie)
        other = next((a for a in lst["items"] if a.get("temsilci") and a["temsilci"] != rep), None)
        s3, _ = api(args.bridge, f"/api/v1/musteri/accounts/{urllib.parse.quote(other['code'])}", rep_cookie) if other else (None, None)
        only = s1 == 200 and all(a.get("temsilci") == rep for a in mine["items"])
        same = s2 == 200 and s1 == 200 and mine["total"] == all_rep["total"]
        record(7, "Portföy güvenliği", "BAŞARILI" if only and same and s3 == 403 else "BAŞARISIZ",
               {"temsilci": rep, "kendi": mine.get("total") if s1 == 200 else s1, "yetkiliIle": all_rep.get("total") if s2 == 200 else s2,
                "baskasininCarisi": s3})
    else:
        record(7, "Portföy güvenliği", "DOĞRULANAMADI", {"not": "MUSTERI_REP_COOKIE / MUSTERI_REP verilmedi"})

    # 8. İlk 10 (bu yıl)
    ref8 = both("C.CODE LIKE '120%'", y0, kesim)
    top = sorted(ref8.items(), key=lambda kv: -kv[1]["net"])[:10]
    st, yl = api(args.bridge, "/api/v1/musteri/accounts?sort=yil&size=10", cookie)
    got8 = [(a["code"], a["netYil"]) for a in (yl or {}).get("items", [])] if st == 200 else []
    same8 = [c for c, _ in got8] == [c for c, _ in top] and all(near(g, v["net"]) for (_, g), (_, v) in zip(got8, top))
    inv = rows(logo, f"""SELECT TOP 10 c.CODE AS k, SUM(CASE WHEN i.TRCODE IN (7,8,9) THEN i.NETTOTAL ELSE -i.NETTOTAL END) AS net
FROM dbo.LG_{f}_01_INVOICE i JOIN dbo.LG_{f}_CLCARD c ON c.LOGICALREF = i.CLIENTREF
WHERE i.CANCELLED = 0 AND i.TRCODE IN (2,3,7,8,9) AND i.DATE_ >= '{y0}' AND i.DATE_ < '{kesim + timedelta(days=1)}'
GROUP BY c.CODE ORDER BY net DESC""")
    record(8, "İlk 10 cari (bu yıl net)", "BAŞARILI" if same8 else "BAŞARISIZ",
           {"api": got8, "referans": [(c, round(v["net"], 2)) for c, v in top],
            "faturaSeviyesiKesisim": len({c for c, _ in got8} & {r["k"] for r in inv})})

    # 9. Aylık grafik
    ok9, ev9 = True, []
    for a in sample[:3]:
        code = a["code"].replace("'", "''")
        s, mo = api(args.bridge, f"/api/v1/musteri/accounts/{urllib.parse.quote(a['code'])}/monthly", cookie)
        first = mo["items"][0]["ay"] if s == 200 and mo["items"] else None
        start = date(int(first[:4]), int(first[5:7]), 1) if first else kesim
        ref9 = both(f"C.CODE = '{code}'", start, kesim, group="CONVERT(char(7), S.DATE_, 126)")
        want = {k: round(v["net"], 2) for k, v in ref9.items()}
        got = {m["ay"]: m["net"] for m in mo["items"] if m["net"] != 0} if s == 200 else {}
        same = s == 200 and set(got) == {k for k, v in want.items() if abs(v) > TOL} and all(near(got[k], want[k]) for k in got)
        ok9 &= same
        ev9.append({"code": a["code"], "api": got, "referans": want, "ayni": same})
    record(9, "Aylık net (3 cari)", "BAŞARILI" if ok9 and sample else "DOĞRULANAMADI" if not sample else "BAŞARISIZ", ev9)

    # 10. Medyan alım aralığı («kendi» kaynaklı 5 cari)
    ok10, ev10 = True, []
    own = [c for c, d in details.items() if d and d.get("aralikKaynagi") == "kendi"][:5]
    for c in own:
        code = c.replace("'", "''")
        days: set[str] = set()
        lo = kesim - timedelta(days=729)
        for firm, a_, b_ in ((pf, lo, y0 - timedelta(days=1)), (f, y0, kesim)):
            for r in rows(logo, f"""SELECT DISTINCT S.DATE_ AS g FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE C.CODE = '{code}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9) AND S.LINENET > 0
  AND S.DATE_ >= '{a_}' AND S.DATE_ < '{b_ + timedelta(days=1)}'"""):
                days.add(d10(r["g"]))
        ds = sorted(date.fromisoformat(x) for x in days)
        gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
        want = float(statistics.median(gaps)) if gaps else None
        got = details[c].get("aralik")
        same = want is not None and got is not None and abs(round(want, 1) - got) < 0.05
        ok10 &= same
        ev10.append({"code": c, "api": got, "referans": want, "gun": len(ds), "ayni": same})
    record(10, "Medyan alım aralığı (5 cari)", "BAŞARILI" if ok10 and own else "DOĞRULANAMADI" if not own else "BAŞARISIZ", ev10)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"zaman": datetime.now().isoformat(), "kesim": kesim.isoformat(), "asof": meta["run"].get("asof"),
                   "sonuclar": results}, fh, ensure_ascii=False, indent=2, default=str)
    bad = [r for r in results if r["durum"] == "BAŞARISIZ"]
    print(f"toplam {len(results)}: başarılı {sum(r['durum'] == 'BAŞARILI' for r in results)}, başarısız {len(bad)}, "
          f"doğrulanamadı {sum(r['durum'] == 'DOĞRULANAMADI' for r in results)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
