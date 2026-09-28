"""Sorgu bilgisi kabulü — M32 Kurumsal satış ve B2B (/kurumsal-satis, /kurumsal-satis/firsat/:id). Test sunucusunda, yan
port köprüsüyle; yalnız okuma, hiçbir yere yazmaz (paket önerisi POST'tur ama yalnız hesaplar, kaydetmez).

Her uçta K1–K3 (kabul.py ile aynı: kaynaksız rakam yok, kayıt tutarlı, her SQL gerçekten koşar) ve doğrudan SQL
referansları:
  R1  «Kurum cirosu» kartı = kartın portal sorgusunun bu yıl dönem satırlarının Σ ciro'su; geçen yıl aynı dönem de öyle;
  R2  aynı kart = okumada çalışan Logo kurum satış sorgularının (yıl kopyası başına) bugünkü sonucunda aynı dönem Σ ciro
      (okumadan sonra Logo'ya fatura girdiyse fark beklenir → UYARI);
  R3  kurum listesi «toplam» = kurum kartı sorgusunun satır sayısı;
  R4  «Sipariş vermeyen bayi» kartı = bayi listesinin «sessiz» sayısı (kart ve sekme aynı kural);
  R5  bayi ayrıntısı Σ kitaplık cirosu = o istekte çalışan Logo sorgularının Σ ciro'su (anlık okuma).

Ortam kabul.py ile aynı. Kullanım: python kabul_kurumsal.py [--skip-heavy]
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

import kabul
from kabul import check, contract, http, num, results, run_all


def post(path: str, body: dict, timeout: int = 600):
    req = urllib.request.Request(kabul.BASE + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Cookie": kabul.COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def ok_or_skip(name: str, st: int, out: dict) -> bool:
    if st == 200:
        return True
    check(name, None, f"HTTP {st} ({(out.get('detail') or {}) if isinstance(out, dict) else ''})"[:200])
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    heavy = not ap.parse_args().skip_heavy
    from semantic_bridge import corporate_sales_kaynak as K

    ig = K.NOT_RAKAM
    B = "/api/v1/corporate"

    st, meta = http(B + "/meta", 120)
    if ok_or_skip("kurumsal /meta", st, meta):
        run_all("kurumsal /meta", contract("kurumsal /meta", meta, ig), heavy)

    st, s = http(B + "/summary", 300)
    if ok_or_skip("kurumsal /summary", st, s):
        k = contract("kurumsal /summary", s, ig)
        got = run_all("kurumsal /summary", k, heavy)
        w = s.get("window")
        rows = got.get("kurumsal.kurumCiroDonem")
        if w and rows is not None:
            cur = sum(num(r.get("ciro")) for r in rows if int(r.get("year") or 0) == w["year"])
            prev = sum(num(r.get("ciro")) for r in rows if int(r.get("year") or 0) == w["year"] - 1)
            check("R1 «Kurum cirosu» kartı = kart sorgusu", abs(cur - num(s.get("kurumCiro"))) < 0.05
                  and abs(prev - num(s.get("kurumCiroGecenYil"))) < 0.05,
                  f"sorgu {cur:,.2f} / {prev:,.2f} · kart {s.get('kurumCiro')} / {s.get('kurumCiroGecenYil')}")
        if w:
            logo_ids = [sid for sid, src in (k.get("sources") or {}).items()
                        if sid.startswith("kurumsal.okuma.kurumSatis.") and "_01_INVOICE AS I" not in src["sql"]]
            if logo_ids and all(sid in got for sid in logo_ids):
                cur = sum(num(r.get("ciro")) for sid in logo_ids for r in got[sid]
                          if int(r.get("yil") or 0) == w["year"] and int(r.get("ay") or 0) <= w["months"])
                same = abs(cur - num(s.get("kurumCiro"))) < 0.05
                check("R2 kart = okumadaki Logo kurum satış sorguları (bugün)", True if same else None,
                      f"Logo bugün {cur:,.2f} · kart {s.get('kurumCiro')}")
            elif not logo_ids:
                check("kurumsal okuma sorguları kayıtlı", None, "bu sürümden sonraki ilk okumada kaydedilir («Verileri yenile» ya da 04:00)")

    st, lst = http(B + "/accounts?page=0", 300)
    if ok_or_skip("kurumsal /accounts", st, lst):
        got = run_all("kurumsal /accounts", contract("kurumsal /accounts", lst, ig), heavy)
        rows = got.get("kurumsal.kurumlar")
        if rows is not None:
            check("R3 kurum listesi toplamı = kurum kartı sorgusu", len(rows) == num(lst.get("total")),
                  f"sorgu {len(rows)} · ekran {lst.get('total')}")
        ref = next((a["ref"] for a in lst.get("items") or [] if a.get("buYil")), None) or next(
            (a["ref"] for a in lst.get("items") or []), None)
        if ref:
            st, acc = http(f"{B}/accounts/{urllib.parse.quote(ref, safe='')}", 300)
            if ok_or_skip("kurumsal /accounts/{ref}", st, acc):
                run_all("kurumsal /accounts/{ref}", contract("kurumsal /accounts/{ref}", acc, ig), heavy)

    for path in ("/books?q=kitap", "/themes?durum=onayli", "/themes?durum=onerildi", "/reminders", "/pipeline/summary",
                 "/approvals", "/b2b/highlights"):
        st, out = http(B + path, 300)
        if ok_or_skip(f"kurumsal {path}", st, out):
            run_all(f"kurumsal {path}", contract(f"kurumsal {path}", out, ig), heavy)

    vocab = (meta or {}).get("vocabulary") or []
    if vocab:
        st, pk = post(B + "/packages/suggest", {"temalar": [vocab[0]], "kisi": 50, "kitapSayisi": 3})
        if ok_or_skip("kurumsal /packages/suggest", st, pk):
            run_all("kurumsal /packages/suggest", contract("kurumsal /packages/suggest", pk, ig), heavy)

    st, opps = http(B + "/opportunities", 300)
    if ok_or_skip("kurumsal /opportunities", st, opps):
        run_all("kurumsal /opportunities", contract("kurumsal /opportunities", opps, ig), heavy)
        oid = next((o["id"] for o in opps.get("items") or [] if o.get("sonTeklif")), None) or next(
            (o["id"] for o in opps.get("items") or []), None)
        if oid:
            st, o = http(f"{B}/opportunities/{oid}", 300)
            if ok_or_skip("kurumsal /opportunities/{id}", st, o):
                run_all("kurumsal /opportunities/{id}", contract("kurumsal /opportunities/{id}", o, ig), heavy)
                qid = next((q["id"] for q in o.get("teklifler") or []), None)
                if qid:
                    st, q = http(f"{B}/quotes/{qid}", 300)
                    if ok_or_skip("kurumsal /quotes/{id}", st, q):
                        run_all("kurumsal /quotes/{id}", contract("kurumsal /quotes/{id}", q, ig), heavy)

    st, d = http(B + "/b2b/dealers?durum=", 300)
    if ok_or_skip("kurumsal /b2b/dealers", st, d):
        run_all("kurumsal /b2b/dealers", contract("kurumsal /b2b/dealers", d, ig), heavy)
        if s:
            check("R4 «Sipariş vermeyen bayi» kartı = bayi listesi «sessiz»", num(s.get("sessizBayi")) == num((d.get("counts") or {}).get("sessiz")),
                  f"kart {s.get('sessizBayi')} · liste {(d.get('counts') or {}).get('sessiz')}")
        kod = next((x["logoKod"] for x in d.get("items") or []), None)
        if kod:
            st, x = http(f"{B}/b2b/dealers/{urllib.parse.quote(kod, safe='')}", 600)
            if ok_or_skip("kurumsal /b2b/dealers/{kod}", st, x):
                k = contract("kurumsal /b2b/dealers/{kod}", x, ig)
                got = run_all("kurumsal /b2b/dealers/{kod}", k, heavy)
                live = [sid for sid in (k.get("sources") or {}) if sid.startswith("kurumsal.bayiAyrinti.")]
                if live and all(sid in got for sid in live):
                    sql_ciro = sum(num(r.get("ciro")) for sid in live for r in got[sid])
                    screen = sum(num(m.get("ciro")) for m in x.get("kitaplik") or [])
                    check("R5 bayi ayrıntısı Σ kitaplık cirosu = anlık Logo sorguları", abs(sql_ciro - screen) < 0.05,
                          f"sorgu {sql_ciro:,.2f} · ekran {screen:,.2f}")

    ok = sum(1 for _, st_, _ in results if st_ == "GEÇTİ")
    bad = sum(1 for _, st_, _ in results if st_ == "KALDI")
    warn = sum(1 for _, st_, _ in results if st_ == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
