"""Stüdyo baskı dışı sayfa kararı: okumanın hikâye dışı önerisi yalnız adaydır; sayfa ancak metni künye, içindekiler,
tanıtım, iç kapak ya da yazar tanıtımı olduğunu gösterirse basılmaz (2026-10-01)."""

from editor.production.manuscript import print_plan

BODY = ("Ahlak, insanın yapıp etmelerini ve bu yapıp etmelerin dayandığı huyları inceleyen bir ilimdir; "
        "bu bölümde onun kaynakları ele alınır ve düşünürlerin görüşleri sırayla değerlendirilir.")


def _book(n=120):
    pages = {p: ["DENEME KİTABI", BODY, BODY] for p in range(1, n + 1)}
    pages[1] = ["İstanbul 2026"]
    pages[2] = ["DENEME KİTABI Ayşe Yılmaz", "ÖRNEK YAYINLARI", "EDİTÖR Ali Veli", "Yayın Yönetmeni Can Can",
                "ISBN 978-605-08-0000-0", "Yayıncı Sertifika No: 12364", "Baskı ve Cilt: Matbaa A.Ş."]
    pages[3] = ["Deneme Kitabı", "Ayşe Yılmaz"]
    pages[4] = ["AYŞE YILMAZ", "Ayşe Yılmaz 1980 yılında Konya'da doğdu. Lisans eğitimini Ankara'da tamamladı."]
    pages[5] = ["İÇİNDEKİLER", "Önsöz / 7 Giriş / 11 Birinci Bölüm / 15 İkinci Bölüm / 40"]
    pages[6] = ["Üçüncü Bölüm / 60 Dördüncü Bölüm / 80 Sonsöz / 110 Kaynakça / 114"]
    pages[7] = ["Babamın aziz hatırasına..."]
    pages[8] = ["ÖNSÖZ", BODY]
    pages[n - 3] = ["Yazarın Notu", BODY]
    pages[n - 2] = ["KAYNAKÇA", "Aydın, S. Türkiye Tarihi. İstanbul: İletişim Yayınları, 2014.",
                    "Yeni kitap önerimiz için karekodu telefon kameranıza okutunuz."]
    pages[n - 1] = ["iyi ki kitaplar var...", "BAŞKA BİR KİTAP", "ZEYNEP KAYA", "Tanıtım yazısı burada."]
    pages[n] = []
    return pages


def test_nonfiction_body_stays_even_if_reading_called_it_non_story():
    pages = _book()
    plan = print_plan(pages, set(pages), 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert plan[1][0] == "künye" and plan[2][0] == "künye"
    assert plan[3] == ("iç kapak", 0)
    assert plan[4] == ("yazar tanıtımı", 0)
    assert plan[5] == ("içindekiler", 0) and plan[6] == ("içindekiler", 0)
    assert plan[118] == ("yayınevi tanıtımı", 2)        # kaynakça kalır, reklam satırı çıkar
    assert plan[119] == ("yayınevi tanıtımı", 0)
    # ithaf, önsöz, gövde, yazarın notu basılır
    for p in (7, 8, 9, 60, 110, 117):
        assert p not in plan, p


def test_only_candidates_can_be_dropped():
    pages = _book()
    plan = print_plan(pages, {1, 5}, 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert set(plan) == {1, 5}


def test_promo_word_in_body_is_not_an_ad():
    pages = _book()
    pages[50] = ["DENEME KİTABI", "Uygulamadaki karekodu okutmadan önce gizlilik ayarlarına bakın. " + BODY]
    plan = print_plan(pages, set(pages), 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert 50 not in plan and 60 not in plan


def test_running_header_with_title_is_not_half_title():
    pages = _book()
    pages[9] = ["DENEME KİTABI", "kısa bir sayfa sonu."]
    plan = print_plan(pages, set(pages), 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert 9 not in plan


def test_bio_when_author_name_is_also_running_header_and_decomposed_dotted_i():
    pages = _book()
    for p in range(10, 60, 2):
        pages[p] = ["AYŞE YILMAZ", BODY]               # yazar adı çift sayfa başlığı
    pages[4] = ["Ayşe Yılmaz", "Ayşe Yılmaz 1980 yılında Konya'da dünyaya geldi. " + BODY]
    plan = print_plan(pages, set(pages), 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert plan[4] == ("yazar tanıtımı", 0)
    pages[4] = ["AYŞE YİLMAZ (PROF. DR.) 1980 yılında Konya'da doğdu. " + BODY]   # «İ» = I + nokta
    plan = print_plan(pages, set(pages), 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert plan[4] == ("yazar tanıtımı", 0)


def test_trailing_book_ads_without_qr_page():
    pages = _book()
    pages[118] = ["KAYNAKÇA", "Aydın, S. Türkiye Tarihi. İstanbul: İletişim Yayınları, 2014."]
    pages[119] = ["iyi ki kitaplar var...", "BAŞKA BİR", "KİTAP ADI", "ZEYNEP KAYA", "Tanıtım yazısı."]
    pages[120] = ["iyi ki kitaplar var...", "ÜÇÜNCÜ KİTAP", "MEHMET ÖZ", "Tanıtım yazısı."]
    plan = print_plan(pages, set(pages), 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert plan[119] == ("yayınevi tanıtımı", 0) and plan[120] == ("yayınevi tanıtımı", 0)
    assert 118 not in plan and 117 not in plan
