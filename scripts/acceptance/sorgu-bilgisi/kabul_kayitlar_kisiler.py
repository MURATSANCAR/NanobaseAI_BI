"""Sorgu bilgisi kabulü — kayıtlar ve kişiler: M12 üretim (/uretim), M8 serbest çalışanlar (/serbest-calisanlar),
kişiler (/kisiler), M7 yazar ilişkileri (/yazar-iliskileri). Test sunucusunda, yan port köprüsüyle; yalnız GET, hiçbir
yere yazmaz (serbest çalışan önerisi POST olduğu için burada çağrılmaz; testte sınanır).

Her uçta K1–K3 (kabul.py ile aynı: kaynaksız rakam yok, kayıt tutarlı, her SQL gerçekten koşar) ve doğrudan SQL
referansları:
  R1  üretim: «N üretim kartı» = okumada çalışan CRM kart sorgusunun satırı (okuma kaydı) ve bugünkü satırı (okumadan
      sonra CRM'e kart girdiyse UYARI);
  R2  üretim: Logo baskı faturası sorgularının bugünkü satırı = okuma kaydındaki satır (sonradan fatura girdiyse UYARI);
  R3  kişiler: «N yazar» kartı = sayım sorgusunun «n» kolonu;
  R4  serbest çalışan: «Ödenecek» kartı = özet görev sorgusunda kabul edilmiş, hakedişe girmemiş satırların Σ miktar ×
      birim ücret;
  R5  serbest çalışan: hakediş listesi durum toplamları = hakediş sorgusunun Σ toplam kolonu (duruma göre);
  R6  yazar: «Havuzdaki aday» = kart sorgusunun «yazar» ve «vazgeçildi» dışındaki satır sayısı.

Ortam kabul.py ile aynı. Kullanım: python kabul_kayitlar_kisiler.py [--skip-heavy]
"""
from __future__ import annotations

import argparse
import urllib.parse
from datetime import date

from kabul import check, contract, http, num, results, run_all


def ok_or_skip(name: str, st: int, out) -> bool:
    if st == 200:
        return True
    check(name, None, f"HTTP {st} ({(out.get('detail') or {}) if isinstance(out, dict) else ''})"[:200])
    return False


def call(name: str, path: str, ignore, heavy: bool, timeout: int = 600):
    st, out = http(path, timeout)
    if not ok_or_skip(name, st, out):
        return None, None, {}
    k = contract(name, out, ignore)
    return out, k, run_all(name, k, heavy)


def q(v: str) -> str:
    return urllib.parse.quote(v, safe="")


def uretim(heavy: bool) -> None:
    from semantic_bridge import production_kaynak as K

    B = "/api/v1/editorial/production"
    ig = K.NOT_RAKAM
    ov, k, got = call("üretim /overview", B + "/overview", ig, heavy, 900)
    if ov:
        src = (k.get("sources") or {}).get("uretim.okuma.crm.kartlar")
        if src and (src.get("stats") or {}).get("rows") is not None:
            check("R1 üretim: «N üretim kartı» = okumadaki CRM kart sorgusu", num(ov.get("total")) == num(src["stats"]["rows"]),
                  f"ekran {ov.get('total')} · okuma {src['stats']['rows']}")
            if "uretim.okuma.crm.kartlar" in got:
                have = len(got["uretim.okuma.crm.kartlar"])
                check("R1 üretim: CRM kart sorgusu bugün", True if have == num(src["stats"]["rows"]) else None,
                      f"okuma {src['stats']['rows']} · bugün {have}")
        else:
            check("üretim okuma sorguları kayıtlı", None, "bu sürümden sonraki ilk okumada (5 dakikada bir) kaydedilir")
        for sid, s in (k.get("sources") or {}).items():
            if sid.startswith("uretim.okuma.logo.faturalar.") and sid in got and (s.get("stats") or {}).get("rows") is not None:
                have, want = len(got[sid]), s["stats"]["rows"]
                check(f"R2 {sid}: satır = okuma kaydı", True if have == want else None, f"okuma {want} · bugün {have}")
    lst, _, _ = call("üretim /cards", B + "/cards?durum=hepsi", ig, heavy)
    for path in ("/delays", "/printers", "/meta", f"/calendar?publication={date.today().replace(day=1).isoformat()}"):
        call(f"üretim {path.split('?')[0]}", B + path, ig, heavy)
    cid = next((c["id"] for c in (lst or {}).get("items") or []), None)
    if cid:
        call("üretim /cards/{id}", f"{B}/cards/{q(cid)}", ig, heavy)


def kisiler(heavy: bool) -> None:
    from semantic_bridge import contributors_kaynak as K

    B = "/api/v1/editorial/contributors"
    ig = K.NOT_RAKAM
    out, k, got = call("kişiler /contributors (yazar)", f"{B}?roles=Yazar&order=son&page=0", ig, heavy)
    if out and got.get("kisiler.sayim"):
        n = num(got["kisiler.sayim"][0].get("n"))
        check("R3 kişiler: «N yazar» = sayım sorgusu", n == num(out.get("total")), f"sorgu {n:,.0f} · ekran {out.get('total')}")
    call("kişiler /contributors (çizer ve serbest)", f"{B}?roles={q('Çizer|Kapak Tasarım|Mizanpaj Yapan|Redaktör')}&page=0", ig, heavy)
    call("kişiler /contributors/roles", f"{B}/roles", ig, heavy)
    pid = next((i["id"] for i in (out or {}).get("items") or []), None)
    if pid:
        call("kişiler /contributors/{id}", f"{B}/{q(pid)}", ig, heavy)


def serbest(heavy: bool) -> None:
    from semantic_bridge import freelance_kaynak as K

    B = "/api/v1/editorial/freelance"
    ig = K.NOT_RAKAM
    ov, _, got = call("serbest /overview", B + "/overview", ig, heavy)
    rows = got.get("serbest.ozet.gorevler")
    if ov and rows is not None:
        total = sum(num(r.get("units")) * num(r.get("unit_price")) for r in rows
                    if r.get("status") == "onaylandi" and not r.get("payout_id"))
        check("R4 serbest: «Ödenecek» = özet görev sorgusu Σ miktar × birim ücret", abs(total - num(ov.get("payable"))) < 0.01,
              f"sorgu {total:,.2f} · ekran {num(ov.get('payable')):,.2f}")
    people, _, _ = call("serbest /people", B + "/people?status=aktif", ig, heavy)
    person = next(iter((people or {}).get("items") or []), None)
    if person:
        call("serbest /people/{id}", f"{B}/people/{q(person['id'])}", ig, heavy)
    card = next((p for p in (people or {}).get("items") or [] if p.get("logoCard")), None)
    if card:
        call("serbest /people/{id}/logo", f"{B}/people/{q(card['id'])}/logo", ig, heavy)
    else:
        check("serbest Logo hareketleri", None, "Logo cari kodu girilmiş kişi yok; bu uç sınanmadı")
    pk, _, _ = call("serbest /packages", B + "/packages?status=", ig, heavy)
    pid = next((p["id"] for p in (pk or {}).get("items") or []), None)
    if pid:
        call("serbest /packages/{id}", f"{B}/packages/{q(pid)}", ig, heavy)
    call("serbest /capacity", B + "/capacity?weeks=8", ig, heavy)
    call("serbest /payable", B + "/payable", ig, heavy)
    pays, _, got = call("serbest /payouts", B + "/payouts", ig, heavy)
    rows = got.get("serbest.hakedisler")
    if pays and rows is not None:
        for s, v in (pays.get("totals") or {}).items():
            sql = sum(num(r.get("total")) for r in rows if r.get("status") == s)
            check(f"R5 serbest: «{s}» toplamı = hakediş sorgusu", abs(sql - num(v)) < 0.01, f"sorgu {sql:,.2f} · ekran {num(v):,.2f}")
    hid = next((h["id"] for h in (pays or {}).get("items") or []), None)
    if hid:
        call("serbest /payouts/{id}", f"{B}/payouts/{q(hid)}", ig, heavy)
    call("serbest /inbox", B + "/inbox", ig, heavy)


def yazar(heavy: bool) -> None:
    from semantic_bridge import author_kaynak as K
    from semantic_bridge import author_relations as R

    B = "/api/v1/editorial/authors"
    ig = K.NOT_RAKAM
    cards, _, got = call("yazar /cards", B + "/cards", ig, heavy)
    rows = got.get("yazar.kartlar")
    if cards and rows is not None:
        sql = sum(1 for r in rows if r.get("stage") in R.POOL_STAGES and r.get("stage") != "vazgecildi")
        screen = sum(n for s, n in (cards.get("stages") or {}).items() if s != "vazgecildi")
        check("R6 yazar: «Havuzdaki aday» = kart sorgusu", sql == screen, f"sorgu {sql} · ekran {screen}")
    call("yazar /agenda", B + "/agenda?scope=hepsi&days=30", ig, heavy)
    call("yazar /reminders/me", B + "/reminders/me", ig, heavy)
    call("yazar /pool/crm", B + "/pool/crm?page=0", ig, heavy)
    hm, _, _ = call("yazar /heatmap", B + "/heatmap?scope=hepsi&order=soguk&page=0", ig, heavy, 900)
    cid = next((c["id"] for c in (cards or {}).get("items") or []), None)
    if cid:
        call("yazar /cards/{id}", f"{B}/cards/{q(cid)}", ig, heavy)
    crm = next((r["crmContactId"] for r in (hm or {}).get("items") or [] if r.get("crmContactId")), None)
    if crm:
        call("yazar /by-crm/{id}", f"{B}/by-crm/{q(crm)}", ig, heavy)
        call("yazar /related/{id}", f"{B}/related/{q(crm)}?page=0", ig, heavy)
        call("yazar /growth/{id}", f"{B}/growth/{q(crm)}", ig, heavy, 900)
        call("yazar /advice/{id}", f"{B}/advice/{q(crm)}", ig, heavy)
        name = next((r["name"] for r in (hm or {}).get("items") or [] if r.get("crmContactId") == crm), "")
        if name:
            call("yazar /similar", f"{B}/similar?name={q(name)}", ig, heavy)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    heavy = not ap.parse_args().skip_heavy
    uretim(heavy)
    kisiler(heavy)
    serbest(heavy)
    yazar(heavy)
    ok = sum(1 for _, s, _ in results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in results if s == "KALDI")
    warn = sum(1 for _, s, _ in results if s == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
