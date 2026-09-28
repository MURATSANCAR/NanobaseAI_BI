"""M43 Depo ve stok — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan Logo/CRM sorgularıyla karşılaştırılır
(`referans.sql` R1–R10). Yazma: yalnız bir taslak güvenlik stoku ve bir not açılır; kimlikleri `--out` dosyasına yazılır,
`cleanup.py` siler (değişiklik kaydı satırlarıyla). Gece işi (`run-due`) burada çağrılmaz: gerçek bülten ve öneri üretir,
kurulumdan sonra `systemctl start timas-stock.service` ile bir kez elle koşturulur.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), SEMANTIC_CONNECTION_FILE (Logo),
SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M43_ORNEK (örnek kitap sayısı, varsayılan 20),
M43_TOHUM (rastgele örnek tohumu).
Kullanım: python kabul.py --out /tmp/claude-m43/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/stock"
N = int(os.environ.get("M43_ORNEK", "20"))
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=1800, fresh=False):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Cookie": COOKIE, "Content-Type": "application/json"}
    if fresh:
        headers["X-Data-Refresh"] = "1"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
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
    return "N'" + v.replace("'", "''") + "'"


def near(a, b, tol=0.001) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def pages(path: str, key: str = "items"):
    out, page = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        s, d = http("GET", f"{P}{path}{sep}sayfa={page}")
        if s != 200:
            return None
        out += d[key]["items"] if key != "items" else d["items"]
        pg = d[key] if key != "items" else d
        if (page + 1) * pg["pageSize"] >= pg["total"]:
            return out
        page += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)
    cur = firms[max(firms)]
    created: dict[str, list[str]] = {"thresholds": [], "notes": []}
    rnd = random.Random(int(os.environ.get("M43_TOHUM", "43")))

    # 0. Geçersiz yazmalar (yazmadan önce).
    s, _ = http("POST", P + "/thresholds", {})
    check("boş gövdeyle eşik taslağı 400", s == 400, str(s))
    s, _ = http("POST", P + "/suggestions/yok-boyle-oneri/decision", {"karar": "kabul"})
    check("olmayan öneriye karar 404", s == 404, str(s))
    s, _ = http("POST", P + "/suggestions/yok-boyle-oneri/decision", {"karar": "belki"})
    check("geçersiz karar 400", s == 400, str(s))
    s, _ = http("GET", P + "/items/YOK-BOYLE-KOD-1")
    check("olmayan kitap 404", s == 404, str(s))

    # 1. Taze okuma ve genel görünüm.
    s, ov = http("GET", P + "/overview", fresh=True)
    check("genel görünüm okundu", s == 200, json.dumps({k: ov.get(k) for k in ("veriSonu", "stokluKitap", "bitecek", "aktarimHatasi")}, ensure_ascii=False) if s == 200 else str(ov)[:300])
    if s != 200:
        return finish(a.out, created)
    s, names = http("GET", P + "/names")
    codes_all = [x["value"] for x in names["items"]]
    details: dict[str, dict] = {}
    sample = rnd.sample(codes_all, min(N * 3, len(codes_all)))
    for c in sample:
        s, d = http("GET", f"{P}/items/{urllib.request.quote(c)}")
        if s == 200 and d["logoVar"]:
            details[c] = d
        if len(details) >= N:
            break
    codes = list(details)
    check("örnek kitaplar", len(codes) >= min(N, 5), f"{len(codes)} kitap")
    inlist = ", ".join(q(c) for c in codes)

    # R1 Logo bakiye.
    ref = {str(r["kod"]).strip(): float(r["bakiye"] or 0) for r in logo(
        f"SELECT i.CODE AS kod, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) AS bakiye "
        f"FROM dbo.LG_{cur}_01_STLINE l JOIN dbo.LG_{cur}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
        f"LEFT JOIN dbo.LG_{cur}_01_STFICHE f ON f.LOGICALREF = l.STFICHEREF "
        f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND NOT (l.TRCODE = 13 AND ISNULL(f.PRODSTAT, 0) = 1) "
        f"AND i.CODE IN ({inlist}) GROUP BY i.CODE")}
    bad = [c for c in codes if not near(details[c]["bakiye"], ref.get(c, 0.0))]
    check("R1 Logo bakiye birebir", not bad, f"{len(codes)} kitap; farklı: {[(c, details[c]['bakiye'], ref.get(c)) for c in bad[:5]]}")
    raw_cat = {str(r["kod"]).strip(): float(r["bakiye"] or 0) for r in logo(
        f"SELECT i.CODE AS kod, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) AS bakiye "
        f"FROM dbo.LG_{cur}_01_STLINE l JOIN dbo.LG_{cur}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
        f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND i.CODE IN ({inlist}) GROUP BY i.CODE")}
    diff_planned = {c: raw_cat.get(c, 0) - ref.get(c, 0) for c in codes if abs(raw_cat.get(c, 0) - ref.get(c, 0)) > 0.001}
    print(f"ÖLÇÜM planlanan üretim girişinin (PRODSTAT 1) katalog bakiyesine etkisi: {len(diff_planned)}/{len(codes)} kitapta, {diff_planned}", flush=True)

    # R2 ambar kırılımı.
    wh: dict[str, dict[int, float]] = {}
    for r in logo(f"SELECT i.CODE AS kod, l.SOURCEINDEX AS ambar, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) AS bakiye "
                  f"FROM dbo.LG_{cur}_01_STLINE l JOIN dbo.LG_{cur}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
                  f"LEFT JOIN dbo.LG_{cur}_01_STFICHE f ON f.LOGICALREF = l.STFICHEREF "
                  f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND NOT (l.TRCODE = 13 AND ISNULL(f.PRODSTAT, 0) = 1) "
                  f"AND i.CODE IN ({inlist}) GROUP BY i.CODE, l.SOURCEINDEX"):
        wh.setdefault(str(r["kod"]).strip(), {})[int(r["ambar"])] = float(r["bakiye"] or 0)
    bad = []
    for c in codes:
        api = {x["no"]: x["adet"] for x in details[c]["ambarlar"]}
        sql = {k: v for k, v in wh.get(c, {}).items() if abs(v) >= 0.5}
        if set(api) != set(sql) or any(not near(api[k], sql[k]) for k in api) or not near(sum(wh.get(c, {}).values()), ref.get(c, 0)):
            bad.append(c)
    check("R2 ambar kırılımı ve toplamı", not bad, f"farklı: {bad[:5]}")

    # R3 satış hızı = Baskı Öneri raporu (aynı SQL dosyası).
    s, rep = http("GET", BASE + "/api/v1/management/reports/baski-oneri")
    views = {v["id"]: v for v in ((rep.get("data") or {}).get("views") or [])} if s == 200 else {}
    t = views.get("tekrar")
    if t:
        keys = [c["key"] for c in t["columns"]]
        ki, kh = keys.index("stok_kodu"), keys.index("ort_satis_hizi")
        rows = {str(r[ki]).strip(): r[kh] for r in t["rows"]}
        pick = rnd.sample([c for c in rows if c in set(codes_all)], min(N, len(rows)))
        bad = []
        for c in pick:
            s2, d = http("GET", f"{P}/items/{urllib.request.quote(c)}")
            if s2 != 200 or not near(d["satisHizi"], rows[c], 1e-6):
                bad.append((c, d.get("satisHizi") if s2 == 200 else s2, rows[c]))
        check("R3 satış hızı = Baskı Öneri", bool(pick) and not bad, f"{len(pick)} kitap; farklı: {bad[:5]}")
    else:
        check("R3 satış hızı = Baskı Öneri", False, f"Baskı Öneri raporu okunamadı ({s}); DOĞRULANAMADI")

    # R4 devir hızı (sertifikalı ifade).
    dv = {str(r["kod"]).strip(): r["devir"] for r in logo(
        f"SELECT i.CODE AS kod, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.AMOUNT END) / NULLIF((SUM(CASE WHEN l.TRCODE = 14 THEN l.AMOUNT END) "
        f"+ SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT WHEN l.IOCODE IN (3,4) THEN -l.AMOUNT END)) / 2.0, 0) AS devir "
        f"FROM dbo.LG_{cur}_01_STLINE l JOIN dbo.LG_{cur}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
        f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND i.CODE IN ({inlist}) GROUP BY i.CODE")}
    bad = [c for c in codes if not near(details[c]["devirHizi"], None if dv.get(c) is None else float(dv[c]), 1e-6)]
    check("R4 stok devir hızı birebir", not bad, f"farklı: {[(c, details[c]['devirHizi'], dv.get(c)) for c in bad[:5]]}")
    iyi = logo(f"SELECT TOP 1 CODE AS kod FROM dbo.LG_{cur}_ITEMS WHERE NAME LIKE N'%İYİLİK TİMİ%'")
    if iyi:
        k = str(iyi[0]["kod"]).strip()
        s2, d = http("GET", f"{P}/items/{urllib.request.quote(k)}")
        print(f"ÖLÇÜM İYİLİK TİMİ ({k}) devir hızı ekranda {d.get('devirHizi') if s2 == 200 else s2} (bilinen referans 1,09)", flush=True)

    # R5 aktarım hatası sayısı.
    r5 = crm("SELECT SUM(CASE WHEN new_logomesaji IS NOT NULL THEN 1 ELSE 0 END) AS hata, "
             "SUM(CASE WHEN new_logomesaji IS NULL THEN 1 ELSE 0 END) AS bekliyor FROM Timas_MSCRM.dbo.new_malzemehareketiBase "
             "WHERE new_logoyaaktarildi = 0 AND statecode = 0")[0]
    s, te = http("GET", P + "/transfer-errors?tur=")
    check("R5 aktarım hatası ve bekleyen sayısı", s == 200 and te["hata"] == int(r5["hata"] or 0) and te["bekliyor"] == int(r5["bekliyor"] or 0),
          f"ekran {te.get('hata') if s == 200 else s}/{te.get('bekliyor') if s == 200 else ''} · SQL {r5['hata']}/{r5['bekliyor']}")

    # R6 CRM raf stoğu.
    raf = {str(r["kod"]).strip(): float(r["raf"] or 0) for r in crm(
        "SELECT p.ProductNumber AS kod, SUM(s.new_kalanmiktar) AS raf FROM Timas_MSCRM.dbo.new_serilothareketsatiriBase s "
        "JOIN Timas_MSCRM.dbo.new_malzemehareketsatiriBase m ON m.new_malzemehareketsatiriId = s.new_malzemehareketsatiriid "
        "JOIN Timas_MSCRM.dbo.ProductBase p ON p.ProductId = m.new_urunid "
        f"WHERE s.statecode = 0 AND p.ProductNumber IN ({inlist}) GROUP BY p.ProductNumber")}
    bad = [c for c in codes if not near(details[c]["crmRaf"] or 0.0, raf.get(c, 0.0))]
    check("R6 CRM raf stoğu birebir", not bad, f"farklı: {[(c, details[c]['crmRaf'], raf.get(c)) for c in bad[:5]]}")

    # R7 hareketsiz stok kümesi.
    win = details[codes[0]].get("hareketPenceresi") if codes else None
    olu = pages("/excess?tur=olu")
    if win and olu is not None:
        bas, bit = date.fromisoformat(win[0]), date.fromisoformat(win[1]) + timedelta(days=1)
        bak = {str(r["kod"]).strip(): float(r["bakiye"] or 0) for r in logo(
            f"SELECT i.CODE AS kod, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) AS bakiye "
            f"FROM dbo.LG_{cur}_01_STLINE l JOIN dbo.LG_{cur}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
            f"LEFT JOIN dbo.LG_{cur}_01_STFICHE f ON f.LOGICALREF = l.STFICHEREF "
            f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND NOT (l.TRCODE = 13 AND ISNULL(f.PRODSTAT, 0) = 1) "
            f"GROUP BY i.CODE")}
        moved: set[str] = set()
        for y in range(bas.year, bit.year + 1):
            f = firms.get(y)
            if not f:
                continue
            aa, bb = max(bas, date(y, 1, 1)), min(bit, date(y + 1, 1, 1))
            moved |= {str(r["kod"]).strip() for r in logo(
                f"SELECT DISTINCT i.CODE AS kod FROM dbo.LG_{f}_01_STLINE l JOIN dbo.LG_{f}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
                f"LEFT JOIN dbo.LG_{f}_01_STFICHE fs ON fs.LOGICALREF = l.STFICHEREF "
                f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.TRCODE <> 14 AND NOT (l.TRCODE = 13 AND ISNULL(fs.PRODSTAT, 0) = 1) "
                f"AND l.DATE_ >= '{aa.isoformat()}' AND l.DATE_ < '{bb.isoformat()}'")}
        ref_dead = {c for c, v in bak.items() if v > 0 and c not in moved and not c.startswith("157")}
        api_dead = {x["stokKodu"] for x in olu}
        check("R7 hareketsiz stok kümesi", api_dead == ref_dead,
              f"ekran {len(api_dead)} / SQL {len(ref_dead)}; yalnız ekranda {sorted(api_dead - ref_dead)[:5]}, yalnız SQL'de {sorted(ref_dead - api_dead)[:5]}")
    else:
        check("R7 hareketsiz stok kümesi", False, "pencere ya da liste okunamadı; DOĞRULANAMADI")

    # R8 Logo bekleyen sipariş.
    ob = {str(r["kod"]).strip(): float(r["bekleyen"] or 0) for r in logo(
        f"SELECT i.CODE AS kod, SUM(o.AMOUNT - o.SHIPPEDAMOUNT) AS bekleyen FROM dbo.LG_{cur}_01_ORFLINE o "
        f"JOIN dbo.LG_{cur}_ITEMS i ON i.LOGICALREF = o.STOCKREF WHERE o.TRCODE = 1 AND o.CLOSED = 0 AND o.CANCELLED = 0 "
        f"AND o.LINETYPE = 0 AND i.CODE IN ({inlist}) GROUP BY i.CODE")}
    bad = [c for c in codes if not near(details[c]["bekleyenLogo"], ob.get(c))]
    check("R8 Logo bekleyen sipariş", not bad, f"farklı: {[(c, details[c]['bekleyenLogo'], ob.get(c)) for c in bad[:5]]}")

    # R9 CRM bekleyen ürün.
    bu = {str(r["kod"]).strip(): float(r["adet"] or 0) for r in crm(
        "SELECT p.ProductNumber AS kod, SUM(b.new_adet) AS adet FROM Timas_MSCRM.dbo.new_bekleyenurunBase b "
        "JOIN Timas_MSCRM.dbo.ProductBase p ON p.ProductId = b.new_urunid WHERE b.statecode = 0 AND b.statuscode = 1 "
        f"AND p.ProductNumber IN ({inlist}) GROUP BY p.ProductNumber")}
    bad = [c for c in codes if not near(details[c]["bekleyenUrun"], bu.get(c))]
    check("R9 CRM bekleyen ürün", not bad, f"farklı: {[(c, details[c]['bekleyenUrun'], bu.get(c)) for c in bad[:5]]}")

    # R10 depo hattı aşama sayıları.
    st = {int(r["durum"]): int(r["adet"]) for r in crm(
        "SELECT CAST(statuscode AS int) AS durum, COUNT(*) AS adet FROM Timas_MSCRM.dbo.new_siparisBase WHERE statecode = 0 "
        "AND statuscode IN (100000011, 100000012, 100000013, 100000014) GROUP BY statuscode")}
    s, pl = http("GET", P + "/pick-line")
    keymap = {"depoda": 100000011, "toplaniyor": 100000012, "kutulaniyor": 100000013, "kutulandi": 100000014}
    got = {keymap[x["key"]]: x["adet"] for x in pl["asamalar"]} if s == 200 else {}
    check("R10 depo hattı aşama sayıları", s == 200 and all(got.get(k, 0) == st.get(k, 0) for k in keymap.values()), f"ekran {got} · SQL {st}")

    # R11 bitecekler: boşsa kaynaklar ayrı ayrı sorgulanır (bellek: boş cevap ayrıca sorgulanır).
    s, ro = http("GET", P + "/running-out")
    if s == 200 and ro["total"] == 0:
        hiz = sum(1 for c in codes if (details[c]["satisHizi"] or 0) > 0)
        check("R11 bitecek listesi boş — kaynak kontrolü", False, f"örnekte satış hızı > 0 olan {hiz}, bakiye okunan {len(ref)}; incelenmeli")
    else:
        check("R11 bitecek listesi dolu ve sıralı", s == 200 and all((ro["items"][i]["gun"] or 0) <= (ro["items"][i + 1]["gun"] or 0)
                                                                   for i in range(len(ro["items"]) - 1)), f"{ro.get('total') if s == 200 else s} kitap")

    # Yazma: bir taslak eşik ve bir not (kimlikleri kaydedilir, cleanup.py siler).
    c0 = codes[0]
    s, t = http("POST", P + "/thresholds", {"stokKodu": c0, "guvenlikGun": 15, "gerekce": "M43 kabul — silinecek"})
    if s == 201:
        created["thresholds"].append(t["id"])
    check("taslak eşik yazıldı", s == 201 and t["durum"] == "taslak", str(s))
    s, n = http("POST", f"{P}/items/{urllib.request.quote(c0)}/notes", {"not": "M43 kabul — silinecek"})
    if s == 201:
        created["notes"].append(n["id"])
    check("not yazıldı", s == 201, str(s))
    s, x = http("GET", P + "/export/bitecekler.xlsx")
    check("Excel indi", s == 200 and isinstance(x, (bytes, bytearray)) and x[:2] == b"PK", str(s))
    s, it = http("GET", f"{P}/items/{urllib.request.quote(c0)}")
    check("ekranda teknoloji adı yok", s == 200 and not any(w in json.dumps(it, ensure_ascii=False).lower() for w in ("qwen", "vllm", "llm", "power bi")),
          "kitap kartı JSON'unda arandı")
    return finish(a.out, created)


def finish(out: str, created: dict) -> int:
    with open(out, "w") as f:
        json.dump(created, f)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok} geçti, {len(results) - ok} kaldı. Kimlikler: {out}", flush=True)
    for name, good, detail in results:
        if not good:
            print(f"   KALDI {name}: {detail}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
