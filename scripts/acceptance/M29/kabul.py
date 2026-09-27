"""M29 İlk dağılım — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, köprü kodunu kullanmadan yazılmış doğrudan Logo/CRM sorgularıyla karşılaştırılır
(`referans.sql` R1–R6). Yazma: yalnız bir taslak plan açılır; kimliği `--out` dosyasına yazılır, `cleanup.py` siler.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), SEMANTIC_CONNECTION_FILE (Logo),
SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M29_STOK (denenecek kitap).
Kullanım: python kabul.py --out /tmp/claude-m29/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/distribution"
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=600):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def q(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)
    cur = firms[max(firms)]
    created: list[str] = []

    # 0. Yetkisiz ve geçersiz istekler (yazmadan önce).
    s, _ = http("POST", P + "/plans/generate", {})
    check("boş gövdeyle öneri 400", s == 400, str(s))
    s, _ = http("PATCH", P + "/plans/yok-boyle-plan/lines/1", {"adet": 1})
    check("olmayan plan 404", s == 404, str(s))

    # 1. Liste yenileme ve R1 depoya giriş.
    s, ref = http("POST", P + "/books/refresh", {})
    check("liste yenilendi", s == 200, json.dumps(ref, ensure_ascii=False)[:300])
    s, books = http("GET", P + "/books?durum=")
    items = books["items"] if s == 200 else []
    meta_s, meta = http("GET", P + "/meta")
    window = int(meta["params"]["listeGun"]) if meta_s == 200 else 90
    start = date.today() - timedelta(days=window)
    direct = {}
    for y in sorted(firms):
        if y < start.year:
            continue
        f = firms[y]
        for r in logo(f"SELECT I.CODE AS kod, MIN(L.DATE_) AS giris, SUM(L.AMOUNT) AS adet FROM dbo.LG_{f}_01_STLINE L "
                      f"JOIN dbo.LG_{f}_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = L.STOCKREF "
                      f"WHERE L.TRCODE = 13 AND L.IOCODE = 1 AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND F.CANCELLED = 0 "
                      f"AND F.PRODSTAT = 0 AND L.DATE_ >= '{start.isoformat()}' AND I.CODE LIKE '15201%' GROUP BY I.CODE"):
            k = str(r["kod"]).strip()
            d = bsrc._day(r["giris"])
            old = direct.get(k)
            direct[k] = (min(d, old[0]) if old else d, (old[1] if old else 0) + float(r["adet"] or 0))
    logo_items = [b for b in items if "logo" in b["kaynak"]]
    check("R1 Logo girişli kitap sayısı", len(logo_items) == len(direct), f"ekran {len(logo_items)} / SQL {len(direct)}")
    bad = [b["stokKodu"] for b in logo_items if b["stokKodu"] not in direct
           or b["depoGiris"] != direct[b["stokKodu"]][0].isoformat() or abs((b["baskiAdedi"] or 0) - direct[b["stokKodu"]][1]) > 0.001]
    check("R1 giriş günü ve adet birebir", not bad, f"farklı: {bad[:10]}")

    # 2. R2 stok bakiyesi.
    codes = [b["stokKodu"] for b in items][:900]
    if codes:
        stock = {str(r["kod"]).strip(): float(r["bakiye"] or 0) for r in logo(
            f"SELECT I.CODE AS kod, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye "
            f"FROM dbo.LG_{cur}_01_STLINE L JOIN dbo.LG_{cur}_ITEMS I ON I.LOGICALREF = L.STOCKREF "
            f"LEFT JOIN dbo.LG_{cur}_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF "
            f"WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1) "
            f"AND I.CODE IN ({', '.join(q(c) for c in codes)}) GROUP BY I.CODE")}
        bad = [b["stokKodu"] for b in items if b["stokKodu"] in stock and abs((b["stok"] or 0) - stock[b["stokKodu"]]) > 0.001]
        check("R2 stok bakiyesi birebir", not bad, f"{len(stock)} kitap; farklı: {bad[:10]}")

    # 3. Öneri: bir kitap (M29_STOK ya da planı olmayan ilk baskı).
    want = os.environ.get("M29_STOK") or next((b["stokKodu"] for b in items if b["durum"] == "yok" and b["ilkBaski"] and "logo" in b["kaynak"]), None)
    if not want:
        check("öneri denenecek kitap", False, "planı olmayan ilk baskı yok; M29_STOK verin")
        return finish(a.out, created)
    s, plan = http("POST", P + "/plans/generate", {"stokKodu": want})
    check("öneri kuruldu", s == 201, f"{want}: {s} {str(plan)[:200] if s != 201 else ''}")
    if s != 201:
        return finish(a.out, created)
    created.append(plan["id"])
    check("gerekçe var, ekranda teknoloji adı yok", bool(plan["gerekce"]) and not any(w in (plan["gerekce"] or "").lower() for w in ("qwen", "vllm", "llm", "model")),
          (plan["gerekce"] or "")[:160])
    # R0 hedef (M46 sözleşmesi).
    year = date.fromisoformat(plan["depoGiris"]).year
    s, tg = http("GET", f"{BASE}/api/v1/budget/targets?year={year}&stok={want}&actuals=false")
    if s == 200 and tg.get("items"):
        check("hedef = M46 yürürlükteki plan", plan["hedef"].get("yillikAdet") == tg["items"][0]["hedef"]["adet"],
              f'{plan["hedef"].get("yillikAdet")} / {tg["items"][0]["hedef"]["adet"]}')
    else:
        check("hedef yoksa plan da hedefsiz", not plan["hedef"].get("var"), f"M46 {s}, plan {plan['hedef']}")
    # Satır toplamı = başlık toplamı, önerilen = üst sınırı aşmıyor.
    total, page, lines = None, 0, []
    while True:
        s, lp = http("GET", f"{P}/plans/{plan['id']}/lines?page={page}")
        lines += lp["items"]
        total = lp["total"]
        if (page + 1) * lp["pageSize"] >= total:
            break
        page += 1
    check("müşteri listesi kesilmeden sayfalandı", len(lines) == total, f"{len(lines)} / {total}")
    check("Σ satır = plan toplamı", abs(sum(x["adet"] for x in lines) - plan["toplam"]) < 0.001, f"{sum(x['adet'] for x in lines)} / {plan['toplam']}")
    if plan["guncelStok"]["adet"] is not None:
        check("öneri + rezerv ≤ stok", plan["toplam"] + plan["rezerv"] <= plan["guncelStok"]["adet"] + 0.001,
              f"{plan['toplam']} + {plan['rezerv']} ≤ {plan['guncelStok']['adet']}")
    # R6 dağılım carileri.
    r6 = crm("SELECT COUNT(*) AS kayit, COUNT(DISTINCT COALESCE(NULLIF(new_CariKodu, ''), CAST(AccountId AS nvarchar(40)))) AS tekil "
             "FROM Timas_MSCRM.dbo.AccountBase WHERE new_distributionstatus = 1 AND StateCode = 0")[0]
    n_dist = sum(1 for x in lines if x["dagilimCarisi"])
    check("R6 dağılım carileri listede (tekil)", n_dist == int(r6["tekil"]), f"plan {n_dist} / CRM tekil {r6['tekil']} (kayıt {r6['kayit']})")

    # 4. R3 benzer kitap kanal dağılımı ve R4 geçmiş dağılım.
    for c in [x for x in plan["benzerler"] if x["secildi"] and x["pencere"]][:5]:
        a0, b0 = date.fromisoformat(c["pencere"][0]), date.fromisoformat(c["pencere"][1])
        by: dict[str, float] = {}
        net = 0.0
        for y in range(a0.year, (b0 - timedelta(days=1)).year + 1):
            f = firms.get(y)
            if not f:
                continue
            for r in logo(f"SELECT C.CODE AS cari, C.SPECODE2 AS kanal, "
                          f"SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT ELSE 0 END) - SUM(CASE WHEN L.TRCODE IN (2,3) THEN L.AMOUNT ELSE 0 END) AS net "
                          f"FROM dbo.LG_{f}_01_STLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF "
                          f"JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = L.STOCKREF WHERE I.CODE = {q(c['stokKodu'])} "
                          f"AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9) "
                          f"AND L.DATE_ >= '{a0.isoformat()}' AND L.DATE_ < '{b0.isoformat()}' GROUP BY C.CODE, C.SPECODE2"):
                n = float(r["net"] or 0)
                net += n
                by[r["cari"]] = by.get(r["cari"], 0.0) + n
        check(f"R3 {c['stokKodu']} ilk 56 gün net adet", abs((c["net"] or 0) - net) < 0.001, f"ekran {c['net']} / SQL {net}")
        check(f"R3 {c['stokKodu']} müşteri sayısı", (c["musteri"] or 0) == len(by), f"ekran {c['musteri']} / SQL {len(by)}")
        r4 = crm("SELECT SUM(ss.new_siparisadedi) AS adet FROM Timas_MSCRM.dbo.new_siparisBase s JOIN Timas_MSCRM.dbo.new_siparissatiriBase ss "
                 "ON ss.new_siparisid = s.new_siparisId WHERE s.new_siparistipi = 2 AND s.statecode = 0 AND ss.statecode = 0 "
                 f"AND ISNULL(s.statuscode, 0) <> 100000001 AND ss.new_StokKodu = {q(c['stokKodu'])}")
        ref4 = float(r4[0]["adet"]) if r4 and r4[0]["adet"] is not None else None
        check(f"R4 {c['stokKodu']} geçmiş dağılım (CRM)", (c["crmDagilimAdet"] is None and ref4 is None) or
              (c["crmDagilimAdet"] is not None and ref4 is not None and abs(c["crmDagilimAdet"] - ref4) < 0.001), f"{c['crmDagilimAdet']} / {ref4}")

    # 5. Değişmez ve iki göz (yalnız bu taslak üzerinde).
    first = next((x for x in lines if x["cariKodu"]), None)
    if first and plan["guncelStok"]["adet"] is not None:
        big = int(plan["guncelStok"]["adet"]) + 1
        http("PATCH", f"{P}/plans/{plan['id']}/lines/{first['no']}", {"adet": big})
        s, _ = http("POST", f"{P}/plans/{plan['id']}/submit", {})
        check("R değişmez: stok aşan plan onaya gidemez (409)", s == 409, str(s))
        http("PATCH", f"{P}/plans/{plan['id']}/lines/{first['no']}", {"adet": first["adet"]})
    s, _ = http("POST", f"{P}/plans/{plan['id']}/submit", {})
    if s == 200:
        s2, _ = http("POST", f"{P}/plans/{plan['id']}/approve", {})
        check("iki göz: gönderen onaylayamaz (409)", s2 == 409, str(s2))
        http("POST", f"{P}/plans/{plan['id']}/withdraw", {})
    s, _ = http("GET", f"{P}/plans/{plan['id']}/export.xlsx")
    check("taslaktan sevk listesi alınmaz (409)", s == 409, str(s))

    # 6. R5 takip sorgusu (kaynak okuyucu, geçmiş bir dönemde): köprü okuyucusu = doğrudan SQL.
    from semantic_bridge import distribution_sources as src

    L = src.Logo(logo)
    d0 = (L.data_end() or date.today()) - timedelta(days=56)
    probe = os.environ.get("M29_TAKIP_STOK") or want
    rows = L.tracking(probe, d0, d0 + timedelta(days=56))
    mine = {}
    for r in rows:
        v = mine.setdefault(r["cari_kodu"], [0.0, 0.0, 0.0])
        v[0] += r["sevk"]; v[1] += r["fatura"]; v[2] += r["iade"]
    ref5 = {}
    for f in L.firms_between(d0, d0 + timedelta(days=55)):
        for r in logo(f"SELECT C.CODE AS cari, SUM(CASE WHEN L.TRCODE IN (7,8) AND L.IOCODE = 4 THEN L.AMOUNT ELSE 0 END) AS sevk, "
                      f"SUM(CASE WHEN L.TRCODE IN (7,8,9) AND L.INVOICEREF <> 0 THEN L.AMOUNT ELSE 0 END) AS fatura, "
                      f"SUM(CASE WHEN L.TRCODE IN (2,3) THEN L.AMOUNT ELSE 0 END) AS iade FROM dbo.LG_{f}_01_STLINE L "
                      f"JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = L.STOCKREF "
                      f"WHERE I.CODE = {q(probe)} AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.TRCODE IN (2,3,7,8,9) "
                      f"AND L.DATE_ >= '{d0.isoformat()}' AND L.DATE_ < '{(d0 + timedelta(days=56)).isoformat()}' GROUP BY C.CODE"):
            v = ref5.setdefault(str(r["cari"]).strip(), [0.0, 0.0, 0.0])
            v[0] += float(r["sevk"] or 0); v[1] += float(r["fatura"] or 0); v[2] += float(r["iade"] or 0)
    diff = [k for k in set(mine) | set(ref5) if any(abs(x - y) > 0.001 for x, y in zip(mine.get(k, [0, 0, 0]), ref5.get(k, [0, 0, 0])))]
    check(f"R5 takip cari × (sevk, fatura, iade) birebir ({probe})", not diff, f"{len(ref5)} cari; farklı: {diff[:10]}")

    # 7. Bölgem ve uyarılar okunuyor.
    s, mr = http("GET", P + "/my-region")
    check("Bölgem okunuyor", s == 200, f"{s} {len(mr.get('items', [])) if s == 200 else ''}")
    s, al = http("GET", P + "/alerts")
    check("uyarılar okunuyor", s == 200, f"{s} {al.get('total') if s == 200 else ''}")
    return finish(a.out, created)


def finish(out: str, created: list[str]) -> int:
    with open(out, "w") as fh:
        json.dump({"plans": created}, fh)
    ok = sum(1 for r in results if r[1])
    print(f"== sonuç: {ok}/{len(results)} geçti; açılan plan kimlikleri {out} (cleanup.py --ids-file ile silinir)")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
