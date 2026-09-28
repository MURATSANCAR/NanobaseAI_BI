"""M41 Amazon ve yurtdışı — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur Logo ve CRM).

Uçların verdiği sonuç, modülün SQL'i kullanılmadan yazılmış doğrudan Logo/CRM sorgularıyla karşılaştırılır
(`referans.sql` K1–K7). Amazon'a hiçbir istek gitmez (K8 ağsız sınar).

Yazma yok: yalnız geçersiz gövdeli istekler (400/404) denenir. İsteğe bağlı `M41_TASLAK=<stok kodu>` verilirse tek
listeleme taslağı yazılır (Zeki AI), kimliği çıktıya düşer ve `temizlik.py --drafts <id>` siler. «Veriyi yenile» ve
Excel indirme değişiklik kaydına satır yazar — `temizlik.py --since <başlangıç>` siler.

Ortam: BASE, COOKIE (timasai, yönetici), SEMANTIC_CONNECTION_FILE (Logo), SEMANTIC_CRM_CONNECTION_FILE, CRM_SCHEMA,
PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M41_YENILEME=0, M41_TASLAK.
Kullanım: python kabul.py --out /tmp/claude-m41/kabul.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone

import httpx

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/channels/amazon"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=900, raw=False):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Cookie": COOKIE}
    if body is not None:
        headers["Content-Type"] = "application/json"
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
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)
    latest = firms[max(firms)]
    p = SCHEMA.rstrip(".") + "."
    draft_id = None

    # 0. Geçersiz istekler (yazmaz).
    s, _ = http("PUT", P + "/params/DE", {"ad": "Almanya", "kdvOrani": 7})
    check("geçersiz KDV oranı 400", s == 400, str(s))
    s, _ = http("POST", P + "/drafts", {})
    check("stok kodsuz taslak 400", s == 400, str(s))
    s, _ = http("POST", P + "/market-cards/yok/decision", {"karar": "girilsin"})
    check("olmayan kart kararı 404", s == 404, str(s))
    s, _ = http("POST", P + "/cariler/ekle", {"kod": "YOK-BOYLE-CARI-M41"})
    check("adla bulunmayan cari eklenmez 404", s == 404, str(s))

    if os.environ.get("M41_YENILEME", "1") != "0":
        http("POST", P + "/refresh")
        t0 = time.time()
        st = {}
        while time.time() - t0 < 3600:
            time.sleep(10)
            s, st = http("GET", P + "/status")
            if s == 200 and not st["job"]["running"]:
                break
        check("okuma bitti, hata yok", s == 200 and not st["job"]["running"] and not st["job"]["error"], str(st.get("job", {}).get("error"))[:200])
    s, meta = http("GET", P + "/meta")
    check("meta 200 ve API kapalı", s == 200 and meta["api"]["bagli"] is False, str(s))
    read = meta.get("read") or {}
    if not read.get("years"):
        return finish(a.out, started, draft_id)
    end = date.fromisoformat(read["veriSonu"])
    yil = end.year
    firm = firms[yil]
    specodes = read.get("yurtdisiKodlari") or ["YURTDIŞI", "YURTDISI"]
    print(f"   veri sonu {end}, firma {firm}, yurtdışı kodları {specodes}")
    print("   bilgi: özel kod 2 yazımları: " + ", ".join(str(r["SPECODE2"]) for r in logo(
        f"SELECT DISTINCT SPECODE2 FROM dbo.LG_{latest}_CLCARD WHERE SPECODE2 LIKE N'%YURT%' OR SPECODE2 LIKE N'%IHRA%' OR SPECODE2 LIKE N'%İHRA%'")))

    # K1 · Amazon adlı cariler = doğrudan CLCARD (+ CRM kartlarının Logo bağı bilgi olarak).
    s, acc = http("GET", P + "/accounts")
    pats = acc.get("desenler") or ["AMAZON"]
    cond = " OR ".join(f"DEFINITION_ LIKE {q('%' + x + '%')}" for x in pats)
    ref1 = {str(r["CODE"]).strip() for r in logo(f"SELECT CODE FROM dbo.LG_{latest}_CLCARD WHERE {cond}")}
    got1 = {x["cariKodu"] for x in acc.get("adayCariler", [])}
    check("K1 Amazon adlı cariler birebir", ref1 == got1, f"SQL {len(ref1)} / ekran {len(got1)}; {sorted(ref1)[:5]}")
    for r in crm(f"SELECT Name, new_logicalref FROM {p}AccountBase WHERE StateCode = 0 AND Name LIKE N'%Amazon%'"):
        print(f"   bilgi: CRM «{r['Name']}» → Logo ref {r['new_logicalref']}")
    codes = acc.get("onayli") or []

    # K2 · Onaylı Amazon carilerinin net cirosu (M42 karnesi) = faturalı satır SQL'i.
    w = acc.get("toptan") or {}
    if codes and w.get("donem"):
        ay = int(w["period"]["ay"]) if "ay" in w["period"] else end.month
        ay_sonu = date(yil + (ay == 12), ay % 12 + 1, 1).isoformat()
        net = logo(f"SELECT SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net "
                   f"FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
                   f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) "
                   f"AND c.CODE IN ({', '.join(q(x) for x in codes)}) AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}'")[0]["net"] or 0
        check("K2 Amazon net ciro birebir", near(w["donem"]["netCiro"], net), f"ekran {w['donem']['netCiro']:,.2f} / SQL {float(net):,.2f}")
    else:
        print(f"   K2 atlandı: {w.get('neden') or 'Amazon carisi onaylanmadı'}")

    # K3 · Konsinye kalan kitap bazında = faturalanmamış sevk − iade irsaliyesi.
    if codes:
        ref3: dict[str, float] = defaultdict(float)
        for y in read.get("konsinyeYillari") or [yil]:
            f = firms[y]
            for r in logo(f"SELECT i.CODE AS stok, SUM(CASE WHEN l.TRCODE = 8 THEN l.AMOUNT ELSE -l.AMOUNT END) AS kalan "
                          f"FROM dbo.LG_{f}_01_STLINE l JOIN dbo.LG_{f}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
                          f"JOIN dbo.LG_{f}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
                          f"WHERE l.TRCODE IN (3, 8) AND l.CANCELLED = 0 AND l.LINETYPE = 0 AND l.INVOICEREF = 0 AND l.BILLED = 0 "
                          f"AND c.CODE IN ({', '.join(q(x) for x in codes)}) AND l.DATE_ >= '{y}-01-01' AND l.DATE_ < '{y + 1}-01-01' GROUP BY i.CODE"):
                ref3[str(r["stok"]).strip()] += float(r["kalan"] or 0)
        got3 = {x["stokKodu"]: x["kalan"] for x in all_pages("/consignment")}
        bad = [f"{k} {got3.get(k)}/{v}" for k, v in ref3.items() if not near(got3.get(k, 0.0), v, 0.001)]
        bad += [f"{k} fazla" for k in got3 if k not in ref3]
        check(f"K3 konsinye kalan birebir ({len(ref3)} kitap)", not bad, "; ".join(bad[:4]) or f"toplam {sum(ref3.values()):,.0f}")
    else:
        print("   K3 atlandı: onaylı Amazon carisi yok")

    # K4 · CRM Amazon Konsinye sipariş sayısı (yıl başına).
    s, ov = http("GET", P + "/overview")
    tip = int(meta["settings"]["konsinyeTipi"])
    bas = f"{min(read['years'])}-01-01"
    ref4 = {str(int(r["yil"])): int(r["n"]) for r in crm(
        f"SELECT YEAR(new_siparistarihi) AS yil, COUNT(*) AS n FROM {p}new_siparisBase WHERE statecode = 0 AND new_siparistipi = {tip} "
        f"AND new_siparistarihi >= '{bas}' GROUP BY YEAR(new_siparistarihi)") if r.get("yil")}
    got4 = (ov.get("crm") or {}).get("siparis") or {}
    check("K4 CRM Amazon Konsinye sipariş sayısı birebir", ref4 == got4, f"SQL {ref4} / ekran {got4}")

    # K5 · Yurtdışı net ciro cari bazında (verinin son yılı).
    ref5 = {str(r["cari"]).strip(): float(r["net"] or 0) for r in logo(
        f"SELECT c.CODE AS cari, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net "
        f"FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
        f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) "
        f"AND c.SPECODE2 IN ({', '.join(q(x) for x in specodes)}) AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{yil + 1}-01-01' GROUP BY c.CODE")}
    s, intl = http("GET", P + f"/international?yil={yil}")
    got5: dict[str, float] = defaultdict(float)
    for x in intl.get("items", []) if s == 200 else []:
        got5[x["cari"]] += x["netCiro"]
    bad = [f"{k} {got5.get(k, 0):,.2f}/{v:,.2f}" for k, v in ref5.items() if not near(got5.get(k, 0.0), v)]
    check(f"K5 yurtdışı net ciro cari bazında birebir ({len(ref5)} cari)", s == 200 and not bad, "; ".join(bad[:4]) or f"toplam {sum(ref5.values()):,.2f}")
    print(f"   bilgi: ülke alanı boş cari: {sum(1 for x in intl.get('items', []) if x['ulke'] == 'Ülke yazılmamış')}")

    # K6 · Döviz faturası sayısı (bütün türler ve satış).
    r6 = logo(f"SELECT COUNT(*) AS toplam, SUM(CASE WHEN TRCODE IN (7,8,9) THEN 1 ELSE 0 END) AS satis FROM dbo.LG_{firm}_01_INVOICE "
              f"WHERE CANCELLED = 0 AND ISNULL(TRCURR, 0) NOT IN (0, 160) AND DATE_ >= '{yil}-01-01' AND DATE_ < '{yil + 1}-01-01'")[0]
    got6 = intl.get("dovizFatura") or {}
    check("K6 döviz faturası sayısı birebir", int(r6["toplam"] or 0) == got6.get("toplam") and int(r6["satis"] or 0) == got6.get("satis"),
          f"SQL {r6['toplam']}/{r6['satis']} · ekran {got6.get('toplam')}/{got6.get('satis')} (katalog notu 74, eski ölçüm)")

    # K7 · Etkin Telif Satış sözleşmesi (kitaba bağlı) sayısı.
    r7 = crm(f"SELECT COUNT(DISTINCT s.new_sozlesmeId) AS n FROM {p}new_sozlesmeBase s "
             f"JOIN {p}new_new_sozlesme_new_kitapBase sk ON sk.new_sozlesmeid = s.new_sozlesmeId "
             f"WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 1")[0]["n"]
    s, rg = http("GET", P + "/rights")
    check("K7 Telif Satış sözleşmesi sayısı birebir", s == 200 and rg["sozlesme"] == int(r7), f"SQL {r7} / ekran {rg.get('sozlesme')}")
    if rg.get("ulkeHatasi"):
        print(f"   bilgi: {rg['ulkeHatasi']} (AMAZON_ULKE_TABLOSU ölçülecek)")

    # K8 · Amazon istemcisi yazma yolunu ağa çıkmadan reddeder; okuma da gönderilmez.
    from semantic_bridge.channels import platforms as PL
    from semantic_bridge.channels.amazon_client import AmazonClient

    def boom(request):
        raise AssertionError("ağ çağrısı")

    c = AmazonClient(lambda k: "1", transport=httpx.MockTransport(boom))
    refused = 0
    for m, path in (("PUT", "listings/2021-08-01/items/S/K"), ("POST", "feeds/2021-06-30/feeds"), ("PATCH", "listings/2021-08-01/items/S/K")):
        try:
            c.request(m, path)
        except PL.ReadOnlyViolation:
            refused += 1
    try:
        c.get("orders/v0/orders")
        sent = True
    except PL.PlatformError:
        sent = False
    check("K8 yazma reddedildi, okuma gönderilmedi", refused == 3 and not sent, f"{refused}/3")

    if os.environ.get("M41_TASLAK"):
        s, d = http("POST", P + "/drafts", {"stokKodu": os.environ["M41_TASLAK"], "pazar": "DE", "dil": "Almanca", "tur": "listeleme"}, timeout=600)
        check("taslak yazıldı (Zeki AI, gönderim yok)", s == 201, str(s))
        if s == 201:
            draft_id = d["id"]
            print(f"   taslak {draft_id}: {json.dumps(d['metin'], ensure_ascii=False)[:300]} · düşen {len(d['dusen'])}")
    s, x = http("GET", P + "/export/yurtdisi.xlsx", raw=True)
    check("yurtdışı Excel", s == 200 and x[:2] == b"PK", str(s))
    return finish(a.out, started, draft_id)


def finish(out_path: str, started: str, draft_id) -> int:
    with open(out_path, "w") as fh:
        json.dump({"since": started, "taslak": draft_id, "results": [{"ad": n, "gecti": ok, "ayrinti": d} for n, ok, d in results]},
                  fh, ensure_ascii=False)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; temizlik: temizlik.py --since {started}" + (f" --drafts {draft_id}" if draft_id else ""))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
