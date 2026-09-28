"""Sorgu bilgisi kabulü — Kayıtlar › telif: M6 sözleşmeler (/telif-sozlesme, /odemeler, /sablonlar, /:key, /yeni'deki
CRM seçicileri), M54 telif dönemi (/telif-donem) ve haklar (/haklar). Test sunucusunda, yan port köprüsüyle; YALNIZ
okuma (GET), hiçbir yere yazmaz (hakediş önizlemesi ve Zeki AI önerisi POST'tur, burada çağrılmaz).

Her uçta K1–K3 (kabul.py ile aynı: kaynaksız rakam yok, kayıt tutarlı, her SQL gerçekten koşar) ve doğrudan SQL
referansları:
  R1  «Yürürlükte» kartı = CRM özet sorgusunun yururlukte kolonu (aynı istekte değilse CRM değişmiş olabilir → UYARI);
  R2  sözleşme listesi toplamı = CRM sayım sorgusunun sonucu;
  R3  ödeme takvimi «Bekleyen» = takvim portal sorgusunun satır sayısı;
  R4  koşu «Kapsam» = koşu satırları portal sorgusunun satır sayısı; «Hesaplandı» = durumu hesaplandı olan satır;
  R5  koşunun CRM kapsam sorgusu bugün koşunca satır sayısı = koşuda kaydedilen satır sayısı (sonradan CRM değiştiyse UYARI);
  R6  «N gün içinde biten» = CRM yenileme sorgusunun satır sayısı;
  R7  «N lisans» = lisans portal sorgusunun satır sayısı;
  R8  hak açıklaması «İncelenecek» sayısı = portal sorgusundaki incele satırları.

Ortam kabul.py ile aynı. Kullanım: python kabul_kayitlar_telif.py [--skip-heavy]
"""
from __future__ import annotations

import argparse
import urllib.parse

from kabul import check, contract, http, num, results, run_all


def ok_or_skip(name: str, st: int, out: dict) -> bool:
    if st == 200:
        return True
    detail = (out.get("detail") or {}) if isinstance(out, dict) else ""
    check(name, None, f"HTTP {st} ({detail})"[:200])
    return False


def first(rows, key=None) -> float:
    if not rows:
        return 0.0
    return num(rows[0].get(key) if key else list(rows[0].values())[0])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    heavy = not ap.parse_args().skip_heavy
    from semantic_bridge import contracts_kaynak as CK
    from semantic_bridge import royalty_kaynak as RK

    # ---------------------------------------------------------------- M6 sözleşmeler
    B = "/api/v1/editorial/contracts"
    st, s = http(B + "/summary", 300)
    if ok_or_skip("sözleşme /summary", st, s):
        got = run_all("sözleşme /summary", contract("sözleşme /summary", s, CK.NOT_RAKAM), heavy)
        rows = got.get("sozlesme.crm.ozet")
        if rows is not None:
            same = first(rows, "yururlukte") == num(s.get("active"))
            check("R1 «Yürürlükte» kartı = CRM özet sorgusu", True if same else None,
                  f"sorgu {first(rows, 'yururlukte'):,.0f} · kart {s.get('active')}")

    st, lst = http(B + "?order=bitis&page=0", 300)
    crm_key = None
    if ok_or_skip("sözleşme listesi", st, lst):
        got = run_all("sözleşme listesi", contract("sözleşme listesi", lst, CK.NOT_RAKAM), heavy)
        rows = got.get("sozlesme.crm.sayim")
        if rows is not None:
            check("R2 liste toplamı = CRM sayım sorgusu", True if first(rows, "n") == num(lst.get("total")) else None,
                  f"sorgu {first(rows, 'n'):,.0f} · liste {lst.get('total')}")
        crm_key = next((c["id"] for c in lst.get("items") or [] if c.get("id")), None)

    st, recs = http(B + "/records", 300)
    portal_key = None
    if ok_or_skip("sözleşme /records", st, recs):
        run_all("sözleşme /records", contract("sözleşme /records", recs, CK.NOT_RAKAM), heavy)
        portal_key = next((r["id"] for r in recs.get("items") or []), None)

    for key in [x for x in (crm_key, portal_key) if x]:
        st, d = http(f"{B}/item/{urllib.parse.quote(key)}", 600)
        if ok_or_skip(f"sözleşme /item/{key[:8]}", st, d):
            run_all(f"sözleşme /item/{key[:8]}", contract(f"sözleşme /item/{key[:8]}", d, CK.NOT_RAKAM), heavy)

    st, due = http(B + "/payments?status=planlandi&within=90", 300)
    if ok_or_skip("sözleşme /payments", st, due):
        got = run_all("sözleşme /payments", contract("sözleşme /payments", due, CK.NOT_RAKAM), heavy)
        rows = got.get("sozlesme.takvim")
        if rows is not None:
            check("R3 «Bekleyen» = takvim portal sorgusu", len(rows) == len(due.get("items") or []),
                  f"sorgu {len(rows)} · ekran {len(due.get('items') or [])}")

    st, tp = http(B + "/templates", 120)
    if ok_or_skip("sözleşme /templates", st, tp):
        run_all("sözleşme /templates", contract("sözleşme /templates", tp, CK.NOT_RAKAM), heavy)
    for kind in ("books", "parties"):
        st, lk = http(f"{B}/lookup/{kind}?q=an", 300)
        if ok_or_skip(f"sözleşme /lookup/{kind}", st, lk):
            run_all(f"sözleşme /lookup/{kind}", contract(f"sözleşme /lookup/{kind}", lk, CK.NOT_RAKAM), heavy)

    # ---------------------------------------------------------------- M54 telif dönemi
    R = "/api/v1/royalty"
    ig = RK.NOT_RAKAM
    st, meta = http(R + "/meta", 120)
    if ok_or_skip("telif /meta", st, meta):
        run_all("telif /meta", contract("telif /meta", meta, ig), heavy)
    st, runs = http(R + "/runs", 120)
    run_id = None
    if ok_or_skip("telif /runs", st, runs):
        run_all("telif /runs", contract("telif /runs", runs, ig), heavy)
        run_id = next((r["id"] for r in runs.get("items") or [] if r["status"] not in ("iptal", "taslak")), None)
    if run_id:
        st, run = http(f"{R}/runs/{run_id}", 300)
        if ok_or_skip("telif /runs/{id}", st, run):
            got = run_all("telif /runs/{id}", contract("telif /runs/{id}", run, ig), heavy)
            rows = got.get("telif.satirlar")
            summ = run.get("summary") or {}
            if rows is not None:
                check("R4 «Kapsam» = koşu satırları sorgusu", len(rows) == num(summ.get("lines")), f"{len(rows)} · {summ.get('lines')}")
                done = sum(1 for r in rows if r.get("durum") == "hesaplandi")
                check("R4 «Hesaplandı» = hesaplandı satırları", done == num((summ.get("counts") or {}).get("hesaplandi")),
                      f"{done} · {(summ.get('counts') or {}).get('hesaplandi')}")
            srcs = (run.get("kaynaklar") or {}).get("sources") or {}
            head = next((sid for sid, x in srcs.items() if sid.startswith("telif.hesap.") and "new_SozlemeninSahibi" in x["sql"]), None)
            if head and head in got:
                was = (srcs[head].get("stats") or {}).get("rows")
                check("R5 koşunun CRM kapsam sorgusu bugün = koşudaki satır", True if len(got[head]) == was else None,
                      f"bugün {len(got[head])} · koşuda {was}")
            elif not head:
                check("R5 koşunun CRM kapsam sorgusu", None, "bu koşu çalışan sorgunun saklanmasından önce hesaplanmış")
        st, lines = http(f"{R}/runs/{run_id}/lines", 300)
        if ok_or_skip("telif /lines", st, lines):
            run_all("telif /lines", contract("telif /lines", lines, ig), heavy)
            lid = next((x["id"] for x in lines.get("items") or []), None)
            if lid:
                st, ln = http(f"{R}/runs/{run_id}/lines/{lid}", 300)
                if ok_or_skip("telif /lines/{id}", st, ln):
                    run_all("telif /lines/{id}", contract("telif /lines/{id}", ln, ig), heavy)
                key = next((x["contractKey"] for x in lines.get("items") or []), None)
                st, cl = http(f"{R}/contracts/{key}/lines", 120)
                if ok_or_skip("telif /contracts/{key}/lines", st, cl):
                    run_all("telif /contracts/{key}/lines", contract("telif /contracts/{key}/lines", cl, ig), heavy)
        for path in (f"{R}/runs/{run_id}/parties", f"{R}/runs/{run_id}/payments"):
            st, out = http(path, 300)
            if ok_or_skip(f"telif {path.rsplit('/', 1)[-1]}", st, out):
                run_all(f"telif {path.rsplit('/', 1)[-1]}", contract(f"telif {path.rsplit('/', 1)[-1]}", out, ig), heavy)
    st, adv = http(R + "/advances", 300)
    if ok_or_skip("telif /advances", st, adv):
        run_all("telif /advances", contract("telif /advances", adv, ig), heavy)
        key = next((x["contractKey"] for x in adv.get("items") or []), None)
        if key:
            st, h = http(f"{R}/advances/{key}", 120)
            if ok_or_skip("telif /advances/{key}", st, h):
                run_all("telif /advances/{key}", contract("telif /advances/{key}", h, ig), heavy)
    st, ren = http(R + "/renewals?days=90", 300)
    if ok_or_skip("telif /renewals", st, ren):
        got = run_all("telif /renewals", contract("telif /renewals", ren, ig), heavy)
        rows = got.get("telif.crm.yenileme.1")
        if rows is not None:
            check("R6 «90 gün içinde biten» = CRM yenileme sorgusu", len(rows) == num(ren.get("total")) or None,
                  f"sorgu {len(rows)} · ekran {ren.get('total')}")

    # ---------------------------------------------------------------- haklar
    H = "/api/v1/rights"
    st, se = http(H + "/search?q=an", 300)
    if ok_or_skip("haklar /search", st, se):
        run_all("haklar /search", contract("haklar /search", se, ig), heavy)
        book = next((b["id"] for b in se.get("items") or []), None)
        if book:
            st, card = http(f"{H}/books/{book}", 300)
            if ok_or_skip("haklar /books/{id}", st, card):
                run_all("haklar /books/{id}", contract("haklar /books/{id}", card, ig), heavy)
    st, lic = http(H + "/licenses-out", 120)
    if ok_or_skip("haklar /licenses-out", st, lic):
        got = run_all("haklar /licenses-out", contract("haklar /licenses-out", lic, ig), heavy)
        rows = got.get("haklar.lisanslar")
        if rows is not None:
            check("R7 «N lisans» = lisans portal sorgusu", len(rows) == num(lic.get("total")), f"{len(rows)} · {lic.get('total')}")
    st, notes = http(H + "/notes?status=incele", 120)
    if ok_or_skip("haklar /notes", st, notes):
        got = run_all("haklar /notes", contract("haklar /notes", notes, ig), heavy)
        rows = got.get("haklar.aciklamaSayilari")
        if rows is not None:
            n = sum(1 for r in rows if r.get("durum") == "incele")
            check("R8 «İncelenecek» sayısı = portal sorgusu", n == num((notes.get("counts") or {}).get("incele")),
                  f"{n} · {(notes.get('counts') or {}).get('incele')}")

    ok = sum(1 for _, s_, _ in results if s_ == "GEÇTİ")
    bad = sum(1 for _, s_, _ in results if s_ == "KALDI")
    warn = sum(1 for _, s_, _ in results if s_ == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
