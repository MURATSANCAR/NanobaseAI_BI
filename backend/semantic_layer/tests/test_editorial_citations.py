"""Kitaba sor: sayfa atıfının kitabı ve çoklu sayfa atıfı (ZEKI-43).

Önce: cevap tek bir kitap kimliği taşıyordu; seçili kitapla başka bir kitap karşılaştırılınca ikinci kitabın sayfa
rozetleri de seçili kitabın sayfasını açıyordu. «(s. 114, 127)» atıfında yalnız 114 rozet oluyordu.
Kitap adları burada sahte kart verisidir; kodda kitap adı/sayfa yoktur.
"""
from __future__ import annotations

from semantic_bridge import editorial_citations as C

A = "aaaaaaaa-0000-0000-0000-000000000001"
B = "bbbbbbbb-0000-0000-0000-000000000002"
CARDS = [
    {"id": A, "title": "birinci-kitap", "publisher": {"title": "Birinci Kitap"}},
    {"id": B, "title": "ikinci-kitap", "publisher": {"title": "İkinci Kitap"}},
    {"id": "cccccccc-0000-0000-0000-000000000003", "title": "anilmayan", "publisher": None},
]


def _pages(text):
    return [p for _s, _e, ps in C.groups(text) for p in ps]


def test_multi_page_forms():
    assert _pages("asıl konu ( s. 114, 127)") == [114, 127]
    assert _pages("s. 12-14") == [12, 14]
    assert _pages("s. 12–14") == [12, 14]
    assert _pages("ss. 3, 5 ve 9") == [3, 5, 9]
    assert _pages("sayfa 7 ve 8") == [7, 8]
    assert _pages("[s.2]") == [2]
    assert _pages("[s.3 p2]") == [3]
    assert _pages("s. 3, s. 5") == [3, 5]


def test_long_closed_lists_are_one_group_and_numbers_are_not_split():
    """Canlıda bozuk görünen cevaplar: sayı geri adımla bölünüyordu («44,59» → 4 + «4,59»), kapanış ayracı dışarıda kalıyordu."""
    t = "Gölge'dir (s.81, 101,130]."
    (s, e, ps), = C.groups(t)
    assert ps == [81, 101, 130] and t[s:e] == "(s.81, 101,130]"
    t = "anlatılır s.17, 44,59,68,88,93,95,119,120,124,128,135,149,160,171,174,191,192]"
    (s, e, ps), = C.groups(t)
    assert ps[:4] == [17, 44, 59, 68] and len(ps) == 18 and t[e - 1] == "]" and e == len(t)
    assert _pages("[s. 4, 59, 68, 88]") == [4, 59, 68, 88]
    # açılışsız grup cümlenin parantezini yutmaz; ayraçsız grupta ondalık atıf değildir, sayı bölünmez
    t = "(bkz. s. 12) sonra"
    (s, e, ps), = C.groups(t)
    assert ps == [12] and t[s:e] == "s. 12"
    assert _pages("s. 14, 3,5 milyon") == [14]
    assert _pages("s. 101,130 arası") == [101]


def test_not_citations():
    assert _pages("s. 14, 3 kişi gelir") == [14]
    assert _pages("s. 3, 5 ve 9 arasında") == [3, 5]
    assert _pages("vs. 14") == []


def test_norm_turkish():
    assert C.norm("İkinci Kitap'ta") == "ikinci kitap ta"
    assert C.norm("birinci-kitap") == "birinci kitap"


def test_candidates_selected_and_named():
    books, default = C.candidates(CARDS, "birinci-kitap", "İkinci Kitap ile benzerliği ne?", "…")
    assert [b["id"] for b in books] == [A, B]
    assert default == A
    books, default = C.candidates(CARDS, None, "İkinci Kitap'ı anlat", "…")
    assert [b["id"] for b in books] == [B] and default == B
    books, default = C.candidates(CARDS, None, "Birinci Kitap ve İkinci Kitap", "…")
    assert default is None


def test_resolve_by_last_mention():
    answer = "Burada dede anlatılır [s. 5]. İkinci Kitap'ta asıl konu anne (s. 114, 127)."
    books, default = C.candidates(CARDS, "birinci-kitap", "benzerlik", answer)
    assert C.resolve(answer, books, default) == [(A, [5]), (B, [114, 127])]


def test_generic_card_name_is_not_a_mention():
    """ZEKI-70: adı yalnız «Kitap» olan kart; cevabın sonraki paragrafında «kitap» kelimesi atıfı ona kaydırıyordu."""
    cards = CARDS + [{"id": "dddddddd-0000-0000-0000-000000000004", "title": "Kitap", "publisher": {"title": "2. Kitap"}}]
    answer = "Ana konu evrim [s. 22]. Kitap, dönemin aydınlarını da ele alır [s. 22, 25]."
    books, default = C.candidates(cards, "birinci-kitap", "kitabın konusu ne?", answer)
    assert [b["id"] for b in books] == [A]
    assert C.resolve(answer, books, default) == [(A, [22]), (A, [22, 25])]


def test_build_verifies_each_book_page():
    answer = "Burada dede [s. 5]. İkinci Kitap'ta asıl konu (s. 114, 127)."
    have = {(A, 5), (B, 114)}
    out = C.build("benzerlik", "birinci-kitap", answer, cards=CARDS, check=lambda b, p: (b, p) in have)
    assert out["defaultId"] == A
    assert out["pages"] == {A: {"5": True}, B: {"114": True, "127": False}}


def test_build_unknown_is_not_written():
    out = C.build("q", "birinci-kitap", "x [s. 5]", cards=CARDS, check=lambda b, p: None)
    assert out["pages"] == {}


def test_export_pill_covers_whole_group():
    from semantic_bridge import editorial_export
    runs = editorial_export._runs("konu ( s. 114, 127)")
    assert ("page", "s. 114, 127") in runs
