"""Okuma denetimi düzeltmeleri D (2026-10-03): süslü yazımlı bölüm başlığı (K14) ve «Ad + hitap» karakter kaydı (K15).
Hiçbir kitap, ad ya da sayfa numarası koddan okunmaz; buradaki adlar ve metinler elle yazılmıştır. PDF, model ve
veritabanı yok.

K14. Tasarım fontuyla büyük-küçük karışık dizilmiş başlık («BÖReKlEr, KrEdİ KaRtI DÖKÜMlErİ Ve») Türkçe başlık
     yazımıyla gösterilir; bağlaçla BİTEN başlık sonraki kısa satırla / başlıkla birleşir. «GİRİŞ» ve «Kulağım Kapıda»
     değişmez.
K15. «Ad + aile hitabı» («Safiş yengem», «Yasemin abla», «Suna teyze») yalın «Ad» ile birleşir — ad kitapta tek
     anlamlıysa, cinsiyet çelişmiyorsa. «X'in babası» X ile ASLA birleşmez. Unvanlı tarihî ad («Ahmed Paşa»,
     «Nuri Efendi», «Selim Han») yalın adla birleşmez.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


def _missing(root: str) -> bool:
    try:
        return importlib.util.find_spec(root) is None
    except ValueError:
        return False


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx",
             "yaml", "pymupdf", "qdrant_client", "qdrant_client.models"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))

from editor import chapters as typeset  # noqa: E402
from editor import identity, outputs  # noqa: E402

BODY = ("Sabah erkenden kalktı ve dükkânın kepengini yavaşça kaldırdı, içeri serin bir koku doldu; sokak "
        "henüz uyanmamıştı ve martılar çatıların üstünde dönüp duruyordu.")


# ------------------------------------------------------------------ K14 bölüm başlığı
def test_fancy_case_title_is_written_in_turkish_title_case():
    assert typeset.display_title("BÖReKlEr, KrEdİ KaRtI DÖKÜMlErİ Ve BeN") == "Börekler, Kredi Kartı Dökümleri ve Ben"
    assert typeset.display_title("ÇÖP ToRbAlArI, HaVlUlAr Ve BeN") == "Çöp Torbaları, Havlular ve Ben"


def test_regular_titles_are_not_touched():
    for t in ("GİRİŞ", "Kulağım Kapıda", "BÖLÜM 1 OSMANLI MERKEZ VE TAŞRA", "Birinci Bölüm AŞKIN MAHİYETİ",
              "İBN SÎNÂ AHLAKIN ELİFBESİ", "ALİ'nin Evi", "Darwin ve Osmanlılar", "0.7 UCU OLAN VAR MI?"):
        assert typeset.display_title(t) == t


def test_conjunction_at_the_end():
    assert typeset.ends_with_conjunction("BÖReKlEr, KrEdİ KaRtI DÖKÜMlErİ Ve")
    assert typeset.ends_with_conjunction("Kahve ya da")
    assert typeset.ends_with_conjunction("ÇAY İLE")
    assert not typeset.ends_with_conjunction("Ankara'da")          # kesmeyle bitişik ek bağlaç değil
    assert not typeset.ends_with_conjunction("Ve")
    assert not typeset.ends_with_conjunction("GİRİŞ")


def _h(title, size=16.0, kind="sunk"):
    return {"title": title, "size": size, "kind": kind}


def _text_pages(n):
    return [{"page_no": p, "spans": [{"text": BODY}]} for p in range(1, n + 1)]


def test_title_ending_with_a_conjunction_takes_the_next_short_heading():
    heads = {3: _h("BÖReKlEr, KrEdİ KaRtI DÖKÜMlErİ Ve"), 4: _h("BeN", 20.0), 9: _h("GİRİŞ")}
    found = [(c["title"], c["page_from"], c["page_to"]) for c in typeset.chapters_from_pages(_text_pages(12), heads)]
    assert found[1:] == [("Börekler, Kredi Kartı Dökümleri ve Ben", 3, 8), ("GİRİŞ", 9, 12)]
    # bağlaçla bitmeyen başlıktan sonraki kısa başlık ayrı bölüm; uzak sayfadaki başlık da ayrı
    heads = {3: _h("Kulağım Kapıda"), 4: _h("BeN")}
    assert [c["title"] for c in typeset.chapters_from_pages(_text_pages(12), heads)][1:] == ["Kulağım Kapıda", "Ben"]
    heads = {3: _h("DÖKÜMlEr Ve"), 9: _h("BeN")}
    assert len(typeset.chapters_from_pages(_text_pages(12), heads)) == 3


def _ln(text, y0, size=10.0, x0=60.0):
    return {"text": text, "y0": y0, "size": size, "x0": x0, "x1": x0 + 6 * len(text)}


def test_title_line_ending_with_a_conjunction_takes_the_next_short_line_on_the_page():
    L = {"body": 10.0, "step": 14.0, "top": 0.1}
    lines = [_ln("ÇÖP ToRbAlArI, HaVlUlAr Ve", 120, 18.0), _ln("BeN", 170, 14.0)]
    lines += [_ln(BODY[:70], 230 + 14 * k) for k in range(12)]
    o = typeset._opening({"lines": lines, "h": 600.0}, L)
    assert o["title"] == "ÇÖP ToRbAlArI, HaVlUlAr Ve BeN"
    # bağlaçla bitmeyen başlığın altındaki kısa satır başlığa katılmaz
    lines[0] = _ln("ÇÖP TORBALARI", 120, 18.0)
    assert typeset._opening({"lines": lines, "h": 600.0}, L)["title"] == "ÇÖP TORBALARI"


def test_report_shows_the_display_title_for_an_old_chapter_summary():
    snap = {"title": "K", "revision": 1, "blockers": [], "generation_id": "g", "events": [], "emotions": [],
            "reviews": [], "contradictions": []}
    rep = outputs.render_report(snap, {"chapters": [{"title": "HaVlUlAr Ve BeN", "sentences": []},
                                                    {"title": "GİRİŞ", "sentences": []}]}, {"sentences": []})
    assert [c["title"] for c in rep["chapters"]] == ["Havlular ve Ben", "GİRİŞ"]


# ------------------------------------------------------------------ K15 «Ad + hitap»
def _p(name, pages, sex="FEMALE", kind="HUMAN_ADULT", windows=(), n=None):
    return {"name": name, "kind": kind, "sex": sex, "entity_scope": "INDIVIDUAL", "pages": set(pages),
            "windows": set(windows), "aliases": [], "n": n if n is not None else len(pages)}


def _plan(units):
    return identity.same_name_plan(units, lambda n: True)


def test_family_address_forms():
    a = identity.family_address("Safiş yengem")
    assert (a["base"], a["root"], a["sex"], a["base_text"]) == ("safiş", "yenge", "FEMALE", "Safiş")
    assert identity.family_address("Yasemin abla")["root"] == "abla"
    assert identity.family_address("Suna Teyze")["root"] == "teyze"
    assert identity.family_address("Ali amcası")["root"] == "amca"
    assert identity.family_address("Mehmet ağabeyim")["sex"] == "MALE"
    # tamlama, unvan, tek sözcük: hitap değil
    for n in ("Lidya'nın babası", "Lidya’nın teyzesi", "Kahraman Avcısı'nın Babası", "Ahmed Paşa", "Nuri Efendi",
              "Selim Han", "Ayşe Sultan", "Hatice Hanım", "Ali Bey", "Rıza Hoca", "Dayım", "Teyze", "Baba"):
        assert identity.family_address(n) is None, n


def test_name_with_family_address_joins_the_bare_name():
    for addr in ("Safiş yengem", "Yasemin abla", "Suna teyze"):
        base = addr.split()[0]
        clusters, refused = _plan([_p(base, [3, 9, 20]), _p(addr, [40, 41])])
        assert clusters == [[0, 1]] and refused == [], addr
    # cinsiyeti okunmamış hitaplı kayıt: hitabın cinsiyeti sayılır, erkek yalın adla birleşmez
    clusters, refused = _plan([_p("Deniz", [3, 9], sex="MALE"), _p("Deniz abla", [40], sex="UNKNOWN")])
    assert clusters == [] and refused[0]["reason"] == "SEX_CONFLICT"
    clusters, refused = _plan([_p("Deniz", [3, 9], sex="UNKNOWN"), _p("Deniz abla", [40], sex="UNKNOWN")])
    assert clusters == [[0, 1]]


def test_ambiguous_name_is_not_joined():
    # aynı adla başka kayıt (soyadlı, unvanlı) ya da iki ayrı hitap: kim olduğu belirsiz
    for other in ("Suna Yılmaz", "Suna Hanım", "Suna abla"):
        clusters, refused = _plan([_p("Suna", [3, 9]), _p("Suna teyze", [40]), _p(other, [60])])
        assert clusters == [], other
        assert refused[0]["reason"] in ("ADDRESS_NAME_SHARED", "ADDRESS_TWO_ROOTS")
    # okunmuş cinsiyet hitapla çelişiyor
    clusters, refused = _plan([_p("Can", [3]), _p("Can abla", [40], sex="MALE")])
    assert clusters == [] and refused[0]["reason"] == "ADDRESS_SEX"
    # yalın adın iki kaydı (iki kişi olabilir): hitaplı kayıt hiçbirine katılmaz
    clusters, _ = _plan([_p("Suna", [3]), _p("Suna", [3]), _p("Suna teyze", [40])])
    assert all(2 not in g for g in clusters)
    # okuma ayrı tuttuysa (aynı sayfa) birleşmez
    clusters, refused = _plan([_p("Suna", [3, 40]), _p("Suna teyze", [40])])
    assert clusters == [] and refused[0]["reason"] == "SAME_PAGE"


def test_possessive_relative_is_another_person():
    # «Lidya'nın babası» Lidya'nın kendisi değildir
    units = [_p("Lidya", [3, 9]), _p("Lidya'nın babası", [40], sex="MALE"), _p("Lidya’nın annesi", [50])]
    assert _plan(units)[0] == []
    units = [_p("Lidya", [3, 9]), _p("Lidya'nın teyzesi", [40])]
    assert _plan(units)[0] == []


def test_historical_titles_never_join_the_bare_name():
    # tarih/biyografi: «Ahmed Paşa», «Nuri Efendi», «Nuri Ağa» ile «Ahmed», «Nuri» farklı kişiler olabilir
    for titled in ("Ahmed Paşa", "Ahmed Bey", "Ahmed Efendi", "Ahmed Ağa", "Şeyh Ahmed", "Hz. Ahmed", "Ahmed Han",
                   "Ahmed Hoca"):
        assert _plan([_p("Ahmed", [3, 9], sex="MALE"), _p(titled, [40], sex="MALE")])[0] == [], titled
    # aile hitabı aynı kitapta birleşir
    assert _plan([_p("Ahmed", [3, 9], sex="MALE"), _p("Ahmed amca", [40], sex="MALE")])[0] == [[0, 1]]


def test_narrators_father_is_not_folded_by_rule():
    # (c) «Babam» ile «<anlatıcı>'nın babası»: anlatıcı kaydı bilinmeden kural birleştirmez
    units = [_p("Babam", [3, 9], sex="MALE"), _p("Kahraman Avcısı'nın Babası", [40], sex="MALE")]
    assert identity.same_name_plan(units, lambda n: False)[0] == []
