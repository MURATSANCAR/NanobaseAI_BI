"""SEO & GEO ekran hızı kabulü (2026-09-29; test sunucusu, yan port köprüsü; yalnız okuma, hiçbir yere yazmaz).

Her yavaş uç «Verileri yenile» başlığıyla (`X-Data-Refresh: 1`, hazır cevap atlanır) iki kez çağrılır:
  H1  ikinci çağrı (hazır hesap güncel) 1,5 sn altında; ilk çağrının süresi de yazılır (girdi değiştiyse hesap
      o çağrıda yapılır — gece ısıtması sonrası o da hızlı olmalı);
  H2  iki çağrının cevabı aynı (kaynaklar hariç);
  H3  cevapta sorgu bilgisi var, kaynaksız rakam yok; hazır kaydı okuyan sorgunun kökeni kayıtlı.
Doğrudan SQL referansları (portal veritabanı):
  R1  ürünler «toplam» = aktif ürün sayısı;
  R2  ürünler ilk sayfanın sırası = eski sıralama sorgusu (satış, görüntülenme JSON'dan; puan; ürün no);
  R3  genel bakış «T-soft ürünü» ve «Düzeltilmesi gereken» = doğrudan sayım;
  R4  sorgu–sayfa «toplam» (hepsi) = fırsat kırılımında toplam gösterimi ≥ 30 olan farklı arama sayısı;
  R5  sayfalar (yazar) «toplam» = model türündeki site sayfası sayısı;
  R6  okur yorumları «aktif kitap» = aktif ürün sayısı;
  R7  hazır kayıtlar: ısıtılan her hesabın satırı var, hesap süresi yazılı.

Ortam `sorgu-bilgisi/kabul.py` ile aynı: BASE, COOKIE, SEMANTIC_STORE_DSN, PYTHONPATH=<ağaç>/backend.
Temizlik gerekmez: betik hiçbir tabloya yazmaz (hazır kayıtlar uygulamanın kendi durumudur, test verisi değil).
Kullanım: python kabul_seo_hiz.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sorgu-bilgisi"))

import kabul as KB  # noqa: E402

PATHS = ["keymap?kind=hepsi&brand=", "guides/topics", "authors-trust", "pages?type=model", "overview", "cannibal", "faq",
         "reviews", "bios", "products"]
LIMIT_MS = 1500


def fresh(path: str, timeout: int = 900):
    req = urllib.request.Request(KB.BASE + "/api/v1/seo-geo/" + path, headers=KB.headers({"X-Data-Refresh": "1"}))
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read() or b"{}")
            return r.status, body, int((time.monotonic() - t) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, {}, int((time.monotonic() - t) * 1000)


def strip(d):
    """Karşılaştırmada rakam olmayan canlı alanlar (sorgu bilgisi, arka plan işlerinin durumu) atılır."""
    if isinstance(d, dict):
        return {k: strip(v) for k, v in d.items() if k not in ("kaynaklar", "run", "state", "sync", "batch")}
    if isinstance(d, list):
        return [strip(v) for v in d]
    return d


def main() -> None:
    out: dict[str, dict] = {}
    for p in PATHS:
        st1, a, ms1 = fresh(p)
        st2, b, ms2 = fresh(p)
        if st1 != 200 or st2 != 200:
            KB.check(f"/{p}", False, f"HTTP {st1}/{st2}")
            continue
        out[p] = b
        KB.check(f"H1 /{p} ikinci çağrı < {LIMIT_MS} ms", ms2 < LIMIT_MS, f"ilk {ms1} ms · ikinci {ms2} ms")
        KB.check(f"H2 /{p} iki cevap aynı", strip(a) == strip(b))
        k = KB.contract(f"H3 /{p}", b)
        hz = [s for s in (k.get("sources") or {}).values() if "semantic_seo_hazir" in s.get("sql", "")]
        KB.check(f"H3 /{p} hazır kaydın kökeni", bool(hz) and all(s.get("origin") for s in hz),
                 f"{len(hz)} hazır okuması")

    with KB.portal().connect() as c:
        active = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_products WHERE active = true")).scalar() or 0
        total = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_products")).scalar() or 0
        failing = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_products WHERE active = true AND score < 70")).scalar() or 0
        first = [r[0] for r in c.execute(sa.text(
            "SELECT product_id FROM semantic_seo_products WHERE active = true ORDER BY "
            "COALESCE(CAST(NULLIF(regexp_replace(CAST(data_json AS json) ->> 'CountTotalSales', '[^0-9.]', '', 'g'), '') AS float), 0) DESC, "
            "COALESCE(CAST(NULLIF(regexp_replace(CAST(data_json AS json) ->> 'StatViews', '[^0-9.]', '', 'g'), '') AS float), 0) DESC, "
            "score ASC, product_id LIMIT 50"))]
        queries = c.execute(sa.text(
            "SELECT COUNT(*) FROM (SELECT r -> 'keys' ->> 0 AS q FROM semantic_seo_opps o, "
            "json_array_elements(CAST(o.rows_json AS json)) r WHERE o.kind = 'query_page' "
            "AND json_array_length(r -> 'keys') >= 2 AND COALESCE(r -> 'keys' ->> 1, '') <> '' "
            "GROUP BY 1 HAVING SUM(COALESCE(CAST(r ->> 'impressions' AS float), 0)) >= 30) x")).scalar() or 0
        model_pages = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_links WHERE type = 'model'")).scalar() or 0
        hazir = {r[0]: r[1] for r in c.execute(sa.text("SELECT name, compute_ms FROM semantic_seo_hazir"))}

    if "products" in out:
        KB.check("R1 ürünler toplam = aktif ürün sayısı", int(out["products"]["total"]) == int(active),
                 f"{out['products']['total']} · {active}")
        got = [i["id"] for i in out["products"]["items"]]
        KB.check("R2 ürünler ilk sayfa sırası = eski sıralama sorgusu", got == first[:len(got)], f"{got[:5]} · {first[:5]}")
    if "overview" in out:
        o = out["overview"]
        KB.check("R3 genel bakış ürün ve 70 altı = doğrudan sayım",
                 int(o["products"]) == int(total) and int(o["failing"]) == int(failing),
                 f"{o['products']}/{o['failing']} · {total}/{failing}")
    key = "keymap?kind=hepsi&brand="
    if key in out and out[key].get("ready"):
        KB.check("R4 sorgu–sayfa toplam = ≥30 gösterimli farklı arama", int(out[key]["total"]) == int(queries),
                 f"{out[key]['total']} · {queries}")
    if "pages?type=model" in out:
        KB.check("R5 yazar sayfaları toplam = model sayfası sayısı", int(out["pages?type=model"]["total"]) == int(model_pages),
                 f"{out['pages?type=model']['total']} · {model_pages}")
    if "reviews" in out:
        KB.check("R6 yorumlar aktif kitap = aktif ürün", int(out["reviews"]["summary"]["activeBooks"]) == int(active),
                 f"{out['reviews']['summary']['activeBooks']} · {active}")
    want = {"keymap", "guides.topics", "authors.trust", "pages", "overview.products", "cannibal", "faq.list", "reviews",
            "bios.authors", "products.order", "crm.summary"}
    KB.check("R7 hazır kayıtlar", want <= set(hazir), ", ".join(f"{k}={v} ms" for k, v in sorted(hazir.items())))

    ok = sum(1 for _, s, _ in KB.results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in KB.results if s == "KALDI")
    warn = sum(1 for _, s, _ in KB.results if s == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
