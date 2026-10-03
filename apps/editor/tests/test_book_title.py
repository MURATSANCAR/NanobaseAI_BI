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
    # dosya adına uyan parça yoksa kitabın adı ilk parçadır (seri adı « - »'den sonra); parçanın içinden kelime seçilmez
    assert r["title"] == "El Cezeri ve Bakır Taç"
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
    assert not BT.may_replace("crm", "site") and BT.may_replace("site", "crm") and not BT.may_replace("user", "crm")
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


# ------------------------------------------------------------------ CRM (kullanıcı kararı 2026-10-03: CRM > site)
def test_crm_name_comes_before_the_site():
    crm = {"title": "Todiş'in Bir Günü - Todiş'le Boyama Zamanı", "by": "SEGMENT"}
    r = BT.resolve("1- todişin bir günü (2).pdf", crm=crm, site={"row": {"title": "Başka Ad"}, "by": "ISBN"})
    assert (r["title"], r["source"], r["review"], r["by"]) == ("Todiş'in Bir Günü", "crm", [], "SEGMENT")
    assert BT.resolve("x.pdf", user="Benim Adım", crm=crm)["source"] == "user"


def test_crm_partial_match_is_flagged():
    r = BT.resolve("istediğim insan.pdf", crm={"title": "İstediğim İnsan Olma Yolunda", "by": "PARTIAL"})
    assert r["title"] == "İstediğim İnsan Olma Yolunda" and r["source"] == "crm"
    assert r["review"] and r["review"][0].startswith("CRM'de kısmi ad eşleşmesi")


@pytest.mark.parametrize("record, file_title, want", [
    ("Gözlerini Kocaman Aç - Duyularla Rabbimi Tanıyorum 3 (Pencereli Kitap)", "Gozlerini Kocaman Ac",
     "Gözlerini Kocaman Aç"),
    ("Kamptan Yükselen Sesler - Mucit Mete Ve Tayfası - 3. Sınıf Hikaye Seti (10. Kitap)", "Kamptan Yukselen Sesler",
     "Kamptan Yükselen Sesler"),
    ("Sherlock Holmes - Trendeki Ceset", "Trendeki Ceset", "Trendeki Ceset"),
    ("Rüzgarın Ardından: Ayine-i Zülcenaheyn", "Rüzgârın Ardından", "Rüzgarın Ardından: Ayine-i Zülcenaheyn"),
    ("Piri Reis Ve Acayip Haritası", "Piri Reis ve Acayip Haritasi", "Piri Reis ve Acayip Haritası"),
    ("Dinozor Ferro İle Tanışalım - Güçlü Dinozorlar", "Dinozor Ferro", "Dinozor Ferro ile Tanışalım"),
    ("Kayıp Kılıç (Önceki Ebat)", "Kayipkilic", "Kayıp Kılıç"),
    ("Dikkat Zeka (4 Yaş)", "", "Dikkat Zeka (4 Yaş)"),
    ("Mülk ve Hukuk: Osmanlı Vergi Düzeninde Meşruiyet Sorunu", "Mulkvehukuk",
     "Mülk ve Hukuk: Osmanlı Vergi Düzeninde Meşruiyet Sorunu"),
    ("GALATASARAY", "galatasaray", "Galatasaray"),
    ("Hamam mı? Tamam mı? - Uçuk Ailemle Kaçık Maceralar", "Hamammi Tamammi", "Hamam mı? Tamam mı?"),
    # seri adı önde, dosya adı iki parçayı da taşıyor: kaydın tamamı
    ("Arsen Lüpen - Kibar Hırsız", "Arsen Lupen Kibar Hirsiz", "Arsen Lüpen - Kibar Hırsız"),
    ("Arsen Lüpen - Herlock Sholmes'e Karşı", "Arsen Lupen Herlock", "Arsen Lüpen - Herlock Sholmes'e Karşı"),
    ("Levent - Doğu Ekspresi'nde Soygun", "Levent Dogu Ekspresi", "Levent - Doğu Ekspresi'nde Soygun"),
])
def test_record_name(record, file_title, want):
    assert BT.record_name(record, file_title) == want


def test_decide_takes_the_crm_name_and_the_site_by_first_segment():
    ev = {"isbns": [], "titles": [], "authors": [], "crm": {"title": "Todiş'in Bir Günü - Boyama", "by": "SEGMENT"}}
    r = BT.decide(_row(), ev, _Ix([]))
    assert (r["title"], r["source"]) == ("Todiş'in Bir Günü", "crm")
    rows = [{**ROWS[0], "isbn": None, "title": "Todiş'in Bir Günü - Todiş'le Boyama Zamanı (Ciltli)"}]
    r = BT.decide(_row(), {"isbns": [], "titles": [], "authors": []}, _Ix(rows))
    assert (r["title"], r["source"], r["by"]) == ("Todiş'in Bir Günü", "site", "SEGMENT")
    # CRM'den gelen ad siteyle ezilmez
    assert BT.decide(_row(title="Todiş'in Bir Günü", title_source="crm", title_file="1- todişin bir günü.pdf"),
                     {"isbns": ["9786050000001"], "titles": [], "authors": []}, _Ix(ROWS)) is None


def test_capital_forma_and_glued_print_suffix_are_dropped():
    assert BT.from_file("turkiyeninzihintarihi 13,5F.pdf")["title"] == "Turkiyeninzihintarihi"
    assert BT.from_file("cagribey 10F.pdf")["title"] == "Cagribey"
    assert BT.from_file("onun gibi yasamaya var misinBASKI.pdf")["title"] == "Onun Gibi Yasamaya Var Misin"
    assert "BASKI" not in BT.from_file("yorganımınaltindansesleniyorumBASKI.pdf")["title"]


def test_every_source_is_allowed_by_the_database():
    # 2026-10-03: «crm» kaynağı eklenince göç 032'nin CHECK'i canlıda her ad yazımını düşürdü; birim testleri DB'siz
    # olduğu için görmedi. Son göçteki izin listesi koddaki kaynaklarla aynı olmalı.
    import re
    from pathlib import Path
    migs = sorted((Path(__file__).resolve().parents[1] / "db" / "migrations").glob("*.sql"))
    last = [m for m in migs if "book_title_source_check" in m.read_text()][-1].read_text()
    allowed = set(re.findall(r"'(\w+)'", last.split("book_title_source_check")[-1]))
    assert allowed == set(BT.SOURCES), (allowed, BT.SOURCES)
