"""M33 İhale takibi — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan Logo/CRM sorgularıyla karşılaştırılır
(`referans.sql` R1–R6). Örnek şartname listesi her koşuda CRM'den rastgele seçilen kitaplardan kurulur (sabit kitap
yok): ISBN'li kitaplar, yalnız adıyla verilen kitaplar ve katalogda olmayan bir ad. Yazma: yalnız bir deneme ihalesi
açılır; kimliği `--out` dosyasına yazılır, `cleanup.py` siler (dosyaları ve değişiklik kaydı dahil).

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), isteğe bağlı COOKIE2 (ihale.karar
yetkisi olmayan ikinci oturum; yoksa 403 denemesi atlanır), SEMANTIC_CONNECTION_FILE (Logo), SEMANTIC_CRM_CONNECTION_FILE,
PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M33_YIL (kamu satış yılı; varsayılan verinin son yılı), M33_ISBN (6), M33_AD (4).
Kullanım: python kabul.py --out /tmp/claude-m33/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import tenders as T

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
COOKIE2 = os.environ.get("COOKIE2", "")
P = BASE + "/api/v1/tenders"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=900, cookie=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Cookie": cookie or COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload, r.headers.get("Content-Type", "")
            return r.status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            out = json.loads(payload)
        except ValueError:
            out = payload
        return (e.code, out, "") if raw else (e.code, out)


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def q(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def finish(out_path: str, created: list[str]) -> int:
    with open(out_path, "w") as fh:
        json.dump({"tenders": created}, fh)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {out_path} (cleanup.py ile silin)")
    return 0 if ok == len(results) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)
    cur = firms[max(firms)]
    created: list[str] = []

    # 0. Geçersiz istekler ve kapalı ilan kaynağı (yazmadan önce).
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    s, _ = http("POST", P, {})
    check("boş gövdeyle ihale 400", s == 400, str(s))
    s, _ = http("GET", P + "/yok-boyle-ihale")
    check("olmayan ihale 404", s == 404, str(s))
    s, w = http("GET", P + "/watch/status")
    check("ilan kaynağı kapalı (TENDER_WATCH_ENABLED=0)", s == 200 and w.get("enabled") is False, json.dumps(w, ensure_ascii=False)[:160])
    s, w = http("POST", P + "/watch/import", {})
    check("ilan içe alma «bu ortamda kapalı» (409) ya da yetkisiz (403)", s in (409, 403), f"{s} {str(w)[:160]}")

    # 1. R1 + R6 · Kamu kurumlarına satış ve kurum sayıları.
    year = int(os.environ.get("M33_YIL") or max(firms))
    s, ps = http("GET", P + f"/public-sales?yil={year}&yenile=true", timeout=1800)
    check("kamu satış ucu 200", s == 200, str(s) if s != 200 else f"{year}: {ps['cariSayisi']} cari")
    if s == 200:
        refs = []
        for r in crm(f"SELECT new_logicalref AS r FROM {SCHEMA}.AccountBase WHERE StateCode = 0 AND new_KurumRolu IN (2,3) AND new_logicalref IS NOT NULL"):
            digits = "".join(ch for ch in str(r["r"]) if ch.isdigit())
            if digits:
                refs.append(int(digits))
        f = firms[year]
        total = cari = 0.0
        seen: set[int] = set()
        chunks = [sorted(set(refs))[i:i + 800] for i in range(0, len(set(refs)), 800)] or [[]]
        for part in chunks:
            cond = f" OR L.CLIENTREF IN ({', '.join(str(x) for x in part)})" if part else ""
            for r in logo(f"SELECT L.CLIENTREF AS ref, SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS ciro "
                          f"FROM dbo.LG_{f}_01_STLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF "
                          f"WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9) "
                          f"AND L.DATE_ >= '{year}-01-01' AND L.DATE_ < '{year + 1}-01-01' AND (C.SPECODE2 = {q(ps['kanal'])}{cond}) "
                          f"GROUP BY L.CLIENTREF"):
                if int(r["ref"]) in seen:
                    continue
                seen.add(int(r["ref"]))
                total += float(r["ciro"] or 0)
                cari += 1
        check("R1 kamu net cirosu birebir (kuruş)", abs(total - ps["toplamCiro"]) < 0.01, f"ekran {ps['toplamCiro']:.2f} / SQL {total:.2f}")
        check("R1 cari sayısı birebir", int(cari) == ps["cariSayisi"], f"ekran {ps['cariSayisi']} / SQL {int(cari)}")
        linked = len(set(refs) & {x["ref"] for x in ps["rows"]})
        print(f"   ölçüm: CRM kamu kurumu Logo bağı {len(set(refs))}, bu yıl satışı olan {linked}; bağsız {ps['crmLogoBagsiz']}")
        counts = {int(r["rol"]): int(r["sayi"]) for r in crm(
            f"SELECT new_KurumRolu AS rol, COUNT(*) AS sayi FROM {SCHEMA}.AccountBase WHERE StateCode = 0 AND new_KurumRolu IN (2,3,4) GROUP BY new_KurumRolu")}
        screen = {int(k): v for k, v in ps["rolSayilari"].items()}
        check("R6 kamu kurum sayıları birebir", counts == screen, f"ekran {screen} / SQL {counts}")

    # 2. Örnek şartname listesi (CRM'den rastgele; sabit kitap yok).
    n_isbn = int(os.environ.get("M33_ISBN", "6"))
    n_name = int(os.environ.get("M33_AD", "4"))
    with_isbn = crm(f"SELECT TOP {n_isbn} new_StokKodu AS kod, new_name AS ad, new_yazartext AS yazar, new_isbn13 AS isbn "
                    f"FROM {SCHEMA}.new_kitapBase WHERE statecode = 0 AND ISNULL(new_StokKodu,'') <> '' AND LEN(REPLACE(REPLACE(new_isbn13,'-',''),' ','')) = 13 "
                    f"ORDER BY NEWID()")
    by_name = crm(f"SELECT TOP {n_name} new_StokKodu AS kod, new_name AS ad, new_yazartext AS yazar "
                  f"FROM {SCHEMA}.new_kitapBase WHERE statecode = 0 AND ISNULL(new_StokKodu,'') <> '' AND LEN(new_name) > 6 "
                  f"AND new_StokKodu NOT IN ({', '.join(q(r['kod']) for r in with_isbn) or q('')}) ORDER BY NEWID()")
    bogus = "Kuantum Alan Kuramına Giriş Cilt " + hashlib.sha1(str(time.time()).encode()).hexdigest()[:4]
    lines = ["Kitap Adı\tYazar\tISBN\tAdet"]
    for r in with_isbn:
        lines.append(f"{r['ad']}\t{r['yazar'] or ''}\t{r['isbn']}\t{1 + int(hashlib.sha1(r['kod'].encode()).hexdigest(), 16) % 300}")
    for r in by_name:
        lines.append(f"{r['ad']}\t{r['yazar'] or ''}\t\t{1 + int(hashlib.sha1(r['kod'].encode()).hexdigest(), 16) % 300}")
    lines.append(f"{bogus}\tDeneme Yazar\t\t5")
    print(f"   örnek: {len(with_isbn)} ISBN'li, {len(by_name)} adla, 1 katalogda yok")

    # 3. Deneme ihalesi, liste alma, eşleştirme.
    s, t = http("POST", P, {"kurum": "KABUL TESTİ — silinecek", "kurumTuru": "mem", "konu": "M33 kabul testi (kitap alımı, silinecek)",
                            "il": "İstanbul"})
    check("deneme ihalesi açıldı", s == 201, str(s))
    if s != 201:
        return finish(a.out, created)
    tid = t["id"]
    created.append(tid)
    s, imp = http("POST", P + f"/{tid}/items/import", {"text": "\n".join(lines), "mode": "replace"})
    check("liste alındı, satır kaybı yok", s == 200 and imp["eklenen"] == len(lines) - 1 and not imp["okunamayan"],
          json.dumps(imp, ensure_ascii=False)[:200])
    s, job = http("POST", P + f"/{tid}/items/match", {})
    check("eşleştirme başladı (202)", s == 202, str(s))
    deadline = time.time() + 1800
    while s == 202 and time.time() < deadline:
        time.sleep(5)
        js, job = http("GET", P + f"/{tid}/jobs/{job['id']}")
        if js != 200 or job["durum"] not in ("calisiyor", "sirada"):
            break
    check("eşleştirme bitti", job.get("durum") == "bitti", json.dumps(job, ensure_ascii=False)[:300])
    s, d = http("GET", P + f"/{tid}")
    items = d["kalemler"]

    # R2 · ISBN'li kalemler CRM'deki kaydın stok koduyla birebir.
    bad = []
    for it, r in zip(items[:len(with_isbn)], with_isbn):
        isbn = T.norm_isbn(r["isbn"])
        rows = crm(f"SELECT new_StokKodu AS kod FROM {SCHEMA}.new_kitapBase WHERE statecode = 0 AND "
                   f"(REPLACE(REPLACE(new_isbn13,'-',''),' ','') = {q(isbn)} OR REPLACE(REPLACE(new_ean13,'-',''),' ','') = {q(isbn)})")
        codes = {str(x["kod"]).strip() for x in rows if x["kod"]}
        if it["stokKodu"] not in codes or (len(codes) == 1 and it["yontem"] != "isbn"):
            bad.append((it["sira"], it["stokKodu"], it["yontem"], sorted(codes)))
    check("R2 ISBN eşleşmesi CRM ile birebir", not bad, f"farklı: {bad}")
    name_items = items[len(with_isbn):len(with_isbn) + len(by_name)]
    for it, r in zip(name_items, by_name):
        print(f"   ad: «{r['ad']}» → {it['stokKodu']} ({it['durum']}, {it['yontemAdi']}, p={it['olasilik']}) beklenen {r['kod']}")
    right = sum(1 for it, r in zip(name_items, by_name) if it["stokKodu"] == r["kod"] and it["durum"] in ("eslesti", "oneri"))
    check("adla verilen kalemler doğru kitaba (eşleşti ya da öneri)", right == len(by_name), f"{right}/{len(by_name)}")
    last = items[-1]
    check("katalogda olmayan ad eşleşmedi", last["durum"] in ("yok", "belirsiz") and last["durum"] != "eslesti", f"{last['durum']} {last['stokKodu']}")
    tech = [w for w in ("qwen", "vllm", "llm", "timesfm") if w in json.dumps(d, ensure_ascii=False).lower()]
    check("ekrana giden cevapta teknoloji adı yok", not tech, str(tech))

    matched = [it for it in items if it["stokKodu"]]
    codes = sorted({it["stokKodu"] for it in matched})
    # R3 · Stok
    if codes:
        stock = {str(r["kod"]).strip(): float(r["stok"] or 0) for r in logo(
            f"SELECT I.CODE AS kod, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS stok "
            f"FROM dbo.LG_{cur}_01_STLINE L JOIN dbo.LG_{cur}_ITEMS I ON I.LOGICALREF = L.STOCKREF "
            f"LEFT JOIN dbo.LG_{cur}_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF "
            f"WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1) "
            f"AND I.CODE IN ({', '.join(q(c) for c in codes)}) GROUP BY I.CODE")}
        bad = [(it["stokKodu"], it["stok"], stock.get(it["stokKodu"])) for it in matched
               if abs((it["stok"] or 0) - stock.get(it["stokKodu"], 0.0)) > 0.001]
        check("R3 stok bakiyesi birebir", not bad, f"{len(codes)} kitap; farklı: {bad[:10]}")
        # R4 · Fiyat
        crm_price = {str(r["kod"]).strip(): (r["fiyat"], r["kdv"]) for r in crm(
            f"SELECT new_StokKodu AS kod, new_kdvdahilfiyat AS fiyat, new_kdvorani AS kdv FROM {SCHEMA}.new_kitapBase "
            f"WHERE statecode = 0 AND new_StokKodu IN ({', '.join(q(c) for c in codes)})")}
        src_name = meta.get("ayarlar", {}).get("priceSource", "crm")
        if src_name == "crm":
            bad = [(it["stokKodu"], it["listeFiyati"], crm_price.get(it["stokKodu"])) for it in matched
                   if crm_price.get(it["stokKodu"], (None,))[0] is not None
                   and abs((it["listeFiyati"] or 0) - float(crm_price[it["stokKodu"]][0])) > 0.001]
            check("R4 liste fiyatı = CRM KDV dahil fiyat, kaynağı yazılı", not bad and all(it["fiyatKaynagi"] for it in matched), f"farklı: {bad[:10]}")
        kdv = sorted({str(v[1]) for v in crm_price.values()})
        print(f"   ölçüm: CRM KDV oranı değerleri {kdv[:10]} (yüzde mi oran mı)")

    # R5 · Teklif toplamı
    lines_total = sum(round(it["adet"] * it["onerilenFiyat"], 2) for it in items
                      if it["durum"] == "eslesti" and it["adet"] is not None and it["onerilenFiyat"] is not None)
    vat_total = sum(round(round(it["adet"] * it["onerilenFiyat"], 2) * (it["kdvOrani"] or 0), 2) for it in items
                    if it["durum"] == "eslesti" and it["adet"] is not None and it["onerilenFiyat"] is not None)
    tot = d["toplamlar"]
    check("R5 ara toplam = Σ adet × birim fiyat (kuruş)", abs(lines_total - tot["araToplam"]) < 0.005, f"{tot['araToplam']} / {lines_total:.2f}")
    check("R5 KDV ayrı satır birebir", abs(vat_total - tot["kdv"]) < 0.005, f"{tot['kdv']} / {vat_total:.2f}")
    s, xlsx, ctype = http("GET", P + f"/{tid}/pricing.xlsx", raw=True)
    check("teklif tablosu Excel", s == 200 and "spreadsheet" in ctype and xlsx[:2] == b"PK", f"{s} {ctype}")

    # Karar akışı: öneri onayı gereken kalemleri insan gibi onayla ya da «yok» işaretle, sonra iki göz.
    for it in items:
        if it["durum"] in ("oneri", "belirsiz"):
            body = {"onayla": True} if it["stokKodu"] else {"stokKodu": None}
            http("PATCH", P + f"/{tid}/items/{it['sira']}", body)
        elif it["durum"] == "bekliyor":
            http("PATCH", P + f"/{tid}/items/{it['sira']}", {"stokKodu": None})
    s, dec = http("POST", P + f"/{tid}/decision/submit", {"karar": "basvur", "gerekce": "kabul testi"})
    check("karar onaya gönderildi", s == 201, f"{s} {str(dec)[:200]}")
    if s == 201:
        s, _ = http("POST", P + f"/{tid}/decision/approve", {})
        check("öneren onaylayamaz (409)", s == 409, str(s))
        if COOKIE2:
            s, _ = http("POST", P + f"/{tid}/decision/approve", {}, cookie=COOKIE2)
            check("ihale.karar yetkisi olmadan onay 403", s == 403, str(s))
        s, _ = http("POST", P + f"/{tid}/decision/withdraw", {})
        check("öneren kararı geri çekti", s == 200, str(s))
    return finish(a.out, created)


if __name__ == "__main__":
    sys.exit(main())
