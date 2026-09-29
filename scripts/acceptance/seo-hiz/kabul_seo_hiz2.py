"""SEO & GEO ekran hızı kabulü, 2. tur (2026-09-29; test sunucusu, yan port köprüsü; yalnız okuma, hiçbir yere yazmaz).

Her uç «Verileri yenile» başlığıyla (`X-Data-Refresh: 1`, hazır cevap atlanır) iki kez çağrılır:
  H0  ilk çağrı da 1,5 sn altında (köprü açılış ısıtması / gece ısıtması sonrası kayıt hazır olmalı; değilse UYARI —
      girdi az önce değiştiyse o çağrı hesabı yapar);
  H1  ikinci çağrı 1,5 sn altında;
  H2  iki çağrının cevabı aynı (kaynaklar ve arka plan iş durumları hariç);
  H3  cevapta sorgu bilgisi var, kaynaksız rakam yok; hazır kaydı okuyan sorgunun kökeni kayıtlı.
Doğrudan SQL referansları (portal veritabanı):
  R1  alışveriş «ürün» = aktif ürün sayısı;
  R2  CRM listesi toplam = aktif ürün; ilk sayfa sırası = eski sorgu (satış, görüntülenme JSON'dan; ürün no);
  R3  CRM «eşleşmedi» toplamı = eski birleşim sorgusu (barkodla CRM kartı yok);
  R4  Google taraması «toplam» ve adres listesi toplamı = denetim kaydı sayısı;
  R5  Google Kitaplar toplamı = aktif ürün sayısı;
  R6  fırsat (yakın sıra, marka dahil) toplamı = sorgu+sayfa kırılımında sırası 4–15 ve gösterimi > 0 satır;
  R7  site içi bağlantılar «teknik tarama sayfası» = teknik tarama kaydı sayısı;
  R8  hazır kayıtlar: 2. turun bütün hesaplarının satırı var, hesap süresi yazılı.

Ortam `sorgu-bilgisi/kabul.py` ile aynı: BASE, COOKIE, SEMANTIC_STORE_DSN, PYTHONPATH=<ağaç>/backend.
Temizlik gerekmez: betik hiçbir tabloya yazmaz.
Kullanım: python kabul_seo_hiz2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sorgu-bilgisi"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kabul as KB  # noqa: E402
from kabul_seo_hiz import LIMIT_MS, fresh, strip  # noqa: E402

PATHS = ["links?view=orphans", "overview", "opportunities?kind=yakin&brand=", "entity", "entity/google-books", "crawlbot",
         "crawlbot/urls", "faq", "crm", "crm?filter=eslesmedi", "shopping"]
SALES = ("COALESCE(CAST(NULLIF(regexp_replace(CAST(p.data_json AS json) ->> 'CountTotalSales', '[^0-9.]', '', 'g'), '') "
         "AS float), 0)")
VIEWS = ("COALESCE(CAST(NULLIF(regexp_replace(CAST(p.data_json AS json) ->> 'StatViews', '[^0-9.]', '', 'g'), '') "
         "AS float), 0)")
EAN = "regexp_replace(COALESCE(CAST(p.data_json AS json) ->> 'Barcode', ''), '[^0-9]', '', 'g')"


def main() -> None:
    out: dict[str, dict] = {}
    for p in PATHS:
        st1, a, ms1 = fresh(p)
        st2, b, ms2 = fresh(p)
        if st1 != 200 or st2 != 200:
            KB.check(f"/{p}", False, f"HTTP {st1}/{st2}")
            continue
        out[p] = b
        KB.check(f"H0 /{p} ilk çağrı < {LIMIT_MS} ms", True if ms1 < LIMIT_MS else None, f"ilk {ms1} ms")
        KB.check(f"H1 /{p} ikinci çağrı < {LIMIT_MS} ms", ms2 < LIMIT_MS, f"ilk {ms1} ms · ikinci {ms2} ms")
        KB.check(f"H2 /{p} iki cevap aynı", strip(a) == strip(b))
        k = KB.contract(f"H3 /{p}", b)
        hz = [s for s in (k.get("sources") or {}).values() if "semantic_seo_hazir" in s.get("sql", "")]
        KB.check(f"H3 /{p} hazır kaydın kökeni", bool(hz) and all(s.get("origin") for s in hz), f"{len(hz)} hazır okuması")

    with KB.portal().connect() as c:
        active = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_products WHERE active = true")).scalar() or 0
        first = [r[0] for r in c.execute(sa.text(
            f"SELECT p.product_id FROM semantic_seo_products p WHERE p.active = true "
            f"ORDER BY {SALES} DESC, {VIEWS} DESC, p.product_id LIMIT 50"))]
        unmatched = c.execute(sa.text(
            f"SELECT COUNT(*) FROM semantic_seo_products p LEFT JOIN semantic_seo_crm_books b "
            f"ON b.tenant_id = p.tenant_id AND b.ean = {EAN} WHERE p.active = true AND b.ean IS NULL")).scalar() or 0
        inspected = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_inspect")).scalar() or 0
        near = c.execute(sa.text(
            "SELECT COUNT(*) FROM semantic_seo_opps o, json_array_elements(CAST(o.rows_json AS json)) r "
            "WHERE o.kind = 'query_page' AND COALESCE(CAST(r ->> 'impressions' AS float), 0) > 0 "
            "AND COALESCE(CAST(r ->> 'position' AS float), 0) BETWEEN 4 AND 15")).scalar() or 0
        has_opps = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_opps WHERE kind = 'query_page'")).scalar() or 0
        tech = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_tech")).scalar() or 0
        hazir = {r[0]: r[1] for r in c.execute(sa.text("SELECT name, compute_ms FROM semantic_seo_hazir"))}

    if "shopping" in out:
        n = out["shopping"]["summary"]["products"]
        KB.check("R1 alışveriş ürün = aktif ürün", int(n) == int(active), f"{n} · {active}")
    if "crm" in out:
        got = [i["id"] for i in out["crm"]["items"]]
        KB.check("R2 CRM listesi toplam = aktif ürün", int(out["crm"]["total"]) == int(active), f"{out['crm']['total']} · {active}")
        KB.check("R2 CRM listesi ilk sayfa sırası = eski sorgu", got == first[:len(got)], f"{got[:5]} · {first[:5]}")
    if "crm?filter=eslesmedi" in out:
        n = out["crm?filter=eslesmedi"]["total"]
        KB.check("R3 CRM eşleşmedi = eski birleşim sorgusu", int(n) == int(unmatched), f"{n} · {unmatched}")
    if "crawlbot" in out:
        n = out["crawlbot"]["inspect"]["total"]
        KB.check("R4 Google taraması toplam = denetim kaydı", int(n) == int(inspected), f"{n} · {inspected}")
    if "crawlbot/urls" in out:
        n = out["crawlbot/urls"]["total"]
        KB.check("R4 adres listesi toplam = denetim kaydı", int(n) == int(inspected), f"{n} · {inspected}")
    if "entity/google-books" in out:
        n = out["entity/google-books"]["total"]
        KB.check("R5 Google Kitaplar toplam = aktif ürün", int(n) == int(active), f"{n} · {active}")
    key = "opportunities?kind=yakin&brand="
    if key in out and has_opps:
        n = out[key]["total"]
        KB.check("R6 fırsat yakın sıra toplam = kırılımda 4–15. sıra", int(n) == int(near), f"{n} · {near}")
    if "links?view=orphans" in out:
        n = out["links?view=orphans"]["summary"]["techPages"]
        KB.check("R7 bağlantılar teknik tarama sayfası = tarama kaydı", int(n) == int(tech), f"{n} · {tech}")
    want = {"links", "opportunities", "opportunities.products", "entity", "crawlbot.products", "crawlbot.rows", "shopping",
            "crm.rows", "overview.products", "crm.summary", "faq.list"}
    KB.check("R8 hazır kayıtlar", want <= set(hazir),
             "eksik: " + ", ".join(sorted(want - set(hazir))) + " · " + ", ".join(f"{k}={v} ms" for k, v in sorted(hazir.items())))

    ok = sum(1 for _, s, _ in KB.results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in KB.results if s == "KALDI")
    warn = sum(1 for _, s, _ in KB.results if s == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
