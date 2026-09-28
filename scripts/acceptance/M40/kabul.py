"""M40 Trendyol — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur Logo).

Uçların verdiği sonuç, Trendyol modülünün SQL'i kullanılmadan yazılmış doğrudan Logo sorgularıyla karşılaştırılır
(`referans.sql` K1–K7). Trendyol'a hiçbir istek gitmez (API kapalı; K5 bunu ağsız sınar).

Yazma: yalnız `M40_URUN_DOSYASI` (panelden indirilmiş GERÇEK ürün listesi, .xlsx/.csv) verilirse o dosya yüklenir, sayılır
ve kabulün sonunda API'den silinir; kimliği çıktıya yazılır. «Veriyi yenile» ve Excel indirme değişiklik kaydına satır
yazar — `temizlik.py --since <başlangıç>` siler.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturumu, yönetici), SEMANTIC_CONNECTION_FILE (Logo),
PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı: M40_URUN_DOSYASI, M40_KITAP (K4/K6 kitap sayısı, 10), M40_YENILEME=0.
Kullanım: python kabul.py --out /tmp/claude-m40/kabul.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

import httpx

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/channels/trendyol"
N = int(os.environ.get("M40_KITAP", "10"))
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=900, raw=False):
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    headers = {"Cookie": COOKIE}
    if body is not None:
        headers["Content-Type"] = "application/octet-stream" if isinstance(body, bytes) else "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload
            return r.status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def q(v) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def near(a, b, tol=0.05) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def all_pages(path: str) -> list[dict]:
    out, page = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        s, d = http("GET", P + f"{path}{sep}page={page}")
        if s != 200:
            return out
        out += d["items"]
        page += 1
        if page * d["pageSize"] >= d["total"]:
            return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    firms = bsrc.firms_by_year(logo)
    latest = firms[max(firms)]
    uploaded = None

    # 0. Geçersiz istekler (yazmaz).
    s, _ = http("POST", P + "/imports?tur=urun&filename=bos.csv", b"")
    check("boş dosya 400", s == 400, str(s))
    s, _ = http("POST", P + "/imports?tur=bilinmeyen&filename=x.csv", b"Barkod;Adet\n1;1\n")
    check("bilinmeyen tür 400", s == 400, str(s))
    s, _ = http("POST", P + "/questions/YOK-BOYLE-SORU-M40/draft")
    check("olmayan soruya taslak 400", s == 400, str(s))
    s, _ = http("POST", P + "/suggestions/yok/decision", {"karar": "onayli"})
    check("olmayan öneri kararı 404", s == 404, str(s))

    # K3 (isteğe bağlı): gerçek panel dosyası.
    path = os.environ.get("M40_URUN_DOSYASI")
    if path:
        from semantic_bridge.channels import trendyol_import as TI

        blob = open(path, "rb").read()
        local = TI.parse("urun", os.path.basename(path), blob)
        s, up = http("POST", P + f"/imports?tur=urun&filename={urllib.request.quote(os.path.basename(path))}", blob)
        check("K3 gerçek ürün dosyası yüklendi", s == 201, str(s))
        if s == 201:
            uploaded = up["id"]
            n_local = len({r["barkod"] for r in local["rows"]})
            check("K3 yüklenen satır = dosyadaki barkodlu satır", up["satir"] == n_local,
                  f"ekran {up['satir']} / dosya {n_local} (atlanan {local['bad']})")
            taninan = set((up["kolonlar"].get("taninan") or {}).values())
            check("K3 kişisel kolon içeri alınmadı", not (taninan & set(local["personal"])), ", ".join(local["personal"]) or "yok")
            open_local = sum(1 for r in local["rows"] if r["satisa_acik"] is True)
            s, pr = http("GET", P + "/products?durum=acik")
            check("K3 satışa açık ürün sayısı = dosya", s == 200 and pr["total"] == open_local, f"ekran {pr.get('total')} / dosya {open_local}")
    else:
        print("   K3 atlandı: M40_URUN_DOSYASI verilmedi (gerçek panel dosyası ölçülecek)")

    # Logo okuması (barkod, stok, fiyat, adla cari).
    if os.environ.get("M40_YENILEME", "1") != "0":
        s, st = http("POST", P + "/refresh")
        t0 = time.time()
        while time.time() - t0 < 3600:
            time.sleep(8)
            s, st = http("GET", P + "/status")
            if s == 200 and not st["job"]["running"]:
                break
        check("Logo okuması bitti, hata yok", s == 200 and not st["job"]["running"] and not st["job"]["error"], str(st["job"].get("error"))[:200])

    s, meta = http("GET", P + "/meta")
    check("meta 200 ve API kapalı", s == 200 and meta["api"]["bagli"] is False, str(s))

    # K1 · Trendyol adlı cariler = doğrudan CLCARD.
    s, acc = http("GET", P + "/accounts")
    pats = acc.get("desenler") or ["TRENDYOL", "DSM GRUP"]
    cond = " OR ".join(f"DEFINITION_ LIKE {q('%' + p + '%')}" for p in pats)
    ref1 = {str(r["CODE"]).strip() for r in logo(f"SELECT CODE FROM dbo.LG_{latest}_CLCARD WHERE {cond}")}
    got1 = {x["cariKodu"] for x in acc.get("adayCariler", [])}
    check("K1 adla bulunan cariler birebir", ref1 == got1, f"SQL {len(ref1)} / ekran {len(got1)}; {sorted(ref1)[:5]}")
    for f in sorted({f for y, f in firms.items() if f != latest}):
        old = [str(r["CODE"]).strip() for r in logo(f"SELECT CODE FROM dbo.LG_{f}_CLCARD WHERE {cond}")]
        print(f"   bilgi: {f} kopyasında aynı adla {len(old)} cari: {old[:5]}")

    # K2 · Toptan senaryo: onaylı Trendyol carilerinin net cirosu = faturalı satır SQL'i.
    w = acc.get("toptan") or {}
    if w.get("eslendi") and w.get("netCiro") is not None and w.get("cariler"):
        yil, ay = int(w["period"]["yil"]), int(w["period"]["ay"])
        ay_sonu = date(yil + (ay == 12), ay % 12 + 1, 1).isoformat()
        firm = firms[yil]
        net = logo(f"SELECT SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net "
                   f"FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
                   f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) "
                   f"AND c.CODE IN ({', '.join(q(x) for x in w['cariler'])}) AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}'")[0]["net"] or 0
        check("K2 Trendyol carisi net ciro birebir", near(w["netCiro"], net), f"ekran {w['netCiro']:,.2f} / SQL {float(net):,.2f}")
    else:
        print(f"   K2 atlandı: {w.get('neden') or 'Trendyol carisi eşlenmedi'} (boş sonuç «satış yok» demek değildir)")

    # K7 · Barkod sayısı = UNITBARCODE'daki farklı dolu barkod.
    s, st = http("GET", P + "/status")
    n7 = logo(f"SELECT COUNT(DISTINCT REPLACE(LTRIM(RTRIM(B.BARCODE)), ' ', '')) AS n FROM dbo.LG_{latest}_UNITBARCODE B "
              f"JOIN dbo.LG_{latest}_ITEMS I ON I.LOGICALREF = B.ITEMREF WHERE B.BARCODE IS NOT NULL AND LTRIM(RTRIM(B.BARCODE)) <> ''")[0]["n"]
    got7 = (st.get("logo") or {}).get("barkod")
    check("K7 barkod sayısı birebir", got7 == int(n7), f"ekran {got7} / SQL {n7}")

    # K4 · Depo stoğu (ürün listesi yüklüyse): N kitapta ekran = doğrudan bakiye.
    prods = [x for x in all_pages("/products") if x.get("stokKodu")][:N]
    if prods:
        codes = [x["stokKodu"] for x in prods]
        ref4 = {str(r["stok"]).strip(): float(r["bakiye"] or 0) for r in logo(
            f"SELECT I.CODE AS stok, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye "
            f"FROM dbo.LG_{latest}_01_STLINE L JOIN dbo.LG_{latest}_ITEMS I ON I.LOGICALREF = L.STOCKREF "
            f"LEFT JOIN dbo.LG_{latest}_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF "
            f"WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1) "
            f"AND I.CODE IN ({', '.join(q(c) for c in codes)}) GROUP BY I.CODE")}
        bad = [f"{x['stokKodu']} {x['depoStok']}/{ref4.get(x['stokKodu'], 0.0)}" for x in prods if not near(x["depoStok"], ref4.get(x["stokKodu"], 0.0), 0.001)]
        check(f"K4 {len(prods)} kitabın depo stoğu birebir", not bad, "; ".join(bad[:4]))

        # K6 · Liste fiyatı: bugün geçerli satış listesi, cariye bağlı olmayan önce, öncelik, en yeni başlangıç.
        rows = {x["stokKodu"]: x for x in all_pages("/price-diff?isaret=") if x.get("stokKodu") in codes}
        t = date.today().isoformat()
        ref6 = {}
        for c in codes:
            r = logo(f"SELECT TOP 1 P.PRICE AS fiyat, P.INCVAT AS kdv FROM dbo.LG_{latest}_PRCLIST P JOIN dbo.LG_{latest}_ITEMS I ON I.LOGICALREF = P.CARDREF "
                     f"WHERE I.CODE = {q(c)} AND P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160 AND P.PRICE > 0 AND P.BEGDATE <= '{t}' "
                     f"AND (P.ENDDATE >= '{t}' OR P.ENDDATE IS NULL) ORDER BY CASE WHEN ISNULL(P.CLIENTCODE, '') = '' AND ISNULL(P.CLSPECODE, '') = '' "
                     f"THEN 0 ELSE 1 END, P.PRIORITY, P.BEGDATE DESC")
            ref6[c] = r[0] if r else None
        bad = []
        for c, r in rows.items():
            ref = ref6.get(c)
            if ref and ref.get("kdv") and not near(r["listeFiyat"], ref["fiyat"], 0.01):
                bad.append(f"{c} {r['listeFiyat']}/{ref['fiyat']}")
        check(f"K6 liste fiyatı birebir ({len(rows)} işaretli kitap)", not bad, "; ".join(bad[:4]) or "KDV hariç listeler brütlendiği için yalnız KDV dahil olanlar kıyaslandı")
    else:
        print("   K4/K6 atlandı: yüklenmiş ürün listesi yok ya da barkodlar Logo'ya bağlanmadı")

    # K5 · Yazma koruması: istemci izinli liste dışı her yöntemi ağa çıkmadan reddeder; okuma da gönderilmez.
    from semantic_bridge.channels import platforms as PL
    from semantic_bridge.channels.trendyol_client import TrendyolClient

    def boom(request):
        raise AssertionError("ağ çağrısı")

    c = TrendyolClient(lambda k: "1", transport=httpx.MockTransport(boom))
    refused = 0
    for m, p in (("PUT", "product/sellers/1/products/price-and-inventory"), ("POST", "product/sellers/1/v2/products"),
                 ("PUT", "order/sellers/1/shipment-packages/1"), ("POST", "qna/sellers/1/questions/1/answers")):
        try:
            c.request(m, p)
        except PL.ReadOnlyViolation:
            refused += 1
    try:
        c.get("product/sellers/1/products")
        sent = True
    except PL.PlatformError:
        sent = False
    check("K5 yazma yolu reddedildi, okuma da gönderilmedi", refused == 4 and not sent, f"{refused}/4")

    s, x = http("GET", P + "/export/stok-farki.xlsx", raw=True)
    check("stok farkı Excel", s == 200 and x[:2] == b"PK", str(s))
    if uploaded:
        s, _ = http("DELETE", P + f"/imports/{uploaded}")
        check("K3 yükleme silindi", s == 200, str(s))
    return finish(a.out, started, uploaded)


def finish(out_path: str, started: str, uploaded) -> int:
    with open(out_path, "w") as fh:
        json.dump({"since": started, "yukleme": uploaded, "results": [{"ad": n, "gecti": ok, "ayrinti": d} for n, ok, d in results]},
                  fh, ensure_ascii=False)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; değişiklik kaydı satırları için: temizlik.py --since {started}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
