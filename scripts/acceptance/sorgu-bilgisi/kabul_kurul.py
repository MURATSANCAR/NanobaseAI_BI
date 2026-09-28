"""Sorgu bilgisi kabulü — DYK Kurul (/kurul, /kurul/toplanti/:id, /kurul/paket/:id). Test sunucusunda, yan port
köprüsüyle; yalnız okuma (GET), hiçbir yere yazmaz. Panel ucu ölçüm bayatsa arka planda ölçüm başlatır: bu köprünün
kendi işidir, kabul betiği bir şey yazmaz; bayat ölçümü tetiklememek için panel `donem=` ile istenir.

Her uçta K1–K3 (kabul.py ile aynı: kaynaksız rakam yok, kayıt tutarlı, her SQL gerçekten koşar) ve doğrudan SQL
referansları:
  R1  her hazır kutunun değeri = kutunun portal sorgusunun (kurul değer satırı) o koddaki `deger`'i;
  R2  «Net satış» kutusu = kökenindeki M45 portal sorgusunun net kolonu (ölçümden sonra finans yenilendiyse fark
      beklenir → UYARI);
  R3  «Süresi yaklaşan sözleşme» kutusu = ölçümde CRM'de çalışan sorgunun bugünkü `yaklasan`'ı (gün döndüyse → UYARI);
  R4  «Geciken kurul aksiyonu» = aksiyon sorgusunun satırlarından termini bugünden önce olan açıkların sayısı;
  R5  toplantı listesi karar sayıları = karar sayım sorgusunun sonucu;
  R6  paket gösterge değerleri = paket kaydı sorgusunun icerik_json'undaki değerler (dondurulmuş içerik).

Ortam kabul.py ile aynı. Kullanım: python kabul_kurul.py [--skip-heavy]
"""
from __future__ import annotations

import argparse
import json
from datetime import date

from kabul import check, contract, http, num, results, run_all

from semantic_bridge import kurul_kaynak as KK

B = "/api/v1/kurul"


def ok_or_skip(name: str, st: int, out: dict) -> bool:
    if st == 200:
        return True
    check(f"{name} · uç", None if st in (403, 404) else False, f"HTTP {st}: {str(out)[:160]}")
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    heavy = not ap.parse_args().skip_heavy
    ig = KK.NOT_RAKAM

    # ---------------------------------------------------------------- panel
    st, stat = http(f"{B}/status")
    donem = ((stat or {}).get("olcum") or {}).get("donem")
    if not donem:
        check("kurul /panel", None, "henüz ölçüm yok (ilk ölçümden sonra koşun)")
        st, p = 0, {}
    else:
        st, p = http(f"{B}/panel?donem={donem}", 900)
    if donem and ok_or_skip("kurul /panel", st, p):
        k = contract("kurul /panel", p, ig)
        got = run_all("kurul /panel", k, heavy)
        vals = {r.get("kod"): r for r in got.get("kurul.degerler") or []}
        flat = {g["kod"]: g for b in p.get("bolumler") or [] for g in b.get("gostergeler") or []}
        for kod, g in flat.items():
            if g.get("durum") != "ok":
                continue
            row = vals.get(kod)
            check(f"R1 kutu = değer satırı · {kod}", row is not None and abs(num(row.get("deger")) - num(g.get("deger"))) < 1e-6,
                  f"ekran {g.get('deger')} · sorgu {None if row is None else row.get('deger')}")
            if f"bolumler[].gostergeler[]:{kod}" not in (k.get("fields") or {}):
                check(f"K1 kutunun satıra özel kaydı · {kod}", False)
        net = flat.get("net_satis") or {}
        fin = [sid for sid in got if sid.startswith(f"kurul.m45.{donem}.portal.fin.satisYbd")]
        if net.get("durum") == "ok" and fin and got[fin[0]]:
            r0 = got[fin[0]][0]
            v = num(r0.get("net", list(r0.values())[2] if len(r0) > 2 else 0))
            same = abs(v - num(net["deger"])) < 0.01
            check("R2 «Net satış» kutusu = M45 portal sorgusu", True if same else None, f"sorgu {v:,.2f} · kutu {num(net['deger']):,.2f}")
        soz = flat.get("sozlesme_bitecek") or {}
        crm = [sid for sid in got if sid.startswith(f"kurul.m6.{donem}.")]
        if soz.get("durum") == "ok" and crm and got[crm[0]]:
            v = num(got[crm[0]][0].get("yaklasan"))
            check("R3 «Süresi yaklaşan sözleşme» = CRM sorgusu", True if v == num(soz["deger"]) else None,
                  f"sorgu {v:.0f} · kutu {num(soz['deger']):.0f}")
        missing_chain = [kod for kod, g in flat.items() if g.get("durum") == "ok"
                         and not (k.get("sources") or {}).get(f"kurul.deger.{kod}", {}).get("origin")]
        check("K1 hazır kutuların ölçüm zinciri kayıtlı", None if missing_chain else True,
              ("zinciri olmayan (bir sonraki ölçümden sonra dolar): " + ", ".join(missing_chain)) if missing_chain else "")
        for kod in [c for c, g in flat.items() if g.get("durum") == "ok"][:3]:
            st, d = http(f"{B}/indicators/{kod}?donem={donem}", 600)
            if ok_or_skip(f"kurul /indicators/{kod}", st, d):
                kd = contract(f"kurul /indicators/{kod}", d, ig)
                run_all(f"kurul /indicators/{kod}", {"sources": {s: v for s, v in (kd.get("sources") or {}).items()
                                                                 if v["connection"] == "portal"}}, heavy)

    st, cat = http(f"{B}/indicators")
    if ok_or_skip("kurul /indicators", st, cat):
        run_all("kurul /indicators", contract("kurul /indicators", cat, ig), heavy)

    # ---------------------------------------------------------------- aksiyonlar
    st, late = http(f"{B}/actions?durum=geciken")
    if ok_or_skip("kurul /actions geciken", st, late):
        k = contract("kurul /actions geciken", late, ig)
        got = run_all("kurul /actions geciken", k, heavy)
        rows = got.get("kurul.aksiyonlar")
        if rows is not None:
            today = date.today().isoformat()
            n = sum(1 for r in rows if r.get("durum") == "acik" and r.get("termin") and str(r["termin"])[:10] < today)
            check("R4 «Geciken kurul aksiyonu» = aksiyon sorgusu", n == num(late.get("total")), f"sorgu {n} · ekran {late.get('total')}")
    st, acts = http(f"{B}/actions?durum=hepsi")
    if ok_or_skip("kurul /actions hepsi", st, acts):
        run_all("kurul /actions hepsi", contract("kurul /actions hepsi", acts, ig), heavy)

    # ---------------------------------------------------------------- toplantılar
    st, ms = http(f"{B}/meetings")
    if ok_or_skip("kurul /meetings", st, ms):
        k = contract("kurul /meetings", ms, ig)
        got = run_all("kurul /meetings", k, heavy)
        counts = {list(r.values())[0]: num(list(r.values())[1]) for r in got.get("kurul.kararSayisi") or []}
        bad = [m["id"] for m in ms.get("items") or [] if num(m.get("kararSayisi")) != counts.get(m["id"], 0)]
        check("R5 toplantı karar sayısı = sayım sorgusu", not bad, ", ".join(bad[:5]))
        for m in (ms.get("items") or [])[:2]:
            st, mt = http(f"{B}/meetings/{m['id']}")
            if ok_or_skip("kurul /meetings/{id}", st, mt):
                run_all("kurul /meetings/{id}", contract("kurul /meetings/{id}", mt, ig), heavy)
            st, sg = http(f"{B}/meetings/{m['id']}/agenda/suggest")
            if ok_or_skip("kurul /meetings/{id}/agenda/suggest", st, sg):
                run_all("kurul /agenda/suggest", {"sources": {s: v for s, v in (contract("kurul /agenda/suggest", sg, ig)
                                                                                .get("sources") or {}).items()
                                                              if v["connection"] == "portal"}}, heavy)

    # ---------------------------------------------------------------- paketler
    st, pks = http(f"{B}/packages")
    if ok_or_skip("kurul /packages", st, pks):
        run_all("kurul /packages", contract("kurul /packages", pks, ig), heavy)
        for pk in (pks.get("items") or [])[:2]:
            st, x = http(f"{B}/packages/{pk['id']}")
            if not ok_or_skip("kurul /packages/{id}", st, x):
                continue
            k = contract("kurul /packages/{id}", x, ig)
            got = run_all("kurul /packages/{id}", {"sources": {s: v for s, v in (k.get("sources") or {}).items()
                                                               if v["connection"] == "portal"}}, heavy)
            rows = got.get("kurul.paket") or []
            if rows:
                frozen = json.loads(rows[0].get("icerik_json") or "{}")
                a = {g["kod"]: g.get("deger") for b in frozen.get("gostergeler") or [] for g in b.get("gostergeler") or []}
                s = {g["kod"]: g.get("deger") for b in (x.get("icerik") or {}).get("gostergeler") or [] for g in b.get("gostergeler") or []}
                check("R6 paket değerleri = paket kaydı (dondurulmuş içerik)", a == s, f"{len(s)} gösterge")
                check("K2 paketin sorgu kaydı ekrana gitmiyor", KK.K.QUERY_KEY not in (x.get("icerik") or {}))

    ok = sum(1 for _, st_, _ in results if st_ == "GEÇTİ")
    bad = sum(1 for _, st_, _ in results if st_ == "KALDI")
    warn = sum(1 for _, st_, _ in results if st_ == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
