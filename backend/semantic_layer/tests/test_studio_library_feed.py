"""Kapak arşivi beslemesi: T-soft ürünü + CRM kartı → arşiv kaydı (semantic_bridge/editorial_studio_library.py)."""
from semantic_bridge import editorial_studio_library as F

SITE = "https://timas.com.tr"


def product(**kw):
    base = {"ProductId": "123", "ProductName": "Dilek Ağacı", "Model": "Ayşe Yazar", "Barcode": "9786050000000",
            "Brand": "Timaş Çocuk", "DefaultCategoryPath": "Çocuk Kitapları > Masal",
            "DefaultCategoryName": "Resimli Masal", "IsActive": "true", "CountTotalSales": "42",
            "SeoLink": "dilek-agaci", "ImageUrls": [{"Small": "https://cdn/s.jpg", "Big": "https://cdn/b.jpg"}]}
    return {**base, **kw}


def test_category_path_joins_path_and_leaf_without_repeats():
    assert F.category_path(product()) == ["Çocuk Kitapları", "Masal", "Resimli Masal"]
    assert F.category_path(product(DefaultCategoryPath="", DefaultCategoryName="Tarih")) == ["Tarih"]
    assert F.category_path(product(DefaultCategoryPath="Tarih", DefaultCategoryName="Tarih")) == ["Tarih"]
    assert F.category_path(product(DefaultCategoryPath=None, DefaultCategoryName=None)) == []


def test_image_url_prefers_largest_and_resolves_relative():
    assert F.image_url(product(), SITE) == "https://cdn/b.jpg"
    assert F.image_url(product(ImageUrls=[], ImageUrl="kapak.jpg"), SITE) == "https://timas.com.tr/kapak.jpg"
    assert F.image_url(product(ImageUrls=["//cdn/x.jpg"]), SITE) == "https://cdn/x.jpg"
    assert F.image_url(product(ImageUrls=[], ImageUrl=""), SITE) is None


def test_item_takes_people_and_audience_from_crm_card():
    crm = {"authors": "Ayşe Yazar, İkinci Yazar", "illustrators": "Çizer Bir", "audience": "Çocuk",
           "ageFrom": 5, "ageTo": 8, "genres": "Masal,Resimli Kitap", "isbn": "978-605-00-0000-0"}
    it = F.item(product(), crm, SITE)
    assert it["id"] == "tsoft-123" and it["title"] == "Dilek Ağacı"
    assert it["authors"] == ["Ayşe Yazar", "İkinci Yazar"] and it["illustrators"] == ["Çizer Bir"]
    assert it["audience"] == "CHILD" and (it["age_from"], it["age_to"]) == (5, 8)
    assert it["genres"] == ["Masal", "Resimli Kitap"]
    assert it["page_url"] == "https://timas.com.tr/dilek-agaci" and it["sales"] == 42 and it["on_sale"] is True


def test_item_without_crm_card_falls_back_to_product_fields():
    it = F.item(product(IsActive="false"), None, SITE)
    assert it["authors"] == ["Ayşe Yazar"] and it["isbn"] == "9786050000000"
    assert it["audience"] is None and it["illustrators"] == [] and it["on_sale"] is False


def test_item_needs_id_and_name():
    assert F.item(product(ProductId=""), None, SITE) is None
    assert F.item(product(ProductName="  "), None, SITE) is None


def test_audience_labels_and_codes():
    assert [F._audience(v) for v in ("Çocuk", "GENÇ", "Yetişkin", 3, "CHILD", "?", None)] == \
        ["CHILD", "YOUNG", "ADULT", "ADULT", "CHILD", None, None]


def test_all_categories_reads_known_list_shapes():
    p = product(Categories=[{"CategoryPath": "Çocuk", "CategoryName": "Masal"}, "Çok Satanlar", {"Name": ""}])
    assert F.all_categories(p) == [["Çocuk", "Masal"], ["Çok Satanlar"]]
    assert F.all_categories(product()) == []


def test_editor_header_is_ascii():
    # X-Editor bir HTTP başlığı: «zamanlayıcı» ASCII değil, gece beslemesi ilk elle koşuda bu yüzden düştü (09-28).
    assert F.header_name("zamanlayıcı") == "zamanlayici"
    assert F.header_name("Şükrü Öztürk") == "Sukru Ozturk"
    assert F.header_name("") == "zamanlayici"
    assert F.header_name("timas\\murat.sancar").isascii()


def test_only_books_by_isbn_barcode():
    assert F.is_book(product(Barcode="9786050000000"))
    assert F.is_book(product(Barcode="9791000000000"))
    assert F.is_book(product(Barcode="19786256767331"))          # set: «1» + ISBN
    assert not F.is_book(product(Barcode="8682815950163"))       # kutu oyunu
    assert not F.is_book(product(Barcode=""))
    assert not F.is_book(product(Barcode="L8440"))


def test_feed_disabled_environment_sends_nothing(monkeypatch):
    # Müşteri VM'i (STUDIO_LIBRARY_FEED=0) arşivi beslemez; GPU'daki ortak arşivi yalnız okur (09-29 kararı).
    monkeypatch.setenv("STUDIO_LIBRARY_FEED", "0")
    assert not F.feed_enabled()

    def boom(*a, **k):
        raise AssertionError("beslemesi kapalı ortam stüdyoya yazmamalı")
    monkeypatch.setattr(F.editorial_studio, "post_json", boom)
    monkeypatch.setattr(F, "build", boom)
    assert F.feed(object()) == {"started": False, "reason": "bu ortam arşivi beslemez"}
    monkeypatch.setenv("STUDIO_LIBRARY_FEED", "1")
    assert F.feed_enabled()
    monkeypatch.delenv("STUDIO_LIBRARY_FEED")
    assert F.feed_enabled()


def test_proxy_paths_stay_inside_gpu_ingress_read_routes(monkeypatch):
    # VM köprüsü arşivi GPU genel nginx'inden okur; yalnız bu iki kalıp dışarı açık (add-studio-routes.py,
    # EDITOR-STUDYO-KUTUPHANE). Köprünün ürettiği her okuma yolu bunlardan birine uymalı, yoksa nginx 200+HTML döner.
    import re
    routes = [re.compile(r"^/v1/studio/library(/categories|/covers)?$"),
              re.compile(r"^/v1/studio/library/covers/([a-z]{2,10}-[A-Za-z0-9_.-]{1,60})(/image)?$")]
    seen = []
    monkeypatch.setattr(F.editorial_studio, "get_json", lambda path: seen.append(path) or {})
    F._get("")
    F._get("/categories", {"audience": "CHILD"})
    F._get("/covers", {"cat": "Çocuk > Masal", "q": "ağaç", "sort": "sales", "page": 2, "size": 60})
    F._get("/covers", {"cat": ""})
    F._get(f"/covers/{F._cid('tsoft-12345')}")
    seen.append(f"/v1/studio/library/covers/{F._cid('tsoft-12345')}/image?w=360")
    assert len(seen) == 6
    for p in seen:
        assert any(r.match(p.split("?")[0]) for r in routes), p
