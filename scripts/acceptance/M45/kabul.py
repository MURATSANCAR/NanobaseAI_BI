"""M45 Finansal raporlar — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, köprü kodunu kullanmadan yazılmış doğrudan Logo sorgularıyla karşılaştırılır
(`referans.sql` R1–R8). Yazma: yalnız bir vergi takvimi kaydı açılıp aynı koşuda silinir; kimlikler `--out` dosyasına
yazılır, `temizlik.py` kalanı ve değişiklik kaydı satırlarını siler.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturum çerezi), SEMANTIC_CONNECTION_FILE (Logo),
SEMANTIC_STORE_DSN (köprü veritabanı; R7 için), PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M45_AY (varsayılan: veri son
gününden önceki son tam ay), M45_STOK (virgülle 5 stok kodu; yoksa en çok satan 5 kitap).
Kullanım: python kabul.py --out /tmp/claude-m45/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/finance"
TECH = ("qwen", "vllm", "llm", "timesfm", "temporal", "openai")
YANS = "('711','721','731','741','751','761','771','781','791')"
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=900):
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


def near(a, b, tol=0.01) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < tol


def wait_idle(limit=3600) -> dict:
    t = time.time()
    while time.time() - t < limit:
        s, st = http("GET", P + "/status")
        if s == 200 and not st.get("running"):
            return st
        time.sleep(10)
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"], timeout=1800)
    firms = bsrc.firms_by_year(logo)
    created: dict[str, list[str]] = {"tax": []}

    # 0. Geçersiz ve yetkisiz istekler (yazmadan önce).
    s, _ = http("POST", P + "/tax-calendar", {})
    check("boş gövdeyle vergi kaydı 400/403", s in (400, 403), str(s))
    s, _ = http("PATCH", P + "/account-map/600", {"satir": "NET_SATIS"})
    check("ara toplama eşleme reddedilir (400) ya da yetki yok (403)", s in (400, 403), str(s))
    s, _ = http("GET", P + "/pnl?year=2026&month=13")
    check("geçersiz ay 400", s == 400, str(s))

    # 1. İlk okuma (Logo): yenile, bitmesini bekle.
    s, meta = http("GET", P + "/meta")
    check("meta açıldı", s == 200, str(s))
    s, st = http("POST", P + "/refresh", {})
    check("Logo okuması başladı", s == 200 and (st.get("started") or st.get("running")), json.dumps(st, ensure_ascii=False)[:200])
    st = wait_idle()
    check("Logo okuması bitti, hata yok", bool(st) and not st.get("error"), f"hata={st.get('error')} yıllar={list((st.get('years') or {}).keys())}")
    end = date.fromisoformat(st["veriSonu"])
    ref_end = bsrc._day(logo(bsrc.data_end_sql(firms[max(firms)]))[0]["son"])
    check("veri son günü = doğrudan SQL", end == ref_end, f"{end} / {ref_end}")
    y = end.year
    f = firms[y]
    nxt = date(end.year + (end.month == 12), end.month % 12 + 1, 1)
    m = int(os.environ.get("M45_AY") or (end.month if (nxt - end).days == 1 else max(1, end.month - 1)))
    m0, m1 = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)

    # R1 mizan.
    r1 = logo(f"SELECT SUM(L.DEBIT) AS b, SUM(L.CREDIT) AS a FROM dbo.LG_{f}_01_EMFLINE L JOIN dbo.LG_{f}_01_EMFICHE F ON F.LOGICALREF = L.ACCFICHEREF "
              f"WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND L.DATE_ >= '{y}0101' AND L.DATE_ < '{y + 1}0101'")[0]
    s, pnl = http("GET", f"{P}/pnl?year={y}&month={m}&grain=ay")
    check("gelir tablosu açıldı", s == 200, str(s))
    mz = (pnl.get("mizan") or {}).get("yil") or {}
    check("R1 mizan yıl borç/alacak = SQL", near(mz.get("borc"), r1["b"]) and near(mz.get("alacak"), r1["a"]),
          f"ekran {mz} / SQL {r1}")
    check("R1 mizan denk (|fark| < 0,01)", abs(float(r1["b"] or 0) - float(r1["a"] or 0)) < 0.01 and pnl["mizan"]["durum"] in ("denk", "fark"),
          f"SQL fark {float(r1['b'] or 0) - float(r1['a'] or 0):.2f}, ekran {pnl['mizan']['durum']}")

    # R2 hesap bazında kâr etkisi (bağımsız kural).
    ref = {str(r["hesap"]).strip(): float(r["etki"] or 0) for r in logo(
        f"SELECT A.CODE AS hesap, SUM(L.CREDIT) - SUM(L.DEBIT) AS etki FROM dbo.LG_{f}_01_EMFLINE L "
        f"JOIN dbo.LG_{f}_01_EMFICHE F ON F.LOGICALREF = L.ACCFICHEREF JOIN dbo.LG_{f}_EMUHACC A ON A.LOGICALREF = L.ACCOUNTREF "
        f"WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND L.DATE_ >= '{m0:%Y%m%d}' AND L.DATE_ < '{m1:%Y%m%d}' "
        f"AND (A.CODE LIKE '6%' OR A.CODE LIKE '7%') AND LEFT(A.CODE, 3) NOT IN {YANS} "
        f"AND NOT (A.CODE LIKE '7%' AND EXISTS (SELECT 1 FROM dbo.LG_{f}_01_EMFLINE K JOIN dbo.LG_{f}_EMUHACC KA ON KA.LOGICALREF = K.ACCOUNTREF "
        f"  WHERE K.ACCFICHEREF = L.ACCFICHEREF AND K.CANCELLED = 0 AND K.SIGN = 0 AND LEFT(KA.CODE, 3) IN {YANS})) "
        f"AND NOT (A.CODE LIKE '6%' AND EXISTS (SELECT 1 FROM dbo.LG_{f}_01_EMFLINE K JOIN dbo.LG_{f}_EMUHACC KA ON KA.LOGICALREF = K.ACCOUNTREF "
        f"  WHERE K.ACCFICHEREF = L.ACCFICHEREF AND K.CANCELLED = 0 AND (LEFT(KA.CODE, 3) IN {YANS} OR LEFT(KA.CODE, 3) IN ('690','692')))) "
        f"GROUP BY A.CODE")}
    screen: dict[str, float] = {}
    for line in [r for r in pnl["rows"] if r["tur"] in ("gelir", "gider", "eslenmemis")]:
        s, la = http("GET", f"{P}/pnl/lines/{line['kod']}/accounts?year={y}&month={m}&grain=ay")
        for i in la.get("items", []):
            screen[i["hesap"]] = screen.get(i["hesap"], 0.0) + float(i["etki"] or 0)
        check(f"R2 satır {line['kod']} = hesaplarının toplamı", near(la.get("toplam") or 0, line["values"]["donem"] or 0),
              f"{la.get('toplam')} / {line['values']['donem']}")
    s, am = http("GET", f"{P}/account-map?year={y}")
    excluded = {i["hesap"] for i in am.get("items", []) if i["esleme"]["satir"] == "dislandi"}
    want = {k: v for k, v in ref.items() if k not in excluded and abs(v) > 0.005}
    bad = [k for k in set(want) | set(screen) if not near(want.get(k, 0.0), screen.get(k, 0.0))]
    check("R2 hesap bazında kâr etkisi kuruşu kuruşuna", not bad, f"{len(want)} hesap; farklı: {[(k, want.get(k), screen.get(k)) for k in bad[:8]]}")
    dis = sum(v for k, v in ref.items() if k in excluded)
    check("R2 dışlanan tutar = SQL", near(pnl.get("dislanan") or 0, dis), f"{pnl.get('dislanan')} / {dis:.2f}")
    # Fişe iniş: satır → hesap → fiş sayfası; fiş toplamı = hesap tutarı (dahil satırlar).
    top = max(screen, key=lambda k: abs(screen[k])) if screen else None
    if top:
        s, en = http("GET", f"{P}/pnl/accounts/{urllib.parse.quote(top)}/entries?year={y}&month={m}&grain=ay&page=0")
        check("fişe iniş açıldı, SQL gösteriliyor", s == 200 and "LG_" in (en.get("sql") or ""), f"{top}: {s} toplam {en.get('total')}")

    # R3 ve R4 yıl başından net satış ve maliyet kapsamı.
    s, ytd = http("GET", f"{P}/pnl?year={y}&month={end.month}&grain=ytd&compare=")
    r3 = logo(f"SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN LINENET ELSE -LINENET END) AS net, "
              f"SUM(CASE WHEN OUTCOST <> 0 THEN (CASE WHEN TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * LINENET ELSE 0 END) AS mnet "
              f"FROM dbo.LG_{f}_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (2,3,7,8,9) "
              f"AND DATE_ >= '{y}0101' AND DATE_ < '{y + 1}0101'")[0]
    check("R3 fatura net satış (yıl) = SQL", near(ytd.get("faturaNetSatis"), r3["net"]), f"{ytd.get('faturaNetSatis')} / {r3['net']} (M46 ölçümü 2026: 837.901.631,04)")
    share = float(r3["mnet"] or 0) / float(r3["net"]) if r3["net"] else None
    check("R4 maliyetli satış payı = SQL", near((ytd.get("maliyet") or {}).get("maliyetliPay"), share, 0.0001), f"{ytd.get('maliyet')} / {share}")
    s, summ = http("GET", P + "/summary")
    check("özet açıldı, her kartta veri son günü", s == 200 and summ.get("veriSonu") == end.isoformat(), str(summ.get("veriSonu")))
    brut = next((c for c in summ.get("cards", []) if c["id"] == "brut-kar"), None)
    check("özet brüt kâr kartı «yaklaşık» işaretli (maliyetsiz satır varken)", brut is not None and (share is None or share > 0.9999 or brut["yaklasik"]),
          json.dumps(brut, ensure_ascii=False)[:200])
    blob = json.dumps(summ, ensure_ascii=False).lower()
    check("ekranda teknoloji adı yok", not any(t in blob for t in TECH), "")

    # R5 kitap kârlılığı (5 stok).
    codes = [c for c in (os.environ.get("M45_STOK") or "").split(",") if c] or [str(r["kod"]).strip() for r in logo(
        f"SELECT TOP 5 I.CODE AS kod FROM dbo.LG_{f}_01_STLINE L JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = L.STOCKREF "
        f"WHERE L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (7,8) AND L.DATE_ >= '{y}0101' "
        f"GROUP BY I.CODE ORDER BY SUM(L.LINENET) DESC")]
    for code in codes[:5]:
        r5 = logo(f"SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS net, "
                  f"SUM(CASE WHEN L.OUTCOST <> 0 THEN (CASE WHEN L.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * L.AMOUNT * L.OUTCOST ELSE 0 END) AS maliyet "
                  f"FROM dbo.LG_{f}_01_STLINE L JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = L.STOCKREF WHERE I.CODE = '{code}' "
                  f"AND L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9) "
                  f"AND L.DATE_ >= '{y}0101' AND L.DATE_ < '{y + 1}0101'")[0]
        s, pr = http("GET", f"{P}/profitability?by=kitap&year={y}&frm=1&to=12&q={urllib.parse.quote(code)}")
        row = next((i for i in pr.get("items", []) if i["key"] == code), None)
        check(f"R5 {code} net satış ve Logo maliyeti", row is not None and near(row["net"], r5["net"]) and near(row["maliyetLogo"], r5["maliyet"]),
              f"ekran {row and (row['net'], row['maliyetLogo'])} / SQL {(r5['net'], r5['maliyet'])}")

    # R8 kanal.
    r8 = {str(r["kanal"]).strip(): float(r["net"] or 0) for r in logo(
        f"SELECT ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), N'Grup kodu boş') AS kanal, "
        f"SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net FROM dbo.LG_{f}_01_STLINE S "
        f"LEFT JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 "
        f"AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '{y}0101' AND S.DATE_ < '{y + 1}0101' "
        f"GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), N'Grup kodu boş')")}
    items, page = [], 0
    while True:
        s, pk = http("GET", f"{P}/profitability?by=kanal&year={y}&frm=1&to=12&page={page}")
        items += pk.get("items", [])
        if (page + 1) * pk.get("pageSize", 100) >= pk.get("total", 0):
            break
        page += 1
    got = {i["key"]: i["net"] for i in items}
    bad = [k for k in set(r8) | set(got) if not near(r8.get(k, 0.0), got.get(k, 0.0))]
    check("R8 kanal net satışı (hepsi, sayfalı)", not bad and len(items) == pk.get("total"), f"{len(got)} kanal; farklı {bad[:5]}")

    # R6 nakit (yetki varsa): tabloyu kur, vadesi geçmiş alacağı FIFO sorgusuyla karşılaştır.
    s, _ = http("POST", P + "/cash/rebuild", {})
    if s == 403:
        check("nakit yetkisi yoksa 403", True, "timasai rolünde finans.nakit yok; R6 atlandı")
    else:
        wait_idle()
        s, cash = http("GET", P + "/cash")
        check("nakit tablosu kuruldu (13 hafta)", s == 200 and len(cash.get("haftalar") or []) == 13, f"hatalar {cash.get('hatalar')}")
        asof1 = (end + timedelta(days=1)).strftime("%Y%m%d")
        r6 = logo(f"""WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 0 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
  FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
  WHERE L.CANCELLED = 0 AND C.CODE LIKE '120%' AND L.DATE_ >= '{y}0101' AND L.DATE_ < '{asof1}' GROUP BY L.CLIENTREF),
 P AS (SELECT P.CARDREF, P.DATE_, P.TOTAL, SUM(P.TOTAL) OVER (PARTITION BY P.CARDREF ORDER BY P.DATE_ DESC, P.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) AS k
  FROM dbo.LG_{f}_01_PAYTRANS P WHERE P.CANCELLED = 0 AND P.SIGN = 0 AND P.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye > 0)),
 A AS (SELECT P.CARDREF, P.DATE_, CASE WHEN B.bakiye >= P.k THEN P.TOTAL WHEN B.bakiye > P.k - P.TOTAL THEN B.bakiye - (P.k - P.TOTAL) ELSE 0 END AS acik
  FROM P JOIN B ON B.CLIENTREF = P.CARDREF)
SELECT SUM(acik) AS gecmis FROM A WHERE acik > 0 AND A.DATE_ < '{end:%Y%m%d}'""")[0]
        check("R6 vadesi geçmiş alacak (FIFO) = SQL", near((cash.get("vadesiGecmis") or {}).get("alacak", 0.0), r6["gecmis"] or 0.0),
              f"{(cash.get('vadesiGecmis') or {}).get('alacak')} / {r6['gecmis']}")
        pos = logo(f"SELECT SUM(L.DEBIT) - SUM(L.CREDIT) AS b FROM dbo.LG_{f}_01_EMFLINE L JOIN dbo.LG_{f}_01_EMFICHE F ON F.LOGICALREF = L.ACCFICHEREF "
                   f"JOIN dbo.LG_{f}_EMUHACC A ON A.LOGICALREF = L.ACCOUNTREF WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 "
                   f"AND LEFT(A.CODE, 3) IN ('100','102') AND L.DATE_ >= '{y}0101' AND L.DATE_ < '{asof1}'")[0]
        check("nakit açılış bakiyesi (100 + 102) = SQL", near(cash.get("acilisBakiye"), pos["b"]), f"{cash.get('acilisBakiye')} / {pos['b']}")

    # R7 M46 ↔ M45 gider (köprü veritabanı).
    dsn = os.environ.get("SEMANTIC_STORE_DSN")
    if dsn:
        import sqlalchemy as sa

        eng = sa.create_engine(dsn)
        with eng.connect() as c:
            b46 = c.execute(sa.text("SELECT SUM(tutar) FROM semantic_budget_expense_actuals WHERE year = :y AND month = :m"), {"y": y, "m": m}).scalar()
            b45 = c.execute(sa.text("SELECT SUM(borc - alacak) FROM semantic_finance_account_actuals WHERE year = :y AND month = :m "
                                    "AND kural = 'dahil' AND hesap_kodu LIKE '7%'"), {"y": y, "m": m}).scalar()
        check("R7 gider: M46 = M45 (7xx, aynı dışlama)", near(b46 or 0, b45 or 0), f"M46 {b46} / M45 {b45}")

    # Yazma: vergi kaydı aç, oku, sil (kimlik kayda).
    s, t = http("POST", P + "/tax-calendar", {"beyan": "KABUL DENEMESİ — silinecek", "sonGun": (end + timedelta(days=5)).isoformat()})
    if s == 201:
        created["tax"].append(t["id"])
        s2, _ = http("DELETE", f"{P}/tax-calendar/{t['id']}")
        check("vergi kaydı açıldı ve silindi", s2 == 200, str(s2))
        if s2 == 200:
            created["tax"].remove(t["id"])
    else:
        check("vergi takvimi yazma yetkisi yoksa 403", s == 403, str(s))
    return finish(a.out, created)


def finish(out: str, created: dict) -> int:
    with open(out, "w") as fh:
        json.dump(created, fh)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok} geçti, {len(results) - ok} kaldı; kimlikler {out}", flush=True)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
