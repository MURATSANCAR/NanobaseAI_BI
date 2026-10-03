"""Kitap adı (editor.book_title): dosya adı temizliği, Türkçe başlık yazımı, künye/site eşleşmesi, kaynak önceliği
ve kişinin adının korunması. Model ve veritabanı yok."""
from __future__ import annotations

import pytest

from editor import book_title as BT


# ------------------------------------------------------------------ Türkçe harf büyüklüğü
def test_turkish_lower_upper():
    assert BT.tr_lower("IŞIK İZİ") == "ışık izi"
    assert BT.tr_upper("ışık izi") == "IŞIK İZİ"
    # Türkçe harf taşımayan büyük harfli metinde I, İ yerine yazılmış sayılır
    assert BT.tr_lower("MEKSIKO", ascii_text=True) == "meksiko"


@pytest.mark.parametrize("given,want", [
    ("todişin bir günü", "Todişin Bir Günü"),
    ("O ZAMAN ARKADAŞIZ", "O Zaman Arkadaşız"),
    ("IVIRTILI ZIVIRTILI ALIŞVERİŞLER", "Ivırtılı Zıvırtılı Alışverişler"),
    ("MEKSIKO", "Meksiko"),
    ("Mucitler icat oykuleri", "Mucitler İcat Oykuleri"),
    ("kedi ve köpek ile ya da mi", "Kedi ve Köpek ile ya da mi"),
    ("ve sonra hiç kimse kalmadı", "Ve Sonra Hiç Kimse Kalmadı"),
    ("hz. muhammed", "Hz. Muhammed"),
    ("hz muhammed", "Hz. Muhammed"),
    ("todi'nin bir günü", "Todi'nin Bir Günü"),
    ("osmanlı tarihi ii", "Osmanlı Tarihi II"),
    ("I DÜNYA SAVAŞI ve ÖNCESİ", "I Dünya Savaşı ve Öncesi"),
    ("savaş: ve sonrası", "Savaş: Ve Sonrası"),
])
def test_title_case(given, want):
    assert BT.title_case(given) == want


def test_hand_written_mixed_case_is_kept():
    for t in ("Ela'nın Neşeli Günlüğü", "alparslanin Yolu anadolu", "DNA: Olay Yeri İnceleme"):
        assert BT.title_case(t) == t


# ------------------------------------------------------------------ dosya adından
@pytest.mark.parametrize("name,want", [
    ("1- todişin bir günü (2).pdf", "Todişin Bir Günü"),
    ("1 todişin bir günü", "Todişin Bir Günü"),
    ("2-cezeri-baski (2).pdf", "Cezeri"),
    ("01- O ZAMAN ARKADAŞIZ.pdf", "O Zaman Arkadaşız"),
    ("01_Yeni Delhi-es (2).pdf", "Yeni Delhi es"),          # ortadaki «Yeni» adın parçası, atılmaz
    ("10.Tünel Meğer Gizli.pdf", "Tünel Meğer Gizli"),
    ("04-13 Selam_K47_10.pdf", "Selam"),                     # sayfa aralığı + dergi künye kodu
    ("10-17 Su ve Sufilik_K43_7+R.pdf", "Su ve Sufilik"),
    ("1-2 020 deneme kitabı.pdf", "Deneme Kitabı"),
    ("2020. Yaz Tatili.pdf", "Yaz Tatili"),
    ("1-I_DÜNYA SAVAŞI ve ÖNCESİ 16.5 x 23 cm.pdf", "I Dünya Savaşı ve Öncesi"),
    ("10-hz muhammed baski (2).pdf", "Hz. Muhammed"),
    ("11 Levent - Düşen Diş IC.pdf", "Levent - Düşen Diş"),
    ("Merakli Kutu 3. Baskı İç.pdf", "Merakli Kutu"),
    ("yazdiklariylayasayanlar-135x210-18f.pdf", "Yazdiklariylayasayanlar"),
    ("2.kitap (2).pdf", "2. Kitap"),                         # numara adın kendisi
    ("7.Kitap (2).pdf", "7. Kitap"),
])
def test_from_file(name, want):
    assert BT.from_file(name)["title"] == want


def test_numbers_inside_the_name_are_kept_and_flagged():
    # ortadaki yıl kitap adının parçası olabilir: atılmaz, gözden geçir işaretlenir
    f = BT.from_file("zümre 2020. din (2).pdf")
    assert f["title"] == "Zümre 2020. Din"
    assert "adda sayı ya da yıl var" in f["review"]
    # ayraçsız baştaki sayı adın parçasıdır («100 Soruda», «1453 Geldim»)
    assert BT.from_file("1453geldimkusattim (2).pdf")["title"] == "1453geldimkusattim"
    assert BT.from_file("1868 baski.pdf")["title"] == "1868"


def test_glued_words_and_missing_turkish_letters_are_not_guessed():
    f = BT.from_file("meleklerbeniseviyor (2).pdf")
    assert f["title"] == "Meleklerbeniseviyor"
    assert "kelimeler bitişik olabilir" in f["review"] and "Türkçe harf yok" in f["review"]
    assert BT.from_file("hzsuleyman.pdf")["title"] == "Hzsuleyman"
    assert BT.from_file("noktacik-baski.pdf")["title"] == "Noktacik"


def test_file_title_always_needs_review():
    for n in ("Melekler Beni Seviyor.pdf", "1- todişin bir günü (2).pdf"):
        assert BT.from_file(n)["review"][0] == "dosya adından"
    assert "baştaki numara atıldı" in BT.from_file("1- todişin bir günü.pdf")["review"]


def test_strip_prefix_only_at_the_start():
    assert BT.strip_prefix("zümre 2020. din") == ("zümre 2020. din", [])
    assert BT.strip_prefix("1-2 020 kitap adı")[0] == "kitap adı"
    assert BT.strip_prefix("04-13 Selam")[0] == "Selam"


# ------------------------------------------------------------------ künye
@pytest.mark.parametrize("claim,file_title,want", [
    ("NOKTACIK", "Noktacik", "Noktacık"),
    ("Melekler Beni Seviyor...", "Meleklerbeniseviyor", "Melekler Beni Seviyor"),
    ("TAKILI KALAN ZİHİN Düşünüp Durma Döngüsünden Çıkış Rehberi", "takili kalan zihin", "Takılı Kalan Zihin"),
    ("KAHRAMAN AVCISI KEREM-2 KAHRAMANIM FATİH", "kahramanim fatih", "Kahramanım Fatih"),
    ("Hazreti Süleyman", "Hz. Süleyman", "Hazreti Süleyman"),
    ("TODİŞLE Boyama Zamahı", "Todişin Bir Günü", None),    # künye başka sayfayı okumuş: kullanılmaz
    ("iyi ki kitaplarım var...", "Gerçekleri Kim Karıştırdı", None),
])
def test_metadata_fit(claim, file_title, want):
    assert BT.metadata_fit(claim, file_title) == want


# ------------------------------------------------------------------ öncelik
SITE = {"row": {"title": "Todiş'in Bir Günü - Todiş'le Boyama Zamanı"}, "by": "ISBN"}


def test_user_name_is_on_top():
    r = BT.resolve("1- todişin bir günü.pdf", user="  Benim  Adım ", site=SITE, metadata=["TODİŞİN BİR GÜNÜ"])
    assert r == {"title": "Benim Adım", "source": "user", "review": [], "raw": "1- todişin bir günü.pdf"}


def test_site_before_metadata_before_file():
    r = BT.resolve("1- todişin bir günü (2).pdf", site=SITE, metadata=["TODİŞİN BİR GÜNÜ"])
    # ürün adı «Kitap - Seri» ise dosya adına uyan bütün parça
    assert (r["title"], r["source"], r["review"]) == ("Todiş'in Bir Günü", "site", [])
    r = BT.resolve("1- todişin bir günü (2).pdf", metadata=["TODİŞİN BİR GÜNÜ"])
    assert (r["title"], r["source"], r["review"]) == ("Todişin Bir Günü", "metadata", [])
    r = BT.resolve("1- todişin bir günü (2).pdf")
    assert r["source"] == "file" and r["review"]


def test_site_name_is_not_cut_to_the_file_nickname():
    r = BT.resolve("2-cezeri-baski.pdf", site={"row": {"title": "El Cezeri ve Bakır Taç - Dedemin Masal Krallığı 1"},
                                               "by": "ISBN"})
    assert r["title"] == "El Cezeri ve Bakır Taç - Dedemin Masal Krallığı 1"
    assert BT.site_name("365 Günde Peygamberler Tarihi (Fleksi Cilt)") == "365 Günde Peygamberler Tarihi"
    assert BT.site_name("Sahaflar ve Kitapçılar (Ciltli)") == "Sahaflar ve Kitapçılar"
    assert BT.site_name("Dikkat Zeka (4 Yaş)") == "Dikkat Zeka (4 Yaş)"


def test_unrelated_metadata_keeps_the_file_name_and_says_why():
    r = BT.resolve("1- todişin bir günü.pdf", metadata=["TODİŞLE Boyama Zamahı"])
    assert r["source"] == "file" and r["title"] == "Todişin Bir Günü"
    assert any(x.startswith("künyede farklı ad: TODİŞLE") for x in r["review"])


def test_automatic_never_overwrites_the_user_or_a_stronger_source():
    assert not BT.may_replace("user", "site")
    assert not BT.may_replace("site", "metadata") and not BT.may_replace("site", "file")
    assert BT.may_replace("file", "metadata") and BT.may_replace("metadata", "site") and BT.may_replace(None, "file")


def _Ix(rows):
    from editor import recommend
    return recommend.SiteIndex(rows)


def _row(**k):
    base = {"id": "b1", "title": "1 todişin bir günü", "title_source": None, "title_review": [], "title_file": None,
            "archive_path": "Cocuk/6-9_yas/1- todişin bir günü (2).pdf", "requested_by": "arsiv:Cocuk/6-9_yas"}
    return {**base, **k}


ROWS = [{"id": "tsoft-1", "title": "Todiş'in Bir Günü", "authors": [], "isbn": "9786050000001", "category": [],
         "categories": [], "page_url": None, "sales": 1},
        {"id": "tsoft-2", "title": "Melekler Beni Seviyor", "authors": [], "isbn": None, "category": [],
         "categories": [], "page_url": None, "sales": 1}]


def test_decide_user_title_is_untouched():
    assert BT.decide(_row(title="Benim Adım", title_source="user"), {"isbns": ["9786050000001"]}, _Ix(ROWS)) is None


def test_decide_legacy_archive_title_by_isbn_and_by_name():
    r = BT.decide(_row(), {"isbns": ["978-605-00-0000-1"], "titles": [], "authors": []}, _Ix(ROWS))
    assert (r["title"], r["source"], r["by"]) == ("Todiş'in Bir Günü", "site", "ISBN")
    r = BT.decide(_row(title="meleklerbeniseviyor", archive_path="Kurgu/meleklerbeniseviyor (2).pdf"),
                  {"isbns": [], "titles": [], "authors": []}, _Ix(ROWS))
    assert (r["title"], r["source"], r["by"]) == ("Melekler Beni Seviyor", "site", "TITLE")


def test_decide_legacy_title_changed_by_hand_is_untouched():
    # eski arşiv kaydının adı dosya adının eski temizliğine eşit değilse biri elle değiştirmiştir
    assert BT.decide(_row(title="Todiş'in Bir Günü"), {"isbns": [], "titles": [], "authors": []}, _Ix(ROWS)) is None
    # portaldan, elle karışık harfle yazılmış ad
    assert BT.decide(_row(title="Böcekleri Seven Kadın", archive_path=None, requested_by="portal:ayse"),
                     {"isbns": [], "titles": [], "authors": []}, _Ix([])) is None


def test_decide_file_source_upgrades_to_metadata_but_never_downgrades():
    ev = {"isbns": [], "titles": ["TODİŞİN BİR GÜNÜ"], "authors": []}
    r = BT.decide(_row(title="Todişin Bir Günü", title_source="file", title_file="1- todişin bir günü (2).pdf"),
                  ev, _Ix([]))
    assert (r["title"], r["source"], r["review"]) == ("Todişin Bir Günü", "metadata", [])
    assert BT.decide(_row(title="Todiş'in Bir Günü", title_source="site", title_file="1- todişin bir günü.pdf"),
                     {"isbns": [], "titles": [], "authors": []}, _Ix([])) is None


def test_name_match_with_another_title_is_not_taken():
    # adla eşleşen ürün yalnız dosya adının kendisiyse kabul edilir (künyedeki başka adla eşleşen ürün başka kitap)
    rows = [{**ROWS[0], "isbn": None, "title": "Boyama Zamanı"}]
    r = BT.decide(_row(), {"isbns": [], "titles": ["Boyama Zamanı"], "authors": []}, _Ix(rows))
    assert r["source"] == "file"
