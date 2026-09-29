"""Zeki AI öneri 4–8 kabulü (test sunucusunda; yerelde koşulmaz): fark ayrıştırma («Neden?»), beklenen aralık + eşik
önerisi, pano «ne değişti», bütçe sapmasının nedeni, olasılıklı nakit bandı, destek taslağı olguları.

Referanslar köprü kodunu kullanmaz: Logo doğrudan bağlantı dosyasıyla sorgulanır (R1–R3, R9), köprü veritabanı doğrudan
SQL ile (R6–R7). Net ciro referansı bilinen tanımdır: faturalı satır (INVOICEREF <> 0), CANCELLED = 0, LINETYPE = 0,
satış TRCODE 7/8/9 artı, iade 2/3 eksi, Σ LINENET; yıllar kendi kopyasında kendi tarihleriyle (L_CAPIPERIOD).
Katalog ölçüsü bu tanımdan saparsa R1 KALDI der — bu bir bulgudur, ayar değil.

Yazma: yalnız pano kartı (R8; timasai'nin panosuna geçici kart eklenir, sonunda çıkarılır). Kimlikler `--out` dosyasına,
`temizlik.py` artakalanı siler.
Ortam: BASE (yan port köprüsü), COOKIE (timasai 15 dk oturumu), SEMANTIC_STORE_DSN, SEMANTIC_CONNECTION_FILE (Logo),
PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı: ZF_SORU (varsayılan «2026 yılı net ciro»), ZF_TALEP (destek talep no, R10).
Kullanım: python kabul.py --out /tmp/claude-zf/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
TECH = ("qwen", "vllm", "llm", "timesfm", "temporal", "openai", "dil modeli")
results: list[tuple[str, bool, str]] = []


def http(method: str, path: str, body=None, timeout=1200):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": "application/json"})
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


def near(a, b, tol=1.0) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def logo():
    from semantic_layer.profiler.connectors import connector_from_file

    conn = connector_from_file(os.environ["SEMANTIC_CONNECTION_FILE"])
    conn.query_timeout = 1800

    def run(sql: str):
        _cols, rows, _t = conn.execute(sql, 2_000_000)
        return rows
    return run


def firms(run) -> dict[int, str]:
    out: dict[int, int] = {}
    own = {int(x) for x in os.environ.get("SEMANTIC_FIRMS", "").split(",") if x.strip().isdigit()}   # canlı Logo başka şirketleri de taşır
    for r in run("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1"):
        f = int(r["FIRMNR"])
        if f in (15, 16) or (own and f not in own):
            continue
        for y in range(r["BEGDATE"].year, r["ENDDATE"].year + 1):
            out[y] = max(out.get(y, 0), f)
    return {y: f"{f:03d}" for y, f in out.items()}


def net_sql(firm: str, a: date, b: date, group: str = "") -> str:
    sel = f"{group} AS k, " if group else ""
    grp = f" GROUP BY {group}" if group else ""
    return (f"SELECT {sel}SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS v "
            f"FROM dbo.LG_{firm}_01_STLINE S LEFT JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = S.CLIENTREF "
            f"WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) "
            f"AND S.DATE_ >= '{a:%Y%m%d}' AND S.DATE_ < '{b:%Y%m%d}'{grp}")


def ref_total(run, fm, a: date, b: date) -> float:
    tot = 0.0
    for y in range(a.year, (b - timedelta(days=1)).year + 1):
        lo, hi = max(a, date(y, 1, 1)), min(b, date(y + 1, 1, 1))
        rows = run(net_sql(fm[y], lo, hi))
        tot += float((rows[0] or {}).get("v") or 0) if rows else 0.0
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    created: dict[str, list] = {"kart": []}
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    run = logo()
    fm = firms(run)
    soru = os.environ.get("ZF_SORU", "2026 yılı net ciro")

    # ---------------------------------------------------------------- R1–R5: «Neden?» ↔ doğrudan Logo SQL
    s, res = http("POST", "/api/v1/fark/ayristir", {"question": soru, "karsi": "gecen-yil"})
    if s != 200 or not res.get("ok"):
        check("R1 ayrıştırma döndü", False, f"HTTP {s}: {str(res)[:300]}")
    else:
        a, b = date.fromisoformat(res["donem"]["bas"]), date.fromisoformat(res["donem"]["bit"])
        ca, cb = date.fromisoformat(res["karsi"]["bas"]), date.fromisoformat(res["karsi"]["bit"])
        r_now, r_prev = ref_total(run, fm, a, b), ref_total(run, fm, ca, cb)
        check("R1 dönem toplamı = doğrudan SQL (net ciro tanımı)", near(res["toplam"]["simdi"], r_now),
              f"api={res['toplam']['simdi']} ref={round(r_now, 2)} ölçü={res['olcu']}")
        check("R2 karşı dönem toplamı = doğrudan SQL (kopya kendi tarihiyle)", near(res["toplam"]["onceki"], r_prev),
              f"api={res['toplam']['onceki']} ref={round(r_prev, 2)} {ca}–{cb}")
        kanal = next((d for d in res["boyutlar"] if d["id"] == "kanal"), None)
        if kanal and a.year == (b - timedelta(days=1)).year:
            rows = run(net_sql(fm[a.year], a, b, "ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), N'Grup kodu boş')"))
            ref = {str(r["k"]): float(r["v"] or 0) for r in rows}
            bad = [i["anahtar"] for i in kanal["kalemler"][:5] if not near(i["simdi"], ref.get(i["anahtar"]))]
            check("R3 en büyük 5 kanal katkısının dönem değeri = doğrudan SQL", not bad, f"uymayan {bad}")
        for d in res["boyutlar"]:
            s_items = sum(i["fark"] for i in d["kalemler"])
            check(f"R4 {d['ad']}: kalem farkları toplamı = net fark (tavan yok)", near(s_items, d["fark"], 5.0),
                  f"Σ={round(s_items, 2)} fark={d['fark']} kalem={d['kalemSayisi']}")
        an = res.get("anlatim") or {}
        check("R5 anlatım döndü (kaynak etiketi)", an.get("kaynak") in ("zeki", "kural") and bool(an.get("metin")), str(an)[:200])
        check("R5b anlatımda teknoloji adı yok", not any(t in (an.get("metin") or "").lower() for t in TECH))
        check("R5c çalıştırılan SQL cevapta", len((res.get("kaynak") or {}).get("sql") or []) >= 2)

    # ---------------------------------------------------------------- R6: beklenen aralık / eşik önerisi
    s, sug = http("POST", "/api/v1/alerts/suggest", {"question": os.environ.get("ZF_UYARI_SORU", "bu ay net ciro"), "condition": "gt"})
    if s == 200 and sug.get("ok"):
        check("R6 beklenen aralık sıralı ve öneri üst sınır", sug["alt"] <= sug["merkez"] <= sug["ust"] and sug["oneri"]["esik"] == sug["ust"],
              json.dumps({k: sug.get(k) for k in ("alt", "merkez", "ust", "yontem", "nokta")}))
    else:
        check("R6 beklenen aralık", s == 200 and bool(sug.get("neden")), f"HTTP {s}: {str(sug)[:200]} (neden yazılıysa uydurmadı)")

    # ---------------------------------------------------------------- R7: bütçe sapmasının nedeni ↔ köprü tabloları
    with eng.connect() as c:
        dev = c.execute(sa.text("SELECT id, kind, scope, key, actual, expected FROM semantic_budget_alerts WHERE status = 'acik' "
                                "AND kind IN ('gider', 'satis') ORDER BY kind LIMIT 2")).all()
    for d in dev:
        s, r = http("POST", f"/api/v1/budget/deviations/{d.id}/neden", {})
        ok = s == 200 and r.get("ok")
        check(f"R7 sapma nedeni döndü ({d.kind}/{d.scope})", bool(ok), f"HTTP {s}: {str(r)[:200]}")
        if ok and d.kind == "gider":
            months = r["boyutlar"][0]
            check("R7b gider: ayların gerçekleşeni toplamı = uyarının gerçekleşeni", near(months["simdi"], d.actual, 1.0),
                  f"api={months['simdi']} db={d.actual}")
        if ok:
            check("R7c toplam = uyarı satırı", near(r["toplam"]["simdi"], d.actual, 0.5) and near(r["toplam"]["onceki"], d.expected, 0.5))
    if not dev:
        print("R7 atlandı: açık bütçe sapması yok.", flush=True)

    # ---------------------------------------------------------------- R8: pano «ne değişti»
    s, bd = http("GET", "/api/v1/board")
    if s == 200:
        cid = "zf-" + uuid.uuid4().hex[:10]
        created["kart"].append(cid)
        cards = [dict(c, sqlOpen=c.get("sqlOpen")) for c in bd["cards"]]
        s0, ask = http("POST", "/api/v1/ask", {"question": "2026 kanallara göre net ciro"})
        sql = (ask or {}).get("sql") if s0 == 200 else None
        if sql:
            s1, _ = http("PUT", "/api/v1/board", {"cards": cards + [{"id": cid, "title": "Kabul (silinecek)", "sql": sql,
                                                                      "question": "2026 kanallara göre net ciro", "chart": "table"}]})
            s2, r1 = http("POST", f"/api/v1/board/cards/{cid}/run", {})
            s3, r2 = http("POST", f"/api/v1/board/cards/{cid}/run", {})
            check("R8 ilk koşu «ilk», ikincisi fark taşır", s2 == 200 and r1.get("fark", {}).get("ilk") is True and "fark" in r2,
                  f"{s1}/{s2}/{s3}")
            s4, note = http("POST", f"/api/v1/board/cards/{cid}/change-note", {})
            check("R8b ne değişti notu", s4 == 200 and isinstance(note.get("maddeler"), list), str(note)[:200])
            http("PUT", "/api/v1/board", {"cards": cards})
        else:
            check("R8 pano kartı", False, f"soru cevaplanmadı: {str(ask)[:200]}")

    # ---------------------------------------------------------------- R9: olasılıklı nakit bandı
    s, cash = http("GET", "/api/v1/finance/cash")
    band = (cash or {}).get("bant") if s == 200 else None
    if band and band.get("var"):
        order = all(w["kapanis"]["kotu"] <= w["kapanis"]["orta"] <= w["kapanis"]["iyi"] for w in band["haftalar"])
        check("R9 bant sıralı (en kötü ≤ beklenen ≤ en iyi)", order)
        same = all(near(w["kuralKapanis"], h["kapanis"], 0.5) for w, h in zip(band["haftalar"], cash["haftalar"]))
        check("R9b «vadelere göre» çizgisi = tablonun kapanışı", same)
        start = date.fromisoformat(cash["run"]["baslangic"])
        wk = start - timedelta(days=7)
        f = fm[wk.year]
        ref = run(f"""SELECT SUM(L.DEBIT) AS t FROM dbo.LG_{f}_01_EMFLINE L JOIN dbo.LG_{f}_01_EMFICHE F ON F.LOGICALREF = L.ACCFICHEREF
            JOIN dbo.LG_{f}_EMUHACC A ON A.LOGICALREF = L.ACCOUNTREF
            WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND F.TRCODE <> 1 AND LEFT(A.CODE, 3) IN ('100', '102')
              AND L.DATE_ >= '{wk:%Y%m%d}' AND L.DATE_ < '{start:%Y%m%d}'
              AND EXISTS (SELECT 1 FROM dbo.LG_{f}_01_EMFLINE L2 JOIN dbo.LG_{f}_EMUHACC A2 ON A2.LOGICALREF = L2.ACCOUNTREF
                          WHERE L2.ACCFICHEREF = L.ACCFICHEREF AND L2.CANCELLED = 0 AND LEFT(A2.CODE, 3) = '120')""")
        print(f"R9 bilgi: son tam haftanın müşteri tahsilatı (doğrudan SQL) = {ref[0].get('t') if ref else None}", flush=True)
    else:
        check("R9 bant yoksa nedeni yazılı (uydurulmadı)", bool(band) and bool(band.get("neden")), str(band)[:200])

    # ---------------------------------------------------------------- R10: destek taslağı olguları (isteğe bağlı)
    t = os.environ.get("ZF_TALEP")
    if t:
        s, dr = http("POST", "/api/v1/support/draft", {"ticket": t})
        if s == 200:
            nums = re.findall(r"\d[\d.,]*", dr.get("draft") or "")
            allowed = " ".join(str(v) for v in (dr.get("facts") or {}).values())
            check("R10 taslaktaki sayılar olgularda (ya da talepte)", all(n.strip(".,") in allowed or len(n) <= 2 for n in nums),
                  f"olgular={sorted(dr.get('facts') or {})}")
        else:
            check("R10 destek taslağı", False, f"HTTP {s}: {str(dr)[:200]}")

    Path(args.out).write_text(json.dumps(created, ensure_ascii=False))
    ok_n = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok_n} geçti, {len(results) - ok_n} kaldı; kimlikler {args.out}")
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
