"""Ortak Zeki AI yapı taşları (sayı denetçisi, olgu yorumlayıcı, kişisel veri maskesi, tahmin istemcisi) ve üstlerine
kurulan üç öneri — aylık finansal yorum (M45), sabah saha brifi (M30), tahmin aralığı (M43 stok, M46 bütçe) — için test
sunucusunda gerçek API ↔ bağımsız referans kabulü. Yerelde koşulmaz.

Referanslar köprü kodunu kullanmaz: tahmin önbelleği dosyası doğrudan JSON olarak okunur (R1–R3), köprü veritabanı
doğrudan SQL ile sorgulanır (R4–R6), gelir tablosu ucu yorum olgularıyla karşılaştırılır (R7; gelir tablosunun Logo SQL
kabulü M45/referans.sql R1'de). Model metinleri: her sayı olgularda, teknoloji adı yok (R8–R9).

Yazma: yalnız seçilen ayın yorum taslağı (tur='ozet') açılır; kimliği `--out` dosyasına yazılır, `temizlik.py` siler.
Ortam: BASE (yan port köprüsü, ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturum çerezi),
SEMANTIC_STORE_DSN (köprü veritabanı), MANAGEMENT_REPORT_CACHE_DIR (tahmin önbelleği), PYTHONPATH=<aday ağaç>/backend.
İsteğe bağlı: ZK_YIL / ZK_AY (yorum dönemi; varsayılan köprünün seçtiği son tam ay), ZK_STOK (virgülle 5 stok kodu;
yoksa tahmin dosyasındaki ilk 5 kitap).
Kullanım: python kabul.py --out /tmp/claude-zeki/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
TECH = ("qwen", "vllm", "llm", "timesfm", "temporal", "openai", "dil modeli")
results: list[tuple[str, bool, str]] = []


def http(method: str, path: str, body=None, timeout=900):
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
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def near(a, b, tol=0.51) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    created: dict[str, list] = {"yorum": []}
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])

    # ---------------------------------------------------------------- R1–R3: tahmin aralığı ↔ önbellek dosyası
    cache = Path(os.environ.get("MANAGEMENT_REPORT_CACHE_DIR", "/data/nanobaseai/bi/var/management-reports")) / "baski-oneri-tahmin.json"
    snap = json.loads(cache.read_text())
    fc = snap["data"]["forecasts"]
    codes = [c for c in (os.environ.get("ZK_STOK") or "").split(",") if c] or list(fc)[:5]
    have_q = {q: sum(1 for v in fc.values() if v.get(q)) for q in ("p10", "p50", "p80", "p90")}
    check("R0 önbellekte kantiller", have_q["p50"] > 0, json.dumps(have_q))
    for code in codes:
        s, it = http("GET", "/api/v1/stock/items/" + urllib.parse.quote(code))
        if s != 200:
            check(f"R1 stok kartı {code}", False, f"HTTP {s}")
            continue
        ref = {q: (round(sum((fc.get(code) or {}).get(q, [])[:3])) if (fc.get(code) or {}).get(q) else None) for q in ("p10", "p50", "p90")}
        band = (it.get("tahminAralik") or {}).get("g90") or {}
        ok = near(band.get("p50"), ref["p50"]) and (
            (band.get("p10") is None and ref["p10"] is None) or near(band.get("p10"), ref["p10"])) and (
            (band.get("p90") is None and ref["p90"] is None) or near(band.get("p90"), ref["p90"]))
        check(f"R1 stok kartı {code}: 90 gün p10/p50/p90 = önbellek", ok, f"api={band} ref={ref}")
        check(f"R2 stok kartı {code}: p10 ≤ p50 ≤ p90 ya da aralık yok",
              band.get("aralik") is False or (band["p10"] <= band["p50"] <= band["p90"]), str(band))
    s, ro = http("GET", "/api/v1/stock/running-out?gun=90")
    rows = [i for i in (ro.get("items") or []) if isinstance(ro, dict)] if s == 200 else []
    bad = [i["stokKodu"] for i in rows if i.get("tahminAralik") and i["tahminAralik"].get("g90")
           and not near(i["tahminAralik"]["g90"]["p50"], round(sum((fc.get(i["stokKodu"]) or {}).get("p50", [])[:3])))]
    check("R3 bitecekler listesi: satırlardaki 90 gün p50 = önbellek", s == 200 and not bad, f"{len(rows)} satır, uymayan {bad[:5]}")

    # ---------------------------------------------------------------- R4: bütçe yıl sonu kapanışı ↔ doğrudan SQL + önbellek
    year = int(os.environ.get("ZK_YIL") or 0) or None
    s, tr = http("GET", "/api/v1/budget/tracking?year=" + str(year or snap["data"]["forecastStart"][:4]))
    ys = (tr or {}).get("yilSonu") if s == 200 and isinstance(tr, dict) else None
    if ys and tr.get("plan"):
        with eng.connect() as c:
            books = c.execute(sa.text("SELECT stok_kodu, adet, ciro FROM semantic_budget_book_targets WHERE plan_id = :p"),
                              {"p": tr["plan"]["id"]}).all()
            act = dict(c.execute(sa.text("SELECT stok_kodu, SUM(ciro) FROM semantic_budget_sales_actuals WHERE year = :y "
                                         "GROUP BY stok_kodu"), {"y": tr["year"]}).all())
        covered = [b for b in books if b.adet and b.adet > 0 and b.ciro and b.ciro > 0 and (fc.get(b.stok_kodu) or {}).get("p50")]
        ref_actual = sum(float(act.get(b.stok_kodu) or 0) for b in covered)
        check("R4 yıl sonu: kapsanan kitap sayısı ve gerçekleşen ciro = SQL", ys["kitap"] == len(covered) and near(ys["gercekCiro"], ref_actual, 1.0),
              f"api={ys['kitap']}/{ys['gercekCiro']} ref={len(covered)}/{round(ref_actual, 2)}")
        check("R4b yıl sonu bandı sıralı", ys["aralik"] is False or ys["p10"] <= ys["p50"] <= ys["p90"], json.dumps({k: ys[k] for k in ("p10", "p50", "p90")}))
    else:
        check("R4 yıl sonu kapanışı", False, f"HTTP {s}; yürürlükte plan ya da tahmin yok (DOĞRULANAMADI)")

    # ---------------------------------------------------------------- R5–R6: sabah saha brifi ↔ doğrudan SQL
    s, today = http("GET", "/api/v1/field/today?limit=3")
    s2, brief = http("GET", "/api/v1/field/today/brief")
    with eng.connect() as c:
        ref_od = c.execute(sa.text("SELECT COALESCE(SUM(s.vadesi_gecmis), 0) FROM semantic_field_portfolio p JOIN semantic_field_signals s "
                                   "ON s.tenant_id = p.tenant_id AND s.logo_code = p.logo_code")).scalar()
    check("R5 Bugün vadesi geçmiş toplamı = SQL (yönetici kapsamı)", s == 200 and near(today["kpi"]["vadesiGecmis"], ref_od, 1.0),
          f"api={today.get('kpi', {}).get('vadesiGecmis') if s == 200 else s} ref={ref_od}")
    ok = s2 == 200 and isinstance(brief, dict) and bool(brief.get("metin")) and brief.get("kaynak") in ("zeki", "kural")
    check("R6 sabah brifi döndü (kaynak etiketiyle)", ok, f"{brief.get('kaynak') if ok else s2}: {str(brief.get('metin') if ok else brief)[:200]}")
    if ok:
        check("R6b brifte teknoloji adı yok", not any(t in brief["metin"].lower() for t in TECH))
        check("R6c brifte etiket kalmadı", not re.search(r"\[[A-Z]\]", brief["metin"]))

    # ---------------------------------------------------------------- R7–R9: aylık finansal yorum
    q = {"year": os.environ.get("ZK_YIL"), "month": os.environ.get("ZK_AY")}
    qs = "&".join(f"{k}={v}" for k, v in q.items() if v)
    s, cur = http("GET", "/api/v1/finance/commentary" + ("?" + qs if qs else ""))
    check("R7a yorum okunur", s == 200, str(s))
    s, bad_body = http("PUT", "/api/v1/finance/commentary", {"metin": ""})
    check("R7b boş metin reddedilir (400/403/404)", s in (400, 403, 404), str(s))
    s, d = http("POST", "/api/v1/finance/commentary/draft", {"year": cur.get("year"), "month": cur.get("month")}, timeout=900)
    if s == 200 and d.get("id"):
        created["yorum"].append(d["id"])
        s3, pnl = http("GET", f"/api/v1/finance/pnl?year={d['year']}&month={d['month']}&grain=ay")
        net = next((r["values"]["donem"] for r in pnl.get("rows", []) if r["kod"] == "NET_SATIS"), None) if s3 == 200 else None
        shown = f"{abs(net):,.0f}".replace(",", ".") if net is not None else None
        if d.get("kaynak") == "kural":
            check("R7 kural metnindeki net satış = gelir tablosu ucu", shown is not None and shown in (d.get("metin") or ""),
                  f"net={shown}")
        else:
            print("R7 atlandı: metin Zeki AI'ın; sayılarının olgulara bağlılığı R8'de denetlenir. Kural metni için "
                  "ZK_AY ile model kapalıyken yeniden koşturun.", flush=True)
        check("R8 taslakta olgu dışı sayı yok", d.get("olguDisiSayilar") == [], f"kaynak={d.get('kaynak')} neden={d.get('neden')}")
        check("R9 taslakta teknoloji adı yok", not any(t in (d.get("metin") or "").lower() for t in TECH))
        s4, ap_ = http("POST", "/api/v1/finance/commentary/approve", {"year": d["year"], "month": d["month"]})
        check("R9b onay açık yetkiyle (200 ya da yetki yoksa 403)", s4 in (200, 403), str(s4))
    else:
        check("R7 yorum taslağı", False, f"HTTP {s}: {str(d)[:200]}")

    # Maske: talep/e-posta gövdeleri köprüde saklanmadığı için gerçek metinle ayrıca sınanmaz; ortak maskenin kuralları
    # pytest'te (test_zeki_text, test_support, test_okur, test_hr_recruit, test_trendyol) ve modüllerin kendi kabulünde.

    Path(a.out).write_text(json.dumps(created, ensure_ascii=False))
    ok_n = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok_n} geçti, {len(results) - ok_n} kaldı; kimlikler {a.out}")
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
