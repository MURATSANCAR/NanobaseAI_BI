"""M42 Platform ve kanallar — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, kanal paketinin SQL'i kullanılmadan yazılmış doğrudan Logo/CRM sorgularıyla
karşılaştırılır (`referans.sql` R1–R8). Yazma yok: yalnız geçersiz gövdeli istekler (400/404) denenir; «Veriyi yenile»
ve Excel indirme değişiklik kaydına satır yazar, `temizlik.py` onları siler.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturumu — marj yetkisi için yönetici),
SEMANTIC_CONNECTION_FILE (Logo), SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M42_KOD
(e-ticaret kanal kodu, varsayılan E-TICARET), M42_KITAP (R8 kitap sayısı, 10), M42_YENILEME=0 (okumayı atla).
Kullanım: python kabul.py --out /tmp/claude-m42/kabul.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/channels"
KOD = os.environ.get("M42_KOD", "E-TICARET")
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
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


def near(a, b, tol=0.01) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)

    # 0. Okuma (gerçek Logo + CRM), sonra geçersiz istekler.
    if os.environ.get("M42_YENILEME", "1") != "0":
        s, st = http("POST", P + "/refresh")
        check("yenileme başladı", s == 200, str(s))
        t0 = time.time()
        while time.time() - t0 < 3600:
            time.sleep(10)
            s, st = http("GET", P + "/status")
            if s == 200 and not st.get("running"):
                break
        check("okuma bitti, hata yok", s == 200 and not st.get("running") and not st.get("error"), str(st.get("error"))[:200])
        print(f"   okuma: {json.dumps(st.get('years'), ensure_ascii=False)[:400]}")
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    if s != 200:
        return finish(a.out, started)
    check("marj yetkisi (kabul oturumu)", meta["me"]["canMargin"] is True, "COOKIE yönetici olmalı")
    end = date.fromisoformat(meta["data"]["dataEnd"])
    yil, ay = end.year, end.month
    ay_sonu = date(yil + (ay == 12), ay % 12 + 1, 1).isoformat()
    firm = firms[yil]
    print(f"   dönem {yil} Ocak–{ay}. ay (veri sonu {end}), firma {firm}, kanal kodu {KOD}")
    s, _ = http("PUT", P + "/accounts/YOK-BOYLE-CARI-M42", {})
    check("olmayan cari eşlemesi 400", s == 400, str(s))
    s, _ = http("POST", P + "/simulate", {})
    check("platformsuz simülasyon 404", s == 404, str(s))
    s, _ = http("POST", P + f"/imports?platform=hepsiburada&filename=bos.csv", b"")
    check("boş panel dosyası 400", s == 400, str(s))
    s, _ = http("GET", P + f"/scorecard?yil={yil + 5}")
    check("gelecek yıl 400", s == 400, str(s))

    s, card = http("GET", P + f"/scorecard?yil={yil}&ay={ay}")
    check("karne 200", s == 200, str(s))
    if s != 200:
        return finish(a.out, started)
    s, accs = http("GET", P + "/accounts")
    acc = {x["cariKodu"]: x for x in accs["items"]}
    s, kk = http("GET", P + "/accounts/kanal-kodlari")
    kmap = {x["kod"]: x["platform"] for x in kk["items"] if x.get("platform")}

    # R1 · E-ticaret kanal net cirosu ay ay (yıl içi toplamların farkı) = doğrudan SQL.
    sql_m = {int(r["ay"]): float(r["net"] or 0) for r in logo(
        f"SELECT MONTH(l.DATE_) AS ay, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net "
        f"FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
        f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = {q(KOD)} "
        f"AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}' GROUP BY MONTH(l.DATE_)")}
    prev = 0.0
    bad = []
    for m in range(1, ay + 1):
        s, c = http("GET", P + f"/scorecard?yil={yil}&ay={m}")
        row = next((k for k in c.get("kanallar", []) if k["kanal"] == KOD), None) if s == 200 else None
        ytd = row["donem"]["netCiro"] if row else 0.0
        if not near(ytd - prev, sql_m.get(m, 0.0)):
            bad.append(f"{m}: ekran {ytd - prev:.2f} / SQL {sql_m.get(m, 0.0):.2f}")
        prev = ytd
    check("R1 e-ticaret net ciro ay ay birebir (kuruş)", not bad, "; ".join(bad[:4]) or f"{ay} ay, toplam {prev:,.2f}")
    head = logo(f"SELECT SUM(CASE WHEN i.TRCODE IN (7,8,9) THEN i.NETTOTAL ELSE -i.NETTOTAL END) AS net "
                f"FROM dbo.LG_{firm}_01_INVOICE i JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = i.CLIENTREF "
                f"WHERE i.CANCELLED = 0 AND i.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = {q(KOD)} "
                f"AND i.DATE_ >= '{yil}-01-01' AND i.DATE_ < '{ay_sonu}'")[0]["net"] or 0
    print(f"   bilgi: başlık NETTOTAL {float(head):,.2f} / satır LINENET {prev:,.2f} (fark %{(float(head) / prev - 1) * 100 if prev else 0:.2f})")

    # R3 · İade ve iskonto oranı.
    r3 = logo(f"SELECT SUM(CASE WHEN l.LINETYPE = 0 AND l.TRCODE IN (2,3) THEN l.LINENET ELSE 0 END) AS iade, "
              f"SUM(CASE WHEN l.LINETYPE = 0 AND l.TRCODE IN (7,8,9) THEN l.LINENET ELSE 0 END) AS satis, "
              f"SUM(CASE WHEN l.LINETYPE = 2 AND l.TRCODE IN (7,8,9) THEN l.TOTAL ELSE 0 END) AS iskonto, "
              f"SUM(CASE WHEN l.LINETYPE = 0 AND l.TRCODE IN (7,8,9) THEN l.TOTAL ELSE 0 END) AS brut "
              f"FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
              f"WHERE l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.LINETYPE IN (0,2) AND l.TRCODE IN (2,3,7,8,9) "
              f"AND c.SPECODE2 = {q(KOD)} AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}'")[0]
    krow = next((k for k in card["kanallar"] if k["kanal"] == KOD), None)
    iade_sql = float(r3["iade"] or 0) / float(r3["satis"] or 1)
    isk_sql = float(r3["iskonto"] or 0) / float(r3["brut"] or 1)
    check("R3 iade oranı (satır) birebir", krow is not None and near(krow["donem"]["iadeOrani"], iade_sql, 1e-9),
          f"ekran {krow and krow['donem']['iadeOrani']} / SQL {iade_sql}")
    check("R3 iskonto oranı birebir", krow is not None and near(krow["donem"]["iskontoOrani"], isk_sql, 1e-9),
          f"ekran {krow and krow['donem']['iskontoOrani']} / SQL {isk_sql}")

    # R2 + R4 · Cari bazında net ciro, brüt kâr, maliyetsiz satır (kanal detayındaki Cariler tablosu).
    r2 = {str(r["cari"]).strip(): r for r in logo(
        f"SELECT c.CODE AS cari, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net, "
        f"SUM(CASE WHEN l.TRCODE IN (7,8,9) AND ISNULL(l.OUTCOST,0) > 0 THEN l.LINENET - l.AMOUNT * l.OUTCOST ELSE 0 END) AS brut_kar, "
        f"SUM(CASE WHEN l.TRCODE IN (7,8,9) AND ISNULL(l.OUTCOST,0) <= 0 THEN 1 ELSE 0 END) AS maliyetsiz_satir "
        f"FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
        f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = {q(KOD)} "
        f"AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}' GROUP BY c.CODE")}
    screen: dict[str, dict] = {}
    per_platform: dict[str, list] = {}
    for pc in card["platforms"]:
        s, ch = http("GET", P + f"/channel/{pc['platform']}?yil={yil}&ay={ay}")
        if s != 200:
            check(f"kanal detayı {pc['platform']}", False, str(s))
            continue
        per_platform[pc["platform"]] = ch["cariler"]
        for c in ch["cariler"]:
            screen[c["grup"]] = c["donem"]
        # R7 · Platform toplamı = carilerinin toplamı (fark 0).
        tot = sum(c["donem"]["netCiro"] for c in ch["cariler"])
        check(f"R7 {pc['label']}: platform = carilerinin toplamı", near(tot, pc["donem"]["netCiro"]),
              f"kart {pc['donem']['netCiro']:,.2f} / cariler {tot:,.2f}")
    if KOD in kmap:
        print(f"   bilgi: {KOD} kanal koduyla {kmap[KOD]} platformuna bağlı; cari bazında satır yok, R2/R4 atlandı")
    else:
        miss, diff_n, diff_k, diff_s = [], [], [], []
        for code, r in r2.items():
            net = float(r["net"] or 0)
            if acc.get(code, {}).get("platform") == "degil":
                continue
            sc = screen.get(code)
            if sc is None:
                if abs(net) > 0.005:
                    miss.append(code)
                continue
            if not near(sc["netCiro"], net):
                diff_n.append(f"{code} {sc['netCiro']:.2f}/{net:.2f}")
            if not near(sc.get("brutKar"), float(r["brut_kar"] or 0)):
                diff_k.append(f"{code} {sc.get('brutKar')}/{float(r['brut_kar'] or 0):.2f}")
            if int(sc.get("maliyetsizSatir", -1)) != int(r["maliyetsiz_satir"] or 0):
                diff_s.append(f"{code} {sc.get('maliyetsizSatir')}/{r['maliyetsiz_satir']}")
        check(f"R2 {len(r2)} carinin net cirosu birebir", not diff_n and not miss, "; ".join((diff_n + [f'ekranda yok: {m}' for m in miss])[:5]))
        check("R4 brüt kâr (maliyetli satırlar) birebir", not diff_k, "; ".join(diff_k[:5]))
        check("R4 maliyetsiz satır sayısı birebir", not diff_s, "; ".join(diff_s[:5]))
        # R7 · SQL tarafı: eşlenmiş (kanal kodundaki) carilerin toplamı = platform kartı.
        for pc in card["platforms"]:
            if pc["platform"] == "eslenmemis":
                codes = [c for c in r2 if acc.get(c, {}).get("durum") != "onayli"]
            else:
                codes = [c for c, v in acc.items() if v.get("durum") == "onayli" and v.get("platform") == pc["platform"]]
            groups = {c["grup"] for c in per_platform.get(pc["platform"], [])}
            outside = [g for g in groups if not g.startswith("#K:") and g not in r2 and abs(screen.get(g, {}).get("netCiro", 0)) > 0.005]
            if any(g.startswith("#K:") for g in groups) or outside:
                print(f"   bilgi: {pc['label']} kanal kodu ya da kod dışı cari içeriyor; SQL tarafı R7 atlandı")
                continue
            sql_tot = sum(float(r2[c]["net"] or 0) for c in codes if c in r2)
            check(f"R7 {pc['label']}: eşlenmiş carilerin SQL toplamı = kart", near(sql_tot, pc["donem"]["netCiro"]),
                  f"kart {pc['donem']['netCiro']:,.2f} / SQL {sql_tot:,.2f}")

    # R5 · CRM satış hedefi (bölge × yıl).
    code_rows = crm(f"SELECT DISTINCT sm.AttributeValue AS kod FROM {SCHEMA}.StringMap sm WHERE sm.AttributeName = 'new_yil' "
                    f"AND sm.Value = '{yil}' AND sm.AttributeValue IN (SELECT DISTINCT new_yil FROM {SCHEMA}.new_satishedefleriBase)")
    if len(code_rows) != 1:
        check("R5 CRM hedef yılı kodu tek", False, f"{len(code_rows)} kod: {code_rows}")
    else:
        yk = int(code_rows[0]["kod"])
        ref = {str(r["bolge"]): r for r in crm(
            f"SELECT new_bolge AS bolge, SUM(ISNULL(new_ocak,0)+ISNULL(new_subat,0)+ISNULL(new_Mart,0)+ISNULL(new_Nisan,0)+ISNULL(new_mayis,0)"
            f"+ISNULL(new_Haziran,0)+ISNULL(new_Temmuz,0)+ISNULL(new_agustos,0)+ISNULL(new_eylul,0)+ISNULL(new_Ekim,0)+ISNULL(new_kasim,0)"
            f"+ISNULL(new_aralik,0)) AS aylik_toplam, SUM(ISNULL(new_ToplamHedef,0)) AS toplam "
            f"FROM {SCHEMA}.new_satishedefleriBase WHERE statecode = 0 AND new_yil = {yk} GROUP BY new_bolge") if r["bolge"] is not None}
        s, reg = http("GET", P + f"/accounts/bolgeler?yil={yil}")
        got = {x["kod"]: x for x in reg.get("items", []) if x.get("yil") == yil}
        bad = [f"{k}: {got.get(k, {}).get('aylikToplam')}/{float(v['aylik_toplam'] or 0)}" for k, v in ref.items()
               if not near(got.get(k, {}).get("aylikToplam"), float(v["aylik_toplam"] or 0))]
        bad += [f"{k} toplam: {got.get(k, {}).get('yillik')}/{float(v['toplam'] or 0)}" for k, v in ref.items()
                if not near(got.get(k, {}).get("yillik"), float(v["toplam"] or 0))]
        check(f"R5 {len(ref)} bölgenin 12 ay toplamı ve ToplamHedef birebir", not bad and set(ref) == set(got), "; ".join(bad[:4]))
        gap = sum(1 for v in ref.values() if not near(v["aylik_toplam"], v["toplam"]))
        print(f"   bilgi: 12 ay toplamı ≠ ToplamHedef olan bölge {gap}")

    # R6 · CRM sipariş tipi sayıları (son 180 gün; okumadan hemen sonra).
    days = int((meta.get("crmOrders") or {}).get("days") or 180)
    ref6 = {str(r["tip"]): int(r["sayi"]) for r in crm(
        f"SELECT new_siparistipi AS tip, COUNT(*) AS sayi FROM {SCHEMA}.new_siparisBase WHERE statecode = 0 "
        f"AND new_siparistarihi >= DATEADD(DAY, -{days}, GETDATE()) GROUP BY new_siparistipi") if r["tip"] is not None}
    got6 = {k: v for k, v in ((meta.get("crmOrders") or {}).get("byType") or {}).items() if k != "bos"}
    diff6 = {k: (got6.get(k), v) for k, v in ref6.items() if got6.get(k) != v}
    check("R6 CRM sipariş tipi sayıları (Pazaryeri 9, Amazon konsinye 14, B2C 8 …)", not diff6,
          f"fark {diff6} (okuma ile sorgu arasındaki yeni sipariş kadar olabilir)" if diff6 else json.dumps(ref6))

    # R8 · Kitap × kanal: rastgele kitaplarda satır toplamı = doğrudan SQL (aynı kapsam: kanal kodları + eşlenmiş cariler).
    s, mx = http("GET", P + f"/matrix?yil={yil}&ay={ay}")
    n = int(os.environ.get("M42_KITAP", "10"))
    rows = random.sample(mx["items"], min(n, len(mx["items"]))) if s == 200 and mx["items"] else []
    specs = [KOD] + [k for k, v in kmap.items() if v != "degil" and k != KOD]
    mapped = [c for c, v in acc.items() if v.get("durum") == "onayli" and v.get("platform") not in (None, "degil")]
    degil = {c for c, v in acc.items() if v.get("durum") == "onayli" and v.get("platform") == "degil"}
    if rows:
        cond = f"c.SPECODE2 IN ({', '.join(q(x) for x in specs)})" + (f" OR c.CODE IN ({', '.join(q(x) for x in mapped)})" if mapped else "")
        ref8: dict[str, float] = {}
        for r in logo(f"SELECT i.CODE AS stok, c.CODE AS cari, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.AMOUNT ELSE -l.AMOUNT END) AS net_adet "
                      f"FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = l.CLIENTREF "
                      f"JOIN dbo.LG_{firm}_ITEMS i ON i.LOGICALREF = l.STOCKREF "
                      f"WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND ({cond}) "
                      f"AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}' AND i.CODE IN ({', '.join(q(x['stokKodu']) for x in rows)}) "
                      f"GROUP BY i.CODE, c.CODE"):
            if str(r["cari"]).strip() in degil:
                continue
            ref8[str(r["stok"]).strip()] = ref8.get(str(r["stok"]).strip(), 0.0) + float(r["net_adet"] or 0)
        bad = [f"{x['stokKodu']} {x['toplam']}/{ref8.get(x['stokKodu'], 0.0)}" for x in rows if not near(x["toplam"], ref8.get(x["stokKodu"], 0.0))]
        check(f"R8 {len(rows)} kitabın kanal toplamı birebir", not bad, "; ".join(bad[:4]))
    else:
        check("R8 matriste kitap var", False, str(s))

    # Simülasyon ve dışa aktarım (yazmaz; Excel değişiklik kaydına satır bırakır).
    top = next((p for p in card["platforms"] if p["platform"] != "eslenmemis" and p["donem"]["brutSatis"] > 0), None)
    if top:
        s, sim = http("POST", P + "/simulate", {"platform": top["platform"], "yil": yil, "ay": ay, "iskontoPuan": 2})
        ok = s == 200 and near(sim["sonra"]["netSatis"], sim["once"]["netSatis"] - sim["once"]["brutSatis"] * 0.02)
        check(f"simülasyon {top['label']} +2 puan", ok, f"marj {sim.get('once', {}).get('marj')} → {sim.get('sonra', {}).get('marj')}" if s == 200 else str(s))
    s, x = http("GET", P + f"/export/karne.xlsx?yil={yil}&ay={ay}", raw=True)
    check("karne Excel", s == 200 and x[:2] == b"PK", str(s))
    return finish(a.out, started)


def finish(out_path: str, started: str) -> int:
    with open(out_path, "w") as fh:
        json.dump({"since": started, "results": [{"ad": n, "gecti": ok, "ayrinti": d} for n, ok, d in results]}, fh, ensure_ascii=False)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; değişiklik kaydı satırları için: temizlik.py --since {started}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
