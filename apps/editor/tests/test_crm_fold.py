"""CRM bağlayıcısının başlık katlaması: dosya adından gelen başlık CRM adıyla eşleşmeli. Çalıştır:

    python3 apps/editor/tests/test_crm_fold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "connectors"))

import crm_covers as C  # noqa: E402


def test_file_name_titles_fold_like_crm_titles():
    assert C.fold("Dilek Agaci.indd") == C.fold("Dilek Ağacı")
    assert C.fold("babamsultanabdulhamid-arsiv.pdf") == "babamsultanabdulhamid arsiv"
    assert C.fold("anne-terligi") == C.fold("Anne Terliği")
    assert C.fold("Kitap.Adı Devam") == "kitap adi devam"          # başlık içindeki nokta uzantı değil


def test_api_goes_to_card_service_when_configured_so():
    import io, json, os
    seen = []

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=0):
        seen.append((req.full_url, req.get_header("Authorization")))
        return _R(json.dumps({"books": []}).encode())

    real, env = C.urllib.request.urlopen, dict(os.environ)
    C.urllib.request.urlopen = fake
    try:
        for k in ("EDITOR_API", "EDITOR_MCP_KEY"):
            os.environ.pop(k, None)
        os.environ.update(EDITOR_CATALOG_BASE="http://127.0.0.1:18889/", EDITOR_CATALOG_KEY="k1")
        C.api("requests"); C.api("store", {"book_id": "x"})
        os.environ.update(EDITOR_API="http://editor-mcp:8000", EDITOR_MCP_KEY="k2")
        C.api("requests")
    finally:
        C.urllib.request.urlopen = real
        os.environ.clear(); os.environ.update(env)
    assert seen == [("http://127.0.0.1:18889/v1/catalog/cover-requests", "Bearer k1"),
                    ("http://127.0.0.1:18889/v1/catalog/crm-lookups", "Bearer k1"),
                    ("http://editor-mcp:8000/catalog/cover-requests", "Bearer k2")]


def _book(i, name, author, urun=None, project=None):
    from datetime import datetime
    b = {"new_kitapId": i, "new_name": name, "new_KitabnAd": name, "new_urunadi": urun or name,
         "new_yazartext": author, "new_isbn13": None, "new_isbn": None, "new_projekarti": project,
         "ModifiedOn": datetime(2026, 1, int(i[-1]) + 1)}
    b["_titles"] = {t for t in (C.fold(b[k]) for k in ("new_name", "new_KitabnAd", "new_urunadi")) if t}
    b["_compact"] = {t.replace(" ", "") for t in b["_titles"]}
    b["_first"] = {C.compact(C.first_part(b[k])) for k in ("new_name", "new_KitabnAd", "new_urunadi")}
    b["_isbns"] = set()
    return b


def test_dash_or_space_inside_a_word_is_spelling():
    # CRM «E-beveyn», kitabın iç kapağı «Dİjİtal … e-beveyn», editör başlığı «Ebeveyn»
    crm = [_book("a1", "Dijital Dünyada E-beveyn Olmak", "Yazar Bir", project="p"),
           _book("a2", "Dijital Dünyada E-beveyn Olmak", "Yazar Bir", urun="Dijital Dünyada E-Beveyn Olmak"),
           _book("a3", "Yeterince İyi Ebeveyn Olmak", "Yazar İki"),
           _book("a4", "Doğal Ebeveynlik", "Yazar Üç")]
    for title in ("Dijital Dünyada Ebeveyn Olmak", "Dİjİtal Dünyada e-beveyn olmak", "DIJITAL DÜNYADA E BEVEYN OLMAK"):
        how, rows, _ = C.match(crm, [], title)
        assert {r["new_kitapId"] for r in rows} == {"a1", "a2"}, title
        assert how in ("COMPACT+EDITIONS", "TITLE+EDITIONS"), (title, how)
        assert rows[0]["new_kitapId"] == "a1"                      # proje kartı olan kayıt metni verir
    assert C.compact("Allah'ın İsimleri") == C.compact("Allahın İsimleri")


def test_compact_never_beats_an_equal_title_and_never_guesses():
    crm = [_book("b1", "Hoşça Kal", "Yazar Bir"), _book("b2", "Hoşçakal", "Yazar İki")]
    assert [r["new_kitapId"] for r in C.match(crm, [], "Hoşçakal")[1]] == ["b2"]     # tam ad önce
    assert [r["new_kitapId"] for r in C.match(crm, [], "Hoşça Kal")[1]] == ["b1"]
    # tam adı CRM'de olmayan bir yazım iki ayrı yazarın kitabına birden düşerse tahmin yok
    assert C.match(crm, [], "Hoş Çakal")[0] == "AMBIGUOUS"
    # editörün doğruladığı yazar ayırır
    assert [r["new_kitapId"] for r in C.match(crm, [], "Hoş Çakal", ["Yazar İki"])[1]] == ["b2"]
    # boşluksuz eşitlik bir kelimeyi yutamaz: farklı ad eşleşmez
    assert C.match(crm, [], "Hoşça Kalın")[0] == "NONE"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)


def test_file_name_without_its_order_number_and_the_books_own_name_inside_a_series_name():
    crm = [_book("c1", "Todiş'in Bir Günü - Todiş'le Boyama Zamanı", "Yazar Bir"),
           _book("c2", "Todiş Ne Yiyor? - Todiş'le Boyama Zamanı", "Yazar Bir")]
    # editörün adı hâlâ dosya adı; temizlenmiş ad `titles` ile gelir, bitişik/kesmeli yazım ilk parçaya eşit
    how, rows, _ = C.match(crm, [], "1 todişin bir günü", titles=["Todişin Bir Günü"])
    assert (how, [r["new_kitapId"] for r in rows]) == ("SEGMENT", ["c1"])
    how, rows, _ = C.match(crm, [], "emircantasarrufuogreniyor")
    assert how == "NONE"
    assert C.first_part("Gözlerini Kocaman Aç - Duyularla Rabbimi Tanıyorum 3 (Pencereli Kitap)") == \
        "Gözlerini Kocaman Aç"
    assert C.first_part("Dikkat Zeka (4 Yaş)") == "Dikkat Zeka (4 Yaş)"


def test_a_number_in_a_partial_name_must_be_equal():
    crm = [_book("d1", "3N Kitap Kırtasiye İnsert 2020", "")]
    assert C.match(crm, [], "3 KITAP")[0] == "NONE"
    crm = [_book("d2", "Kaybolan Balinaların Şarkısı", "Yazar")]
    assert C.match(crm, [], "kaybolan balinalar")[0] == "PARTIAL"
    assert C.match([_book("d3", "Kayıp İslam Tarihi", "")], [], "kayi I")[0] == "NONE"
    assert C.match([_book("d4", "Kitapkıran 1", "")], [], "KITAP 1")[0] == "NONE"
    assert C.match([_book("d5", "Levent Van'da - Türkiye'yi Geziyorum 5", "")], [], "levent Van")[0] == "PARTIAL"


def test_a_record_that_is_not_a_book_is_never_a_partial_match():
    for name in ("Entel Dantel İşler Ayraç", "Dedektif Aynes Seti (4 Kitap)", "Bilim Dedektifleri 3 (İptal Edildi)",
                 "Öteki Beriki Diğeri 15x21 Kartpostal"):
        assert C.match([_book("n1", name, "")], [], " ".join(name.split()[:2]))[0] == "NONE", name
    # hikâye setindeki bir kitap kitaptır (set adı « - »'den sonra)
    crm = [_book("n2", "Kampta Oyun Var - Selim'in Renkli Dünyası - 3. Sınıf Hikaye Seti", "")]
    assert C.match(crm, [], "kampta oyun")[0] == "PARTIAL"


def test_ambiguous_records_sharing_the_books_name_still_name_the_book():
    crm = [_book("e1", "Penguen Karcan - Mini Masallar 3 (30)", "Yazar Bir", project="p"),
           _book("e2", "Penguen Karcan - Penton The Penguin (İngilizce)", "Yazar İki")]
    rep = C.report(None, crm, {"book_id": "x", "title": "penguenkarcan"}, with_image=False)
    assert rep["outcome"] == "AMBIGUOUS" and rep["crm_title"] == "Penguen Karcan" and "crm" not in rep
    crm = [_book("f1", "Mavi Kuş - Orman Masalları", "A", urun="Mavi"), _book("f2", "Mavi Deniz", "B", urun="Mavi")]
    rep = C.report(None, crm, {"book_id": "y", "title": "mavi"}, with_image=False)
    assert rep["outcome"] == "AMBIGUOUS" and "crm_title" not in rep


def test_a_name_taken_from_the_crm_does_not_re_match_by_itself():
    crm = [_book("k1", "Arsen Lüpen - Kibar Hırsız", "M. Leblanc"), _book("k2", "Arsen Lüpen - Kristal Tıpa", "M. Leblanc"),
           _book("k3", "Arsen Lüpen", "M. Leblanc", urun="Arsen Lüpen Seti")]
    # editör: önce dosya adı, en son bugünkü (CRM'den gelmiş) ad
    how, rows, _ = C.match(crm, [], "Arsen Lüpen - Kibar Hırsız", titles=["Arsen Lupen Kibar Hirsiz",
                                                                          "Arsen Lüpen - Kibar Hırsız"])
    assert [r["new_kitapId"] for r in rows] == ["k1"], how
    how, rows, _ = C.match(crm, [], "Arsen Lüpen", titles=["Arsen Lupen Kibar Hirsiz", "Arsen Lüpen"])
    assert [r["new_kitapId"] for r in rows] == ["k1"] and how == "TITLE"


def test_an_automatic_title_is_left_out_of_matching():
    crm = [_book("k1", "Arsen Lüpen - Herlock Sholmes'e Karşı", "M"), _book("k2", "Arsen Lüpen - Kristal Tıpa", "M"),
           _book("k3", "Arsen Lüpen - Kontes Cagliostro", "M")]
    b = {"title": "Arsen Lüpen", "titles": ["Arsen Lupen Herlock", "arsen lupen herlock baski"], "title_auto": True}
    how, rows, _ = C.match_book(crm, b)
    assert (how, [r["new_kitapId"] for r in rows]) == ("PARTIAL", ["k1"])
    assert C.match_book(crm, {**b, "title_auto": False})[0] == "AMBIGUOUS"     # kişinin adı önce gelir


def test_only_new_or_changed_books_are_read_again():
    from datetime import datetime
    crm = [_book("g1", "Hafıza Bakımı", "Bora Jin", project="p1")]          # ModifiedOn 2026-01-02
    m = C.match(crm, [], "hafizabakimi")
    last = {"at": "2026-02-01T10:00:00+00:00", "outcome": "NO_IMAGE", "crm_book_id": "g1", "crm_title": "Hafıza Bakımı"}
    assert not C.unchanged({"title": "x"}, m, {})                               # hiç aranmamış
    assert C.unchanged({"last_lookup": last}, m, {})                            # değişmedi
    assert not C.unchanged({"last_lookup": {**last, "at": "2026-01-01T00:00:00+03:00"}}, m, {})   # kayıt sonra değişti
    assert not C.unchanged({"last_lookup": last}, m, {"p1": datetime(2026, 3, 1)})                # yeni kapak
    assert not C.unchanged({"last_lookup": {**last, "crm_book_id": "eski"}}, m, {})               # başka kayıt
    assert not C.unchanged({"last_lookup": {**last, "outcome": "NO_MATCH"}}, m, {})               # artık bulunuyor
    none = C.match(crm, [], "bambaşka kitap")
    assert C.unchanged({"last_lookup": {**last, "outcome": "NO_MATCH"}}, none, {})
    assert not C.unchanged({"last_lookup": last}, none, {})                     # eşleşme kayboldu: kayıt silinmeli
    amb = [_book("h1", "Penguen Karcan - Mini Masallar 3", "A"), _book("h2", "Penguen Karcan - Penton (İngilizce)", "B")]
    ma = C.match(amb, [], "penguenkarcan")
    assert C.unchanged({"last_lookup": {**last, "outcome": "AMBIGUOUS", "crm_title": "Penguen Karcan"}}, ma, {})
    assert not C.unchanged({"last_lookup": {**last, "outcome": "AMBIGUOUS", "crm_title": None}}, ma, {})
