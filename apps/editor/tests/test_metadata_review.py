"""Künye iddialarının okurken gözden geçirilmesi (`editor.metadata_review`, 56 kitap denetimi 2026-10-03).
Adlar ve değerler elle yazılmıştır; hiçbir kitap koddan okunmaz. Model ve DB yok."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from editor import metadata_review as MR  # noqa: E402


def _m(subject, claim):
    return {"subject": subject, "claim": claim, "source_pages": [2]}


def test_title_shared_by_many_books_is_a_series_slogan():
    shared = {MR.fold("iyi ki kitaplarım var"): 7}
    out = MR.review([_m("TITLE", "İyi ki Kitaplarım Var"), _m("TITLE", "Deniz Feneri")],
                    names=["Deniz Feneri"], shared=shared)
    assert out[0]["subject"] == "SERIES" and out[0]["flag"] == "SHARED_TITLE"
    assert MR.title_values(out) == ["Deniz Feneri"]


def test_title_of_another_book_of_the_series_is_marked():
    out = MR.review([_m("TITLE", "Filippo ve Kayıp Kedi")], names=["Filippo, Ben ve Kiraz Ağacı"])
    assert out[0]["flag"] == "SERIES_BOOK" and MR.title_values(out) == []
    # kitabın kendi adı (alt başlıklı ya da bitişik yazılmış) işaretlenmez
    for t in ("Filippo, Ben ve Kiraz Ağacı", "FİLİPPO BEN VE KİRAZ AĞACI", "Kiraz Ağacı"):
        assert not MR.series_book(t, ["Filippo, Ben ve Kiraz Ağacı"]), t
    # hiç kelime paylaşmayan ad: bir şey söylenmez (book_title gözden geçirir)
    assert not MR.series_book("Bambaşka Bir Ad", ["Filippo, Ben ve Kiraz Ağacı"])
    # bir-iki harflik okuma hatası aynı addır
    assert not MR.series_book("Bir Delinin Sınar Günluğu", ["Bir Delinin Sınav Günlüğü"])
    # künyenin TITLE'ı aynı künyenin dizi adıysa kitabın adı değildir
    out = MR.review([_m("TITLE", "ALPARSLAN’IN AKINCISI"), _m("SERIES", "Alparslan'ın Akıncısı")],
                    names=["Özgürlük Savaşı", "Alparslan'ın Akıncısı"])
    assert out[0]["subject"] == "SERIES" and out[0]["flag"] == "SERIES_NAME"


def test_publisher_that_is_a_person_name_is_dropped():
    pubs = {MR.fold("Timaş Yayınları"): 40, MR.fold("Genç Timaş"): 12}
    assert MR.person_like("Ayşe Yılmaz", ["Ayşe Yılmaz"], pubs)
    assert MR.person_like("Melek Kaya", [], pubs)
    for v in ("Timaş Yayınları", "Genç Timaş", "Timaş Çocuk", "Erdem Kitap", "Timaş", "İlk Genç Timaş"):
        assert not MR.person_like(v, [], pubs), v
    out = MR.review([_m("PUBLISHER", "Ayşe Yılmaz"), _m("PUBLISHER", "Timaş Yayınları")],
                    people=["Ayşe Yılmaz"], publishers=pubs)
    assert [m["claim"] for m in out] == ["Timaş Yayınları"]


def test_book_title_word_stuck_to_the_author_is_trimmed_only_to_a_known_person():
    assert MR.trim_author("Çiğdem Can İcat", ["İcat Öyküleri"], ["Çiğdem Can"]) == "Çiğdem Can"
    assert MR.trim_author("Çiğdem Can Icat", ["Mucitler ve İcat Öyküleri"], ["Çiğdem Can"]) == "Çiğdem Can"
    # soyadı kitap adının ilk kelimesi: bilinen kişi değilse kırpılmaz
    assert MR.trim_author("Ali Rıza Kaya", ["Kaya Gibi Sağlam"], ["Mehmet Can"]) == "Ali Rıza Kaya"
    assert MR.trim_author("Ali Kaya", ["Kaya Gibi"], ["Ali"]) == "Ali Kaya"        # iki kelimenin altına inmez
    assert MR.trim_author("Çiğdem Can İcat", ["İcat Öyküleri"], []) == "Çiğdem Can İcat"
    out = MR.review([_m("AUTHOR", "Çiğdem Can İcat"), _m("TITLE", "İcat Öyküleri")], names=["İcat Öyküleri"],
                    people=["Çiğdem Can"])
    assert out[0]["claim"] == "Çiğdem Can" and out[0]["original_claim"] == "Çiğdem Can İcat"


def test_context_counts_books_once_and_is_cached():
    class Cur:
        n = 0

        def execute(self, sql, params=None):
            Cur.n += 1
            rows = [{"subject": "TITLE", "claim": "Slogan", "book_id": b} for b in ("a", "b", "c", "c")] + \
                   [{"subject": "TITLE", "claim": "Tek Kitap", "book_id": "a"},
                    {"subject": "PUBLISHER", "claim": "Timaş", "book_id": "a"},
                    {"subject": "PUBLISHER", "claim": "TİMAŞ", "book_id": "b"}]
            return type("R", (), {"fetchall": lambda _s: rows})()
    MR._CTX.update(at=0.0, value=None)
    ctx = MR.context(Cur(), now=100.0)
    assert ctx["shared"] == {"slogan": 3} and ctx["publishers"] == {"timas": 2}
    MR.context(Cur(), now=200.0)
    assert Cur.n == 1
    MR._CTX.update(at=0.0, value=None)
