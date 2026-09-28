"""Kategori ağacı: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Ekran portal tablolarından (semantic_book_profiles, semantic_category_*) okur; tabloları gece eşitlemesi doldurur
(`timas-categories.timer` → `categories_api.sync()`): CRM kitap kartları ve sınıflama bağları (`books_sql`, `link_sql`,
`vocab_sql`) ve Logo son N ayın net satış adedi (`priority_sql`, yıl başına kendi firma kopyasıyla). Uçta koşan portal
okumaları `sorgu_izi` ile yakalanır; asıl CRM/Logo metni eşitlemenin kaydettiği şema, firma ve pencereyle aynı
fonksiyonlardan kurulur ve portal okumasının kökeni olarak yazılır. Site ürün sayısı SEO eşitlemesinin portal
kopyasındandır.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from semantic_bridge import categories as C
from semantic_bridge import categories_sources as src
from semantic_bridge import provenance as P

F_OZET = ("Özet: aktif kitap = CRM'de aktif kitap kartları; ağaçta yeri olan = yürürlükteki ağaçta düğümü olan profil; "
          "onaylı profil ve oranı profil durumundan; satıştaki kitap = son N ayda net satışı olan (Logo); açık "
          "tutarsızlık = kuralların açık bulguları; bağ sayıları CRM çoka-çok sınıflamalarından; site ürün sayısı SEO "
          "eşitlemesinin ürün kopyasından; CRM farkı = onaylı profil ile CRM kartı arasındaki fark satırları.")
F_KUYRUK = ("Kuyruk: öncelik = kitabın son N ayda net satış adedi (Logo faturalı satış − iade, yıl başına kendi firma "
            "kopyasıyla), büyükten küçüğe; sayfalama toplamı süzgece uyan kitap sayısı.")
F_AGAC = ("Ağaç: düğüm başına kitap = düğüme yerleşen profiller; onaylı = onaylı profiller; son dönem net satış = o "
          "kitapların son N ay net adedi (Logo). Etki önizlemesi taslak ağaç ile yürürlükteki ağacın farkıdır.")
F_BULGU = "Tutarsızlıklar: kural başına açık bulgu sayısı; satırdaki öncelik kitabın son N ay net satış adedi (Logo)."
F_FARK = "CRM farkı: onaylı profili CRM kartından farklı kitap ve satır sayısı; «N günden eski» farkın yaşı."
F_ETIKET = "Etiketler: durum başına etiket sayısı; «N kitapta» = CRM anahtar kelime bağlarının kitap sayısı."
F_KITAP = ("Kitap profili: son 24 ay net satış adedi Logo'dan (öncelik); öneri olasılıkları öneriyi üreten modelin "
           "seçim olasılığıdır (sayı modelin seçim ölçüsü, değer üretmez); geçmiş profil olay kaydından.")


def origin(k: P.Kaynaklar, engine: Any, tenant: str, logo_db: Optional[str], crm_db: Optional[str], *,
           crm: bool = True, logo: bool = True) -> list[str]:
    """Portal tablolarını dolduran eşitlemenin asıl CRM ve Logo sorguları."""
    info = C.meta_get(engine, tenant, "sync", {}) or {}
    ids: list[str] = []
    schema = (info.get("crm") or {}).get("schema")
    at = info.get("at")
    if crm and schema:
        ids.append(k.sorgu("crm.kategori.kitaplar", "CRM aktif kitap kartları", "crm", src.books_sql(schema),
                           database=crm_db, rows=(info.get("crm") or {}).get("books"), ran_at=at,
                           ms=(info.get("crm") or {}).get("ms")))
        for key in src.LINKS:
            ids.append(k.sorgu(f"crm.kategori.bag.{key}", f"CRM sınıflama bağları · {key}", "crm",
                               src.link_sql(schema, key), database=crm_db, ran_at=at))
    lg = info.get("logo") or {}
    if logo and lg.get("firms") and lg.get("start") and lg.get("end"):
        start, end = date.fromisoformat(lg["start"]), date.fromisoformat(lg["end"])
        for y in lg.get("years") or []:
            firm = (lg.get("firms") or {}).get(str(y))
            if not firm:
                continue
            a = max(start, date(int(y), 1, 1))
            b = min(end + timedelta(days=1), date(int(y) + 1, 1, 1))
            ids.append(k.sorgu(f"logo.kategori.oncelik.{y}", f"Logo net satış adedi · {y}", "logo",
                               src.priority_sql(firm, a, b), database=logo_db, ran_at=at, data_end=lg.get("end"),
                               period=f"{a.isoformat()} – {(b - timedelta(days=1)).isoformat()} · Logo firma {firm}",
                               description="Kitap önceliği (son N ay net adet) bu okumadan; eşitlemede portala yazılır."))
    if not ids:
        ids.append(k.hesap("esitleme-bekliyor", "Portal tablolarının son eşitlemesi, asıl sorguları kaydetmeye "
                                                "başlamadan önce yapıldı; CRM ve Logo sorguları bir sonraki gece "
                                                "eşitlemesinde yazılır.", dis="Kategori ağacı gece eşitlemesi"))
    return ids
