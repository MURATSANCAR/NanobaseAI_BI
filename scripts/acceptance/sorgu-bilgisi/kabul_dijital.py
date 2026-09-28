"""Sorgu bilgisi kabulü — M36 Dijital yayın ve e-kitap (/dijital-yayin, /kitap/:id, /firsatlar, /satis). Test sunucusunda,
yan port köprüsüyle; yalnız okuma, hiçbir yere yazmaz.

Her uçta K1–K3 (kabul.py ile aynı: kaynaksız rakam yok, kayıt tutarlı, her SQL gerçekten koşar) ve doğrudan SQL
referansları:
  R1  «Dijitalde» kartı = kartın portal sayım sorgusunun sonucu;
  R2  «Hak riski» kartı = /rights-risks listesindeki risk satırı sayısı (rozet ile sekme aynı kural);
  R3  katalog «N kitap» = sayım sorgusunun sonucu;
  R4  CRM sözleşme sayıları (new_EKitap, new_SesliKitapHakki, new_iletimhakki; yalnız Telif Alış) = okumada çalışan CRM
      sorgusunun bugünkü sonucu (okumadan sonra CRM değiştiyse UYARI);
  R5  Logo satış sorgularının bugünkü satırı = okuma kaydındaki satır (okumadan sonra Logo'ya fatura girdiyse UYARI);
  R6  satış panosu Σ net TL = aylık sorgunun Σ net TL kolonu.

Ortam kabul.py ile aynı. Kullanım: python kabul_dijital.py [--skip-heavy]
"""
from __future__ import annotations

import argparse
import urllib.parse

from kabul import check, contract, http, num, results, run_all


def ok_or_skip(name: str, st: int, out: dict) -> bool:
    if st == 200:
        return True
    check(name, None, f"HTTP {st} ({(out.get('detail') or {}) if isinstance(out, dict) else ''})"[:200])
    return False


def first_value(rows) -> float:
    return num(list(rows[0].values())[0]) if rows else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    heavy = not ap.parse_args().skip_heavy
    from semantic_bridge import dijital_kaynak as K

    ig = K.NOT_RAKAM
    B = "/api/v1/dijital"

    st, meta = http(B + "/meta", 120)
    if ok_or_skip("dijital /meta", st, meta):
        run_all("dijital /meta", contract("dijital /meta", meta, ig), heavy)

    st, ov = http(B + "/overview", 300)
    if ok_or_skip("dijital /overview", st, ov):
        k = contract("dijital /overview", ov, ig)
        got = run_all("dijital /overview", k, heavy)
        rows = got.get("dijital.kpi.dijitalde")
        if rows is not None:
            check("R1 «Dijitalde» kartı = sayım sorgusu", first_value(rows) == num(ov["kpi"]["dijitalde"]),
                  f"sorgu {first_value(rows):,.0f} · kart {ov['kpi']['dijitalde']}")
        counts = [sid for sid in got if sid.startswith("dijital.okuma.crm.sozlesmeSayilari")]
        if counts and got[counts[0]]:
            today = got[counts[0]][0]
            same = all(num(today.get(c)) == num((ov.get("sozlesme") or {}).get(c)) for c in ("yururlukte", "ekitap", "sesli", "iletim", "notlu"))
            check("R4 CRM sözleşme sayıları = okumadaki CRM sorgusu", True if same else None,
                  f"bugün {dict((c, today.get(c)) for c in ('yururlukte', 'ekitap', 'sesli', 'iletim', 'notlu'))} · "
                  f"okuma {ov.get('sozlesme')}")
        for sid, src in (k.get("sources") or {}).items():
            if sid.startswith("dijital.okuma.logo.satis.") and sid in got and (src.get("stats") or {}).get("rows") is not None:
                have, want = len(got[sid]), src["stats"]["rows"]
                check(f"R5 {sid}: satır = okuma kaydı", True if have == want else None, f"okuma {want} · bugün {have}")
        if not any(sid.startswith("dijital.okuma.") for sid in k.get("sources") or {}):
            check("dijital okuma sorguları kayıtlı", None, "bu sürümden sonraki ilk okumada kaydedilir («Yeniden oku» ya da 04:00)")

    st, risk = http(B + "/rights-risks", 300)
    if ok_or_skip("dijital /rights-risks", st, risk):
        run_all("dijital /rights-risks", contract("dijital /rights-risks", risk, ig), heavy)
        if ov:
            check("R2 «Hak riski» kartı = risk listesi", num((ov.get("kpi") or {}).get("hakRiski")) == len(risk.get("risk") or []),
                  f"kart {(ov.get('kpi') or {}).get('hakRiski')} · liste {len(risk.get('risk') or [])}")

    st, lst = http(B + "/titles?page=0", 300)
    if ok_or_skip("dijital /titles", st, lst):
        got = run_all("dijital /titles", contract("dijital /titles", lst, ig), heavy)
        rows = got.get("dijital.katalogToplam")
        if rows is not None:
            check("R3 katalog «N kitap» = sayım sorgusu", first_value(rows) == num(lst.get("total")),
                  f"sorgu {first_value(rows):,.0f} · ekran {lst.get('total')}")
        kid = next((i["kitapId"] for i in lst.get("items") or []), None)
        if kid:
            st, t = http(f"{B}/titles/{urllib.parse.quote(kid)}", 300)
            if ok_or_skip("dijital /titles/{id}", st, t):
                run_all("dijital /titles/{id}", contract("dijital /titles/{id}", t, ig), heavy)

    for tur in ("ekitap", "sesli"):
        st, opp = http(f"{B}/opportunities?tur={tur}", 300)
        if ok_or_skip(f"dijital /opportunities {tur}", st, opp):
            run_all(f"dijital /opportunities {tur}", contract(f"dijital /opportunities {tur}", opp, ig), heavy)

    for path in ("/crm-pending?durum=hepsi", "/platforms"):
        st, out = http(B + path, 120)
        if ok_or_skip(f"dijital {path}", st, out):
            run_all(f"dijital {path}", contract(f"dijital {path}", out, ig), heavy)

    st, imps = http(B + "/imports", 120)
    if ok_or_skip("dijital /imports", st, imps):
        run_all("dijital /imports", contract("dijital /imports", imps, ig), heavy)
        iid = next((i["id"] for i in imps.get("items") or []), None)
        if iid:
            st, imp = http(f"{B}/imports/{urllib.parse.quote(iid)}", 300)
            if ok_or_skip("dijital /imports/{id}", st, imp):
                run_all("dijital /imports/{id}", contract("dijital /imports/{id}", imp, ig), heavy)

    st, sales = http(B + "/sales", 300)
    if ok_or_skip("dijital /sales", st, sales):
        got = run_all("dijital /sales", contract("dijital /sales", sales, ig), heavy)
        rows = got.get("dijital.satisAylik")
        if rows is not None:
            sql_net = sum(num(list(r.values())[3]) for r in rows)   # sales_stmts aylik: dönem, platform, Σ adet, Σ net TL, sayı
            screen = sum(num(r.get("netTl")) for r in sales.get("aylik") or [])
            check("R6 satış: Σ net TL = aylık sorgu", abs(sql_net - screen) < 0.01, f"sorgu {sql_net:,.2f} · ekran {screen:,.2f}")

    ok = sum(1 for _, s, _ in results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in results if s == "KALDI")
    warn = sum(1 for _, s, _ in results if s == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
